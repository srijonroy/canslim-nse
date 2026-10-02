"""Readable page for the big-winner study: data/reports/winners_study.html.

Built from the saved outputs in data/research/winners/ (no re-run needed).

usage: python -m canslim.winners_report
"""
import html as H

import pandas as pd

from canslim.winners import CHECK, OUT, ROOT

LABELS = {
    "ret6": "6-month return", "rs": "Relative strength (RS) rating", "trend": "Uptrend (price > 50 > 150 > 200-day)",
    "prox_high": "Price vs 52-week high", "opm_chg": "Operating margin change vs a year ago (pts)",
    "opm": "Operating margin (%)", "opm_chg_q": "Operating margin change vs last quarter (pts)",
    "np_min2": "Profit growth, weaker of last 2 quarters (%)", "np_yoy": "Latest quarter profit growth (%)",
    "sales_yoy": "Latest quarter sales growth (%)", "sales_min2": "Sales growth, weaker of last 2 quarters (%)",
    "sales_streak": "Quarters in a row with sales +15%", "sales_accel": "Sales growth speeding up (pts)",
    "np_accel": "Profit growth speeding up (pts)", "npm_chg": "Net margin change vs a year ago (pts)",
    "record_sales": "Record quarterly sales (1 = yes)", "record_np": "Record quarterly profit (1 = yes)",
    "ttm_cagr3": "3-year profit growth (%/yr)", "roe": "Return on equity (%)", "sue": "Earnings surprise (SUE)",
    "streak": "Quarters in a row with profit +20%", "days_since_ann": "Days since the last result",
    "value_cr": "Daily traded value (Rs Cr)", "vol60": "Volatility (3-month)", "size_pct": "Size (traded value rank)",
    "inst_chg": "FII+DII holding change (pts) - data only from 2023", "ext50": "Distance above 50-day average",
    "mom_6_1": "6-month momentum (skip last month)", "mom_12_1": "12-month momentum (skip last month)",
    "ud_vol": "Up-day vs down-day volume", "tight": "Tight recent price action", "new_high": "New 52-week high in last 2 weeks",
    "vol_surge": "Volume surge", "max_ret21": "Biggest one-day gain, last month", "group_rs": "Industry group strength",
}
KEY = [("ret6", "(1.0, inf]", "Up more than 100% in the last 6 months"),
       ("ret6", "(0.5, 1.0]", "Up 50-100% in the last 6 months"),
       ("rs", "Q5 high", "Top fifth by relative strength"),
       ("trend", "(0.5, 1.5]", "In an uptrend"),
       ("prox_high", "(0.95, 1.01]", "Within 5% of the 52-week high"),
       ("opm_chg", "(6.0, inf]", "Operating margin up 6+ points vs a year ago"),
       ("np_min2", "(50.0, inf]", "Profit up 50%+ in each of the last 2 quarters"),
       ("np_yoy", "(100.0, inf]", "Latest quarter profit up 100%+"),
       ("sales_yoy", "(40.0, inf]", "Latest quarter sales up 40%+"),
       ("sales_streak", "(3.5, inf]", "4+ quarters in a row of sales +15%"),
       ("roe", "(20.0, 30.0]", "ROE 20-30%"),
       ("vol60", "Q5 high", "Most volatile fifth"),
       ("value_cr", "(0.0, 1.0]", "Tiny: under Rs 1 Cr traded a day")]
COLS = ["hit % discover", "hit % check", "median 12m % discover", "median 12m % check",
        "fell 30%+ % discover", "fell 30%+ % check"]
CSS = """
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--line:#e4e3de;--card:#fff;--up:#1f7a4d;--dn:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--fg:#ecebe6;--mut:#9a9993;--line:#2c2c2a;--card:#1d1d1c;--up:#4cc38a;--dn:#f07167}}
body{background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:24px 16px}
main{max-width:1050px;margin:auto} h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:32px 0 8px}
.muted{color:var(--mut)} .tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:6px;margin:8px 0}
table{border-collapse:collapse;width:100%} th,td{text-align:right;padding:6px 10px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left} th{font-size:12px;color:var(--mut);font-weight:600}
td.up{color:var(--up);font-weight:600} td.dn{color:var(--dn)} tr.base td{font-weight:600}
details{margin:6px 0} summary{cursor:pointer} li{margin:2px 0} a{color:inherit}
"""


def _f1(x):
    return "–" if pd.isna(x) else f"{x:.1f}"


def render_report():
    lt = pd.read_csv(OUT / "lift_table.csv", index_col=[0, 1])
    cs = pd.read_csv(OUT / "canslim_check.csv")
    imp = pd.read_csv(OUT / "importance.csv", index_col=0).iloc[:, 0]
    dec = {p: pd.read_csv(OUT / f"deciles_{p}.csv", index_col=0) for p in ("discover", "check")}
    mb = pd.read_csv(OUT / "model_book.csv", parse_dates=["date"])
    base = cs[cs.group == "all stocks"].set_index("period")
    hit_base = {"hit % discover": base.at["discover", "hit %"], "hit % check": base.at["check", "hit %"]}

    def cell(v, col):
        if pd.isna(v):
            return "<td>–</td>"
        b = hit_base.get(col)
        cls = "" if b is None else (" class=up" if v >= b * 1.25 else " class=dn" if v <= b * 0.8 else "")
        return f"<td{cls}>{v:.1f}</td>"

    def row(label, r, n):
        n_txt = "–" if pd.isna(n) else f"{int(n):,}"
        return f"<tr><td>{H.escape(label)}</td>" + "".join(cell(r[c], c) for c in COLS) + f"<td>{n_txt}</td></tr>"

    head = ("<tr><th></th><th colspan=2>Doubled within 12m (%)</th><th colspan=2>Median 12m return (%)</th>"
            "<th colspan=2>Fell 30%+ at some point (%)</th><th>Stock-weeks</th></tr>"
            "<tr><th></th>" + "<th>2016-21</th><th>2023-25</th>" * 3 + "<th>2016-21</th></tr>")
    flat = {f"{m} {p}": base.at[p, m] for m in ("hit %", "median 12m %", "fell 30%+ %") for p in ("discover", "check")}
    base_row = ("<tr class=base><td>All stocks (base rate)</td>" + "".join(f"<td>{flat[c]:.1f}</td>" for c in COLS)
                + f"<td>{int(base.at['discover', 'stock-weeks']):,}</td></tr>")
    pc = cs[cs.group != "all stocks"].set_index("period")
    pflat = {f"{m} {p}": pc.at[p, m] for m in ("hit %", "median 12m %", "fell 30%+ %") for p in ("discover", "check")}
    canslim_row = row("Passes the scanner's CAN SLIM filters", pflat, pc.at["discover", "stock-weeks"])
    key_rows = "".join(row(lbl, lt.loc[(f, b)], lt.loc[(f, b)]["n discover"]) for f, b, lbl in KEY if (f, b) in lt.index)
    details = []
    for f in lt.index.get_level_values(0).unique():
        rows_f = "".join(row(str(b), lt.loc[(f, b)], lt.loc[(f, b)]["n discover"]) for b in lt.loc[f].index)
        details.append(f"<details><summary>{H.escape(LABELS.get(f, f))}</summary>"
                       f"<div class=tw><table>{head}{rows_f}</table></div></details>")

    def dec_tbl(t):
        return ("<div class=tw><table><tr><th>Score decile (10 = model's favourites)</th><th>Doubled %</th>"
                "<th>Median 12m %</th><th>Fell 30%+ %</th></tr>" + "".join(
                    f"<tr><td>{i}</td><td>{r['hit %']:.1f}</td><td>{r['median 12m %']:.1f}</td><td>{r['fell 30%+ %']:.1f}</td></tr>"
                    for i, r in t.iterrows()) + "</table></div>")
    imp_html = "".join(f"<li>{H.escape(LABELS.get(k, k))} <span class=muted>({v:.3f})</span></li>"
                       for k, v in imp.head(8).items())
    recent = mb[mb.date >= CHECK[0]].sort_values("max_gain", ascending=False).head(30)
    mb_rows = "".join(
        f"<tr><td>{r.sym}</td><td>{r.date:%d %b %Y}</td><td>+{r.max_gain * 100:.0f}%</td><td>{_f1(r.ret6 * 100)}</td>"
        f"<td>{_f1(r.rs)}</td><td>{'yes' if r.trend == 1 else 'no'}</td><td>{_f1(r.sales_yoy)}</td><td>{_f1(r.np_yoy)}</td>"
        f"<td>{_f1(r.opm_chg)}</td><td>{_f1(r.roe)}</td><td>{_f1(r.value_cr)}</td></tr>" for r in recent.itertuples())
    top20 = {}
    for line in (OUT.parent / "winners_run.log").read_text(encoding="utf-8").splitlines() \
            if (OUT.parent / "winners_run.log").exists() else []:
        if line.startswith("=== discover") or line.startswith("=== check"):
            top20[line.split()[1]] = line.split("top-20 per week")[-1].strip()
    page = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Big-winner study</title><style>{CSS}</style></head><body><main>
<p class=muted><a href="latest.html">&larr; Daily scan</a></p>
<h1>Big-winner study: what came before NSE stocks doubled</h1>
<p class=muted>For every stock and every week: did the price at least double within the next 12 months?
Each signal is measured on 2016-2021, then checked on 2023-2025 (2022 is left out so the two don't overlap).
Universe: price &ge; Rs 10, &ge; Rs 0.5 Cr traded a day, 1 year of history, earnings data.
Green = at least 25% above the base rate; red = at least 20% below.</p>
<p class=muted><b>Caveat:</b> price data covers only stocks still listed today. Companies that collapsed and delisted are
missing, so every number here is flattered; compare rows with each other, not with zero.</p>

<h2>Main result</h2><div class=tw><table>{head}{base_row}{canslim_row}{key_rows}</table></div>
<ul>
<li><b>Price strength is the most reliable sign.</b> Stocks already up 100%+ in six months doubled again about twice as often as average, in both periods.</li>
<li><b>Earnings help, but only two signals held up in both periods:</b> operating margin up 6+ points, and profit up 50%+ in each of the last two quarters.
These drive the earnings monitor in the daily report.</li>
<li><b>Fast sales growth and long growth streaks were a trap in 2016-21</b> (negative median return, more crashes) and only worked in 2023-25.</li>
<li><b>"Doubling" partly just measures volatility:</b> tiny and very volatile stocks double more often, and crash more often too.</li>
</ul>

<h2>Can a model learn to spot doublers?</h2>
<p>A gradient-boosting model (scikit-learn) was trained on 2016-21 only, then scored on 2023-25. Its weekly top-20 picks
doubled <b>{top20.get('discover', '–')}</b> of the time on the years it learned from, but only <b>{top20.get('check', '–')}</b>
on the unseen years (base rate {base.at['check', 'hit %']:.1f}%), about the same as the CAN SLIM filters, and its favourites
had the highest crash rate. It is not used by the daily scan.</p>
<p class=muted>What it leaned on most (drop in accuracy when that input is shuffled):</p><ul>{imp_html}</ul>
<details><summary>Model results by score decile, 2023-25 (unseen)</summary>{dec_tbl(dec['check'])}</details>
<details><summary>Model results by score decile, 2016-21 (training years)</summary>{dec_tbl(dec['discover'])}</details>

<h2>Model book: biggest runs that started in 2023-25</h2>
<p class=muted>What each stock looked like in the first week of its doubling run. {len(mb):,} runs by
{mb.sym.nunique():,} stocks in all periods (data/research/winners/model_book.csv).</p>
<div class=tw><table><tr><th>Stock</th><th>Run began</th><th>Best gain in 12m</th><th>6-mo return %</th><th>RS</th><th>Uptrend</th>
<th>Sales growth %</th><th>Profit growth %</th><th>Margin change pts</th><th>ROE %</th><th>Rs Cr/day</th></tr>{mb_rows}</table></div>

<h2>Every signal, bucket by bucket</h2>{''.join(details)}
<footer class=muted style="margin-top:32px;font-size:12px">Code: canslim/winners.py, canslim/winners_report.py &middot;
data: data/research/winners/ &middot; generated {pd.Timestamp.now():%Y-%m-%d %H:%M}. Research only, not investment advice.</footer>
</main></body></html>"""
    f = ROOT / "data" / "reports" / "winners_study.html"
    f.write_text(page, encoding="utf-8")
    return f


if __name__ == "__main__":
    print(render_report())
