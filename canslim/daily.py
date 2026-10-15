"""Daily run: refresh data, rank, and write the report.

System (chosen by the 2016-2026 walk-forward test, see data/system/results.csv):
  book_rules -- O'Neil's CAN SLIM as hard filters, ranked by RS rating,
  with the market filter "no new buys unless the market is in a confirmed uptrend".

Steps
  1. prices: incremental Fyers update (all NSE equities + indices)
  2. fundamentals: re-fetch companies that just reported (Screener latest results),
     plus anything older than 7 days on Sundays
  3. factors as of today's close, market state
  4. top 10 (+ near-miss watchlist), base pattern + pivot for each, reasons
  5. sell flags for names listed in the last 60 days
  6. data/reports/<date>.html (+ latest.html), data/history/picks.csv

Research output only. Not investment advice; no orders are ever placed.

usage: python -m canslim.daily [--skip-update] [--skip-fundamentals]
"""
import argparse
import html
import json
import re
import time
import traceback
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import data, earnings_monitor, factors, patterns, sectors, stockchart
from canslim.research import FUND_COLS, SIGN
from canslim.system import market_state

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "data" / "reports"
HISTORY = ROOT / "data" / "history"
LOG = ROOT / "data" / "daily.log"

# book rules as tuned in canslim.tune (data/tune/final.json)
RULES = [
    ("Uptrend (price > 50 > 150 > 200-day, 200-day rising)", lambda r: r.trend == 1),
    ("Within 15% of 52-week high", lambda r: r.prox_high >= 0.85),
    ("Quarterly profit growth >= 25%", lambda r: r.np_yoy >= 25),
    ("Sales growth >= 20% or 2+ strong quarters", lambda r: (r.sales_yoy >= 20) or (r.streak >= 2)),
    ("3-year profit growth >= 15%/yr", lambda r: r.ttm_cagr3 >= 15),
    ("ROE >= 20%", lambda r: r.roe >= 20),          # tuned 2016-22 (book: 17%+), confirmed on 2023-26 hold-out
    ("RS rating >= 80", lambda r: r.rs >= 80),
    ("Net profit margin up vs a year ago", lambda r: r.npm_chg > 0),   # book rule 6; adopted 2026-10-02 (booktest)
]


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ------------------------------------------------------------------ refresh
def update_prices():
    from canslim import prices
    from canslim.fyers_auth import get_client
    fy = get_client()
    syms = prices.INDICES + prices.universe()
    prices.update(syms, 3, fy, quiet=True)


def recent_reporters(pages: int = 10) -> list:
    """NSE symbols on Screener's 'latest quarterly results' pages."""
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        pg = next((x for x in b.contexts[0].pages if "screener.in" in x.url), None) or b.contexts[0].new_page()
        if "screener.in" not in pg.url:
            pg.goto("https://www.screener.in/")
        for n in range(1, pages + 1):
            h = pg.evaluate("u => fetch(u).then(r => r.text())", f"/results/latest/?p={n}")
            out += re.findall(r'href="/company/([A-Z][A-Z0-9&\-]*)/(?:consolidated/)?#quarters"', h)
            time.sleep(1.3)
    return list(dict.fromkeys(out))


def update_fundamentals(liquid: list):
    from canslim import fundamentals as fu
    names = set(liquid)
    fresh = [s for s in recent_reporters() if s.replace("&", "and") in names or s in names]
    stale_cutoff = time.time() - 86400
    todo = [s for s in fresh if not fu.path_for(s).exists() or fu.path_for(s).stat().st_mtime < stale_cutoff]
    log(f"fundamentals: {len(fresh)} recent reporters in universe, {len(todo)} to refresh")
    if todo:
        fu.update(todo, max_age_days=0)
    if date.today().weekday() == 5:        # Saturday run: sweep anything older than a week
        fu.update([n.replace("and", "&") if n in ("MandM", "MandMFIN") else n for n in sorted(names)],
                  max_age_days=7)


# ------------------------------------------------------------------ snapshot
def snapshot():
    P = data.panels(refresh=True)
    F = factors.price_factors(P)
    U = factors.universe_mask(P, F)
    d = P["close"].index[-1]
    fund = data.fundamentals()
    ev = factors.fundamental_events(fund)
    FP = factors.fundamental_panel(ev, pd.DatetimeIndex([d]), FUND_COLS)
    row = pd.DataFrame({k: v.iloc[-1] for k, v in F.items()})
    for k, v in FP.items():
        row[k] = v.iloc[-1].reindex(row.index)
    row["universe"] = U.iloc[-1].reindex(row.index).fillna(False)
    row["has_f"] = row.np_yoy.notna()
    elig = row.universe & row.has_f
    row["rs"] = row.rs_ibd.where(elig).rank(pct=True) * 99
    ind = {k: f["industry"] for k, f in fund.items()}
    row["industry"] = pd.Series(ind).reindex(row.index)
    row["sector"] = pd.Series({k: f["sector"] for k, f in fund.items()}).reindex(row.index)
    g = row[elig].groupby("industry").rs.agg(["mean", "count"])
    g = g[g["count"] >= 3]
    g["rank"] = g["mean"].rank(ascending=False).astype(int)
    row["group_rank"] = row.industry.map(g["rank"])
    row["groups_total"] = len(g)
    rad = sectors.radar(F["rs_ibd"], U, ind)
    row["group_warn"] = row.industry.map(sectors.group_warnings(rad))
    return d, P, row[elig].copy(), fund, g, list(row.index[row.universe]), rad


def evaluate(row: pd.Series) -> list:
    return [name for name, fn in RULES if not _safe(fn, row)]


def _safe(fn, r):
    try:
        return bool(fn(r))
    except Exception:
        return False


# ------------------------------------------------------------------ sell flags
def sell_flags(sym, P, snap, first_price, first_date):
    flags = []
    c = P["close"][sym].dropna()
    v = P["volume"][sym].reindex(c.index)
    if c.empty:
        return ["no price data"]
    last = c.iloc[-1]
    chg = (last / first_price - 1) * 100
    if chg <= -8:
        flags.append(f"down {chg:.1f}% from first listing (book: cut losses at 7-8%)")
    ma50 = c.rolling(50).mean()
    avgv = v.rolling(50).mean()
    if last < ma50.iloc[-1] and v.iloc[-1] > 1.5 * avgv.iloc[-1]:
        flags.append("closed below 50-day MA on heavy volume")
    if len(c) > 15 and c.iloc[-1] / c.iloc[-15] - 1 >= 0.25 and chg >= 50:
        flags.append("climax run: +25% in 3 weeks after a big advance (book: consider selling into strength)")
    if sym in snap.index:
        r = snap.loc[sym]
        failed = evaluate(r)
        if failed:
            flags.append("no longer passes: " + "; ".join(failed))
    else:
        flags.append("dropped out of the liquid universe / data missing")
    return flags


# ------------------------------------------------------------------ report
def fmt(x, nd=0, suffix=""):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}{suffix}"


def reasons(r) -> str:
    parts = [f"RS {fmt(r.rs)}", f"{fmt((r.prox_high - 1) * 100, 1, '%')} from high",
             f"Qtr profit {fmt(r.np_yoy, 0, '%')}", f"Sales {fmt(r.sales_yoy, 0, '%')}",
             f"3y profit CAGR {fmt(r.ttm_cagr3, 0, '%')}", f"ROE {fmt(r.roe, 0, '%')}",
             f"SUE {fmt(r.sue, 1)}"]
    if not pd.isna(r.group_rank):
        parts.append(f"group #{int(r.group_rank)}/{int(r.groups_total)}")
    return " · ".join(parts)


RUNUP_FLAG = 1.0          # label above +100% in 6 months: historically MORE likely to double again, with bigger swings
                          # (canslim.runup: skipping them hurt; canslim.winners: ~2x base rate of doubling in 2016-21 and 2023-25)


def buy_point(b) -> str:
    """Book Ch.2 buy point as a badge: not yet / at pivot / extended."""
    if b is None:
        return "<span class='pill mut'>n/a</span>"
    if b.kind == "none":
        return f"<span class='pill mut'>Not yet</span><div class=muted>{html.escape(b.summary())}</div>"
    if b.status in ("forming", "near pivot"):
        return f"<span class='pill mut'>Not yet</span><div class=muted>{b.dist:+.1f}% vs pivot {b.pivot:.2f}</div>"
    if b.status.startswith("breakout"):
        light = " · light volume" if "light" in b.status else ""
        return f"<span class='pill ok'>At pivot</span><div class=muted>{b.dist:+.1f}% vs pivot {b.pivot:.2f}{light}</div>"
    return f"<span class='pill bad'>Extended</span><div class=muted>{b.dist:+.1f}% past pivot {b.pivot:.2f}</div>"


def runup_cell(c: pd.Series) -> str:
    c = c.dropna()
    if len(c) <= 126:
        return "–"
    r = c.iloc[-1] / c.iloc[-127] - 1
    if r > RUNUP_FLAG:
        return f"<span class='pill ok'>{r * 100:+.0f}%</span><div class=muted>strong momentum, swings hard</div>"
    return f"{r * 100:+.0f}%"


CHART_CSS = """
:root{--c0:#52514e;--c1:#eb6834;--c2:#2a78d6}
@media (prefers-color-scheme:dark){:root{--c0:#c3c2b7;--c1:#d95926;--c2:#3987e5}}
button.sym{font:inherit;font-weight:600;color:var(--fg);background:none;border:0;border-bottom:1px dashed var(--mut);padding:0;cursor:pointer}
button.sym:hover,button.sym.on{color:var(--c2);border-bottom-color:var(--c2)}
#drawer{position:fixed;top:12px;right:12px;width:min(480px,calc(100vw - 24px));max-height:calc(100vh - 24px);overflow:auto;
 background:var(--card);border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 32px rgba(0,0,0,.25);padding:12px 14px;z-index:10}
#drawer[hidden]{display:none} #drawer .dh{display:flex;align-items:center;gap:6px}
#drawer .dh b{font-size:16px} #dx{margin-left:auto;font-size:16px;background:none;border:1px solid var(--line);border-radius:6px;color:var(--fg);cursor:pointer;padding:2px 9px}
.rng{display:flex;gap:4px;margin:10px 0 4px} .rng button{font:inherit;font-size:12px;padding:2px 10px;border:1px solid var(--line);border-radius:6px;background:none;color:var(--fg);cursor:pointer}
.rng button.on{border-color:var(--c2);color:var(--c2)} .lg{display:flex;gap:14px;font-size:12px;color:var(--mut)}
.lg i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:5px}
#ch{width:100%;height:auto;display:block;margin-top:4px} #ch text{fill:var(--mut);font-size:10px}
#ch .grid{stroke:var(--line)} #ch .x{stroke:var(--mut);stroke-dasharray:3 3}
#tip{position:absolute;pointer-events:none;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px;font-size:12px;white-space:nowrap}
#tip[hidden]{display:none}
.stats{display:flex;gap:18px;margin:8px 0 4px} .stats div{font-size:12px;color:var(--mut)} .stats b{display:block;font-size:17px;color:var(--fg)}
"""

CHART_JS = """
const CD=JSON.parse(document.getElementById('chartdata').textContent);
for(const c of Object.values(CD)){let d=c.d0;c.d=[d,...c.dd.map(x=>d+=x)];
 const ema=(s,n)=>{const a=2/(n+1);let e=s;return c.c.map(v=>e+=a*(v-e))};c.e20=ema(c.s20,20);c.e200=ema(c.s200,200)}
const dr=document.getElementById('drawer'),svg=document.getElementById('ch'),tip=document.getElementById('tip');
let cur=null,yrs=5;const W=440,H=250,L=40,R=6,T=8,B=20;
const day=d=>new Date(d*864e5),f2=v=>v.toLocaleString('en-IN',{maximumFractionDigits:2}),pc=v=>(v>=0?'+':'')+(v*100).toFixed(1)+'%';
function ticks(lo,hi){let s=Math.pow(10,Math.floor(Math.log10((hi-lo)/4||1))),e=(hi-lo)/4/s;s*=e>=7.5?10:e>=3.5?5:e>=1.5?2:1;
 const o=[];for(let v=Math.ceil(lo/s)*s;v<=hi;v+=s)o.push(v);return o}
function draw(){const c=CD[cur];if(!c)return;const last=c.d[c.d.length-1],i0=Math.max(0,c.d.findIndex(x=>x>=last-yrs*365.25));
 const n=c.d.length-i0,S=['c','e20','e200'].map(k=>c[k].slice(i0)),all=S.flat(),lo=Math.min(...all),hi=Math.max(...all);
 const X=i=>L+(W-L-R)*i/Math.max(n-1,1),Y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo||1));let g='';
 for(const v of ticks(lo,hi))g+=`<line class=grid x1=${L} x2=${W-R} y1=${Y(v)} y2=${Y(v)} /><text x=${L-4} y=${Y(v)+3} text-anchor=end>${v.toLocaleString('en-IN')}</text>`;
 let py=null;for(let i=0;i<n;i++){const y=day(c.d[i0+i]).getUTCFullYear();if(y!==py&&py!==null)g+=`<text x=${X(i)} y=${H-4} text-anchor=middle>${y}</text>`;py=y}
 S.forEach((s,k)=>{g+=`<path fill=none stroke="var(--c${k})" stroke-width=${k==2?2:1.5} stroke-linejoin=round d="M${s.map((v,i)=>X(i).toFixed(1)+' '+Y(v).toFixed(1)).join('L')}"/>`});
 g+=`<line id=hx class=x y1=${T} y2=${H-B} visibility=hidden />`;svg.innerHTML=g;
 const ce=c.c[c.c.length-1],m=(a,b)=>`<div>${a}<b>${b}</b></div>`;
 document.getElementById('dstats').innerHTML=m('Close',f2(ce))+m(c.d[i0]>last-yrs*365.25+10?'Since '+day(c.d[i0]).getUTCFullYear():yrs+'y change',pc(ce/S[0][0]-1))+m('vs 20 EMA',pc(ce/c.e20[c.e20.length-1]-1))+m('vs 200 EMA',pc(ce/c.e200[c.e200.length-1]-1));
 document.getElementById('dnote').textContent='Last close '+day(last).toISOString().slice(0,10)+'. Adjusted for splits and bonuses; averages use the full history from '+c.from+'.';
 svg.onmousemove=e=>{const r=svg.getBoundingClientRect(),i=Math.round(Math.min(Math.max(((e.clientX-r.left)*W/r.width-L)/(W-L-R),0),1)*(n-1)),hx=document.getElementById('hx');
  hx.setAttribute('x1',X(i));hx.setAttribute('x2',X(i));hx.setAttribute('visibility','visible');
  tip.innerHTML=day(c.d[i0+i]).toISOString().slice(0,10)+'<br>Price <b>'+f2(S[0][i])+'</b><br>20 EMA '+f2(S[1][i])+'<br>200 EMA '+f2(S[2][i]);
  tip.hidden=false;const dl=dr.getBoundingClientRect(),x=e.clientX-dl.left+dr.scrollLeft;tip.style.left=(x>dl.width/2?x-tip.offsetWidth-12:x+12)+'px';tip.style.top=(e.clientY-dl.top+dr.scrollTop+12)+'px'};
 svg.onmouseleave=()=>{tip.hidden=true;const hx=document.getElementById('hx');hx&&hx.setAttribute('visibility','hidden')}}
function openChart(s){cur=s;document.getElementById('dsym').textContent=s;dr.hidden=false;
 document.querySelectorAll('button.sym').forEach(b=>b.classList.toggle('on',b.dataset.s===s));draw()}
document.addEventListener('click',e=>{const b=e.target.closest('button.sym');if(b)openChart(b.dataset.s)});
document.querySelectorAll('.rng button').forEach(b=>b.onclick=()=>{yrs=+b.dataset.y;document.querySelectorAll('.rng button').forEach(x=>x.classList.toggle('on',x===b));draw()});
document.getElementById('dx').onclick=()=>{dr.hidden=true;document.querySelectorAll('button.sym.on').forEach(b=>b.classList.remove('on'))};
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.getElementById('dx').click()});
"""

CHART_HTML = """<aside id=drawer hidden><div class=dh><b id=dsym></b><span class=muted>· price, 20-day and 200-day EMA</span>
<button id=dx aria-label="Close chart">✕</button></div>
<div class=rng><button data-y=1>1y</button><button data-y=2>2y</button><button data-y=5 class=on>5y</button></div>
<div class=lg><span><i style="background:var(--c0)"></i>Price</span><span><i style="background:var(--c1)"></i>20 EMA</span><span><i style="background:var(--c2)"></i>200 EMA</span></div>
<svg id=ch viewBox="0 0 440 250" role=img aria-label="Price chart"></svg><div id=tip hidden></div>
<div class=stats id=dstats></div><div class=muted id=dnote style="font-size:12px"></div></aside>"""


def chart_data(syms, years: int = 5) -> str:
    """JSON for the report's chart drawer, kept small: per symbol the last `years` of closes, dates as a first epoch
    day + gaps, and each EMA's value the day before the window (the page continues the EMAs from there, so they
    match stockchart.series exactly; a stock with less history starts from its first close, as ewm does)."""
    out = {}
    for s in sorted(syms):
        full = stockchart.series(s)
        if full.empty:
            continue
        i0 = max(0, int(full.index.searchsorted(full.index[-1] - pd.DateOffset(years=years))))
        df = full.iloc[i0:]
        days = ((df.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).to_numpy()
        seed = full.iloc[i0 - 1] if i0 else df.iloc[0]
        nd = 2 if df.close.iloc[-1] < 1000 else 1
        out[s] = {"d0": int(days[0]), "dd": np.diff(days).tolist(), "c": df.close.round(nd).tolist(),
                  "s20": round(float(seed.ema20 if i0 else seed.close), 4),
                  "s200": round(float(seed.ema200 if i0 else seed.close), 4), "from": int(full.index[0].year)}
    return json.dumps(out, separators=(",", ":"))


def render(d, ms, top, watch, sells, groups, mon=None, mon_rest=0, emg=None, rad=None) -> str:
    st = ms.iloc[-1]
    ok = st in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE")
    banner = {
        "CONFIRMED_UPTREND": ("ok", "Market in a confirmed uptrend: new positions are allowed under the system."),
        "UPTREND_UNDER_PRESSURE": ("warn", "Uptrend under pressure: distribution is building. Be selective."),
        "RALLY_ATTEMPT": ("bad", "Rally attempt, not yet confirmed: the system makes NO new buys until a follow-through day."),
        "CORRECTION": ("bad", "Market in correction: the system makes NO new buys. List shown for research/watching."),
    }[st]
    since = ms[ms != st].index.max()
    esc = html.escape
    charted = set()

    def cell(c, v):                                   # the symbol in a Stock cell opens the chart drawer
        m = re.match(r"([A-Z0-9&-]+)(.*)", str(v), flags=re.S) if c == "Stock" else None
        if not m:
            return v
        charted.add(m.group(1))
        return f'<button class=sym data-s="{esc(m.group(1))}">{esc(m.group(1))}</button>{m.group(2)}'

    def table(df, cols):
        head = "".join(f"<th>{esc(c)}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{cell(c, r[c])}</td>" for c in cols) + "</tr>" for _, r in df.iterrows())
        return f"<div class=tw><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"

    top_html = table(top, ["#", "Stock", "Buy point", "6-mo", "Industry", "Close", "Why it ranks", "Base / pivot"]) if len(top) else \
        "<p class=muted>No stock passes every rule today.</p>"
    watch_html = table(watch, ["Stock", "Buy point", "6-mo", "Industry", "RS", "Misses", "Base / pivot"]) if len(watch) else ""
    mon_html = table(mon, ["Stock", "Result", "Earnings", "Price", "Buy point", "Notes"]) if mon is not None and len(mon) else         "<p class=muted>No fresh results with strong earnings and a confirming price.</p>"
    if mon_rest:
        mon_html += f"<p class=muted>{mon_rest} more reported strong earnings but the price is not confirming yet "                     "(below the 50-day average or more than 15% off the high); full list in data/history.</p>"
    emg_html = table(emg, ["#", "Stock", "Result", "Earnings", "Price", "Buy point", "Notes"]) if emg is not None and len(emg) else         "<p class=muted>No stock meets the emerging-list rules today.</p>"
    sell_html = table(sells, ["Stock", "Listed", "Since listing", "Flags"]) if len(sells) else \
        "<p class=muted>No sell flags on recently listed stocks.</p>"
    radar_html = "<p class=muted>Sector radar unavailable.</p>"
    if rad is not None and len(rad):
        lead = rad[rad.strength >= 80].assign(
            Group=lambda x: x.group.map(lambda v: esc(str(v))), Stocks=lambda x: x.stocks, Strength=lambda x: x.strength,
            **{"Weeks in top 20%": lambda x: x.weeks_top.map(lambda w: f"{w}+" if w >= sectors.WEEKS else str(w)),
               "Top-20% weeks, last year": lambda x: x.weeks_top_last_year, "Status": lambda x: x.status})
        drop = rad[rad.status == "Dropped out"].assign(
            Group=lambda x: x.group.map(lambda v: esc(str(v))), Stocks=lambda x: x.stocks, **{"Strength now": lambda x: x.strength,
            "Weeks since it dropped out": lambda x: x.weeks_since_drop.astype(int)})
        radar_html = (f"<p class=muted>{len(rad)} industries with ≥ 5 liquid stocks, ranked weekly by the average RS of their stocks "
                      "(strength 100 = strongest). Tested 2016–26: the top 20% beat the bottom 20% by ~4% over the next 3 months; "
                      "a group typically stays in the top 20% for ~2 months (15% last 6+ months). Groups that drop out lagged the "
                      "market by 1–5% over the next 3–12 months.</p><h3>Strong now (top 20%)</h3>"
                      + table(lead, ["Group", "Stocks", "Strength", "Weeks in top 20%", "Top-20% weeks, last year", "Status"])
                      + "<h3>Dropped out of the top 20% in the last 13 weeks (warning)</h3>"
                      + (table(drop, ["Group", "Stocks", "Strength now", "Weeks since it dropped out"]) if len(drop)
                         else "<p class=muted>None.</p>"))
    grp = groups.sort_values("rank").head(15).reset_index()
    grp_html = "".join(f"<li>{esc(str(r['industry']))} <span class=muted>(RS {r['mean']:.0f}, {int(r['count'])} stocks)</span></li>"
                       for _, r in grp.iterrows())
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>CAN SLIM scan {d:%d %b %Y}</title><style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--line:#e4e3de;--ok:#1f7a4d;--warn:#a36a00;--bad:#b3261e;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--fg:#ecebe6;--mut:#9a9993;--line:#2c2c2a;--card:#1d1d1c;--ok:#4cc38a;--warn:#e0a73a;--bad:#f07167}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:1150px;margin:auto}} h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px}}
.muted{{color:var(--mut)}} .banner{{border-left:4px solid;padding:10px 14px;background:var(--card);margin:16px 0}}
.ok{{border-color:var(--ok)}} .warn{{border-color:var(--warn)}} .bad{{border-color:var(--bad)}}
.tw{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:6px}}
table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-weight:600;font-size:12px;color:var(--mut);white-space:nowrap}} td:first-child{{white-space:nowrap}}
ul{{margin:0;padding-left:18px}}
.pill{{display:inline-block;padding:1px 8px;border-radius:10px;font-weight:600;font-size:12px;white-space:nowrap;border:1px solid}}
.pill.ok{{color:var(--ok)}} .pill.warn{{color:var(--warn)}} .pill.bad{{color:var(--bad)}} .pill.mut{{color:var(--mut)}}
td div.muted{{font-size:12px}} footer{{margin-top:32px;font-size:12px}}
{CHART_CSS}</style></head><body><main>
<h1>CAN SLIM daily scan — {d:%A %d %b %Y}</h1>
<div class=muted><a href="winners_study.html">Big-winner study</a> · NSE close · O'Neil's rules, ranked by RS · tested 2016–2026: 21% CAGR vs Nifty 500 12% (research only) · click a stock for its chart</div>
<div class="banner {banner[0]}"><b>{st.replace('_', ' ').title()}</b> (since {since.date() if since is not pd.NaT and since == since else '–'}) — {banner[1]}</div>
<h2>Top {len(top)} — pass every rule</h2>{top_html}
<h2>Earnings monitor — latest quarterly results (last {earnings_monitor.FRESH_DAYS} days), any size</h2>
<div class=muted style="margin-bottom:8px">Strong quarter = operating margin up 6+ points vs a year ago, and/or profit up 50%+ in each of the
last two quarters (the two earnings signals that held up in both test periods). Shown only when the price confirms:
above the 50-day average and within 15% of the high. <a href="winners_study.html">What the study found</a></div>{mon_html}
<h2>Emerging / turnaround list — higher risk</h2>
<div class=muted style="margin-bottom:8px">Strong recent earnings (the same two signals) + RS ≥ 80 + uptrend + within 15% of the high +
≥ Rs 5 Cr/day, with <b>no ROE or 3-year-growth rule</b>, so turnarounds like Laurus Labs (2020) can qualify. Ranked by RS, max 3 per industry.
Tested 2016–22 as a 10-stock portfolio: <b>21.9%/yr but a worst drop of −39%</b>, vs CAN SLIM 23.8%/yr and −21%. It passed the bar for a
separate list (narrowly in 2016–19), not for replacing CAN SLIM. The same market filter applies.</div>{emg_html}
<h2>Watchlist — miss one rule</h2>{watch_html or '<p class=muted>None.</p>'}
<h2>Sell flags on stocks listed in the last 60 days</h2>{sell_html}
<h2>Sector radar</h2>{radar_html}
<h2>Leading industry groups (all sizes, ≥ 3 stocks)</h2><ul>{grp_html}</ul>
<footer class=muted>Rules: {esc('; '.join(n for n, _ in RULES))}. Market filter: no new buys unless the market model
shows a confirmed uptrend. Base patterns are annotations (book Ch.2): buy zone = pivot to +5% on volume ≥ 40% above average.
Buy point: Not yet = below the pivot or no sound base; At pivot = within the buy zone; Extended = more than 5% past the pivot.
6-mo above +100% is labelled "strong momentum": on NSE 2016-2025 such stocks doubled again about twice as often
as average, but also swung harder (see data/research/winners). Information only, not a ranking rule.
Generated {datetime.now():%Y-%m-%d %H:%M}. Research only — not investment advice. Created by Amrendra Kumar.</footer>
</main>{CHART_HTML}<script type="application/json" id=chartdata>{chart_data(charted)}</script>
<script>{CHART_JS}</script></body></html>"""


def run(skip_update=False, skip_fund=False):
    REPORTS.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    if not skip_update:
        log("updating prices")
        update_prices()
    d, P, snap, fund, groups, liquid, rad = snapshot()
    if not skip_fund:
        try:
            update_fundamentals(liquid)
            d, P, snap, fund, groups, liquid, rad = snapshot()
        except Exception as e:
            log(f"fundamentals refresh failed (using cached data): {e}")
    log(f"snapshot {d.date()}: {len(snap)} liquid stocks with fundamentals")
    ms = market_state(P)
    idx = data.index_close()
    snap["failed"] = [evaluate(r) for _, r in snap.iterrows()]
    snap["n_fail"] = snap.failed.map(len)
    passing = snap[snap.n_fail == 0].sort_values("rs", ascending=False)
    # industry cap of 3, as in the backtest
    picks, per = [], {}
    for s, r in passing.iterrows():
        g = r.industry
        if g and per.get(g, 0) >= 3:
            continue
        per[g] = per.get(g, 0) + 1
        picks.append(s)
        if len(picks) == 10:
            break

    bases = {}

    def base_obj(s):
        if s not in bases:
            try:
                df = pd.DataFrame({k: P[k][s] for k in ("open", "high", "low", "close", "volume")}).dropna()
                bases[s] = patterns.detect(df, idx)
            except Exception as e:
                log(f"base detection failed for {s}: {e}")
                bases[s] = None
        return bases[s]

    def base_of(s):
        b = base_obj(s)
        return b.summary() if b is not None else "n/a"

    top = pd.DataFrame([{"#": i + 1, "Stock": s.replace("and", "&") if s in ("MandM", "MandMFIN") else s,
                         "Buy point": buy_point(base_obj(s)), "6-mo": runup_cell(P["close"][s]),
                         "Industry": html.escape(str(snap.at[s, "industry"])),
                         "Close": f"{P['close'][s].dropna().iloc[-1]:.2f}",
                         "Why it ranks": reasons(snap.loc[s]), "Base / pivot": html.escape(base_of(s))}
                        for i, s in enumerate(picks)])
    near = snap[(snap.n_fail == 1) & (snap.rs >= 70)].sort_values("rs", ascending=False).head(15)
    watch = pd.DataFrame([{"Stock": s, "Buy point": buy_point(base_obj(s)), "6-mo": runup_cell(P["close"][s]),
                           "Industry": html.escape(str(r.industry)), "RS": f"{r.rs:.0f}",
                           "Misses": html.escape(r.failed[0]), "Base / pivot": html.escape(base_of(s))}
                          for s, r in near.iterrows()])
    # history + sell flags
    hist_f = HISTORY / "picks.csv"
    hist = pd.read_csv(hist_f, parse_dates=["date"]) if hist_f.exists() else pd.DataFrame(
        columns=["date", "rank", "symbol", "close", "rs", "market"])
    recent = hist[(hist.date >= pd.Timestamp(d) - pd.Timedelta(days=60)) & (hist.date < pd.Timestamp(d))]
    sells = []
    for s, g in recent.groupby("symbol"):
        if s in picks:
            continue
        first = g.sort_values("date").iloc[0]
        fl = sell_flags(s, P, snap, first.close, first.date)
        last = P["close"][s].dropna().iloc[-1] if s in P["close"] else np.nan
        sells.append({"Stock": s, "Listed": f"{first.date:%d %b}",
                      "Since listing": f"{(last / first.close - 1) * 100:+.1f}%",
                      "Flags": html.escape("; ".join(fl)) or "—"})
    sells = pd.DataFrame(sells)
    new = pd.DataFrame([{"date": d, "rank": i + 1, "symbol": s, "close": P["close"][s].dropna().iloc[-1],
                         "rs": round(snap.at[s, "rs"], 1), "market": ms.iloc[-1]} for i, s in enumerate(picks)])
    hist = pd.concat([hist[hist.date != d], new]).sort_values(["date", "rank"])
    hist.to_csv(hist_f, index=False)
    snap.drop(columns=["failed"]).assign(fails="|".join).to_csv(HISTORY / f"snapshot_{d:%Y%m%d}.csv") \
        if False else snap.assign(failed=snap.failed.map("; ".join)).to_csv(HISTORY / f"snapshot_{d:%Y%m%d}.csv")
    def earn(r):
        parts = [f"Sales {fmt(r.sales_yoy, 0, '%')}",
                 f"Profit {fmt(r.np_yoy, 0, '%')} (prev qtr {fmt(r.np_yoy_prev, 0, '%')})",
                 f"Op. margin {fmt(r.opm_ago, 0, '%')} → {fmt(r.opm_now, 0, '%')}"]
        tags = (["<span class='pill ok'>margin up</span>"] if r.margin_up else []) +                (["<span class='pill ok'>2 strong qtrs</span>"] if r.two_strong else [])
        return " ".join(tags) + "<div class=muted>" + html.escape(" · ".join(parts)) + "</div>"

    def earnings_rows(df):
        return pd.DataFrame([{"Stock": f"{s}<div class=muted>{html.escape(str(r.industry))}</div>",
                              "Result": f"{r.result_date:%d %b}"
                                        + (" <span class='pill ok'>new</span>"
                                           if (pd.Timestamp(d) - r.result_date).days <= earnings_monitor.NEW_DAYS else "")
                                        + f"<div class=muted>qtr to {r.quarter:%b %Y}</div>",
                              "Earnings": earn(r),
                              "Price": html.escape(f"{r.close:.2f} · 6-mo {fmt(r.ret6 * 100, 0, '%')} · "
                                                   f"{r.from_high:+.0f}% from high · RS {fmt(r.rs)}"),
                              "Buy point": buy_point(base_obj(s)), "Notes": html.escape(r.notes) or "–"}
                             for s, r in df.iterrows()])

    mon, mon_rest, emg = pd.DataFrame(), 0, pd.DataFrame()
    m = e_ = None
    try:
        m = earnings_monitor.scan(pd.Timestamp(d), P, fund)
        if len(m):
            m.to_csv(HISTORY / f"earnings_monitor_{d:%Y%m%d}.csv")
            mon = earnings_rows(m[m.price_ok].head(30))
            mon_rest = int((~m.price_ok).sum())
        log(f"earnings monitor: {len(m)} strong fresh results, {len(mon)} with price confirming")
    except Exception as e:
        log(f"earnings monitor failed: {e}\n{traceback.format_exc()}")
    try:
        e_ = earnings_monitor.emerging(pd.Timestamp(d), P, fund)
        if len(e_):
            e_.to_csv(HISTORY / f"emerging_{d:%Y%m%d}.csv")
            emg = earnings_rows(e_)
            emg.insert(0, "#", range(1, len(emg) + 1))
        log(f"emerging list: {len(emg)} names")
    except Exception as e:
        log(f"emerging list failed: {e}\n{traceback.format_exc()}")
    try:
        from canslim import db, holdings
        c = db.connect()
        db.store_market(c, d, ms.iloc[-1])
        db.store_snapshot(c, d, snap, P["close"].ffill().iloc[-1])
        db.store_list(c, d, "canslim", new.drop(columns="date").assign(industry=[snap.at[s, "industry"] for s in picks]))
        db.store_earnings_list(c, d, "earnings", m)
        db.store_earnings_list(c, d, "emerging", e_)
        c.commit()
        db.store_radar(c, d, rad)
        try:                                   # other frameworks (frameworks.py): separate lists, app page "Other frameworks"
            from canslim import frameworks
            Fx = factors.price_factors(P)
            for name, df in frameworks.daily_lists(P, factors.universe_mask(P, Fx), Fx["rs_ibd"], fund=fund).items():
                inp = df.drop(columns=["rank", "symbol", "close"])
                note = [json.dumps({k: (None if pd.isna(v) else float(v)) for k, v in r.items()}) for _, r in inp.iterrows()]
                db.store_list(c, d, f"fw_{name}", df[["rank", "symbol", "close"]].assign(note=note))
                log(f"framework {name}: {len(df)} stocks")
        except Exception as e:
            log(f"frameworks failed: {e}\n{traceback.format_exc()}")
        c.commit()
        st = holdings.store_status(c, d.strftime("%Y-%m-%d"))
        from canslim import paper
        log(f"paper portfolio: {paper.run(c)}")
        c.close()
        log(f"database updated: {db.DB.name}" + (f", {len(st)} holdings: " + ", ".join(
            f"{r.symbol} {r.light}" for r in st.itertuples()) if len(st) else ""))
    except Exception as e:
        log(f"database update failed: {e}\n{traceback.format_exc()}")
    page = render(d, ms, top, watch, sells, groups, mon, mon_rest, emg, rad)
    (REPORTS / f"{d:%Y-%m-%d}.html").write_text(page, encoding="utf-8")
    (REPORTS / "latest.html").write_text(page, encoding="utf-8")
    log(f"report written: {len(picks)} picks, {len(watch)} watchlist, {len(sells)} sell checks, market {ms.iloc[-1]}")
    return REPORTS / "latest.html"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-update", action="store_true")
    ap.add_argument("--skip-fundamentals", action="store_true")
    a = ap.parse_args()
    try:
        print(run(a.skip_update, a.skip_fundamentals))
    except Exception:
        log("FAILED\n" + traceback.format_exc())
        raise
