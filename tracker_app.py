"""CAN SLIM tracker -- local app over data/canslim.db.

Pages: Today (lists + market), Other frameworks (7 other methods), Sectors (sector radar), Insights (research findings, data/research/insights/*.md), Holdings (traffic light, add / log / sell), Stock (history of any symbol),
Journal (every decision, and whether overriding the rule helped).
Research only. Nothing here places orders.

usage: run_app.bat   (or: python -m streamlit run tracker_app.py)
"""
import json
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from canslim import db, holdings, stockchart

st.set_page_config(page_title="CAN SLIM tracker", layout="wide")
LIGHT = {"GREEN": "🟢", "AMBER": "🟠", "RED": "🔴", "GREY": "⚪"}


def con():
    return db.connect()


def q(sql, params=()):
    c = con()
    try:
        return pd.read_sql_query(sql, c, params=list(params))
    finally:
        c.close()


def exec_(sql, params=()):
    c = con()
    try:
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def pct(x):
    return "" if x is None or pd.isna(x) else f"{x:+.1%}"


# ------------------------------------------------------------------ chart panel (click any stock)
DARK = getattr(getattr(st.context, "theme", None), "type", "light") == "dark"
INK, EMA20, EMA200 = ("#c3c2b7", "#d95926", "#3987e5") if DARK else ("#52514e", "#eb6834", "#2a78d6")


@st.cache_data(show_spinner=False)
def price_ema(sym):
    return stockchart.series(sym)


@st.cache_data(show_spinner=False, ttl=3600)
def known_symbols():
    return stockchart.universe()


def _open_chart(sym):
    st.session_state.chart = sym


def table(df, key, sym="symbol", **kw):
    """st.dataframe; if it has a symbol column, clicking a row opens that stock's chart panel."""
    if sym not in df.columns or df.empty:
        return st.dataframe(df, **kw)
    syms = df[sym].tolist()

    def picked():                                    # any cell of the row; positions refer to df, not the sorted view
        cells = st.session_state[key].selection.cells
        if cells:
            _open_chart(syms[cells[0][0]])
    return st.dataframe(df, key=key, on_select=picked, selection_mode="single-cell", **kw)


def chips(syms, key, label="Chart"):
    """Clickable symbols for stocks named in text."""
    syms = list(dict.fromkeys(s for s in syms if s))
    if not syms:
        return
    st.pills(label, syms, key=key, on_change=lambda: st.session_state[key] and _open_chart(st.session_state[key]))


# TradingView's open-source chart library: wheel zooms, drag scrolls, the price axis refits to what is visible.
TV_JS = "https://unpkg.com/lightweight-charts@5.0.8/dist/lightweight-charts.standalone.production.js"
TV_HTML = """<style>
 body{margin:0;font:12px/1.4 "Source Sans Pro",system-ui,sans-serif;color:__FG__;overflow:hidden}
 .bar{display:flex;gap:4px;align-items:center;margin:0 0 4px;flex-wrap:wrap}
 .bar button{font:inherit;padding:2px 10px;border:1px solid __LINE__;border-radius:6px;background:none;color:__FG__;cursor:pointer}
 .bar button.on{border-color:__EMA200__;color:__EMA200__} .bar label{color:__MUT__;cursor:pointer;margin-right:10px;white-space:nowrap}
 .bar .sp{margin-left:auto}
 .lg{display:flex;flex-wrap:wrap;gap:2px 12px;color:__MUT__;min-height:34px;align-content:flex-start}
 .lg i{display:inline-block;width:12px;height:2px;vertical-align:middle;margin-right:4px} .lg b{color:__FG__;font-weight:600}
 .lg .ev{color:__FG__} #c{height:430px} .hint{color:__MUT__;font-size:11px;margin-top:2px}
</style>
<div class=bar><button data-y=1>1y</button><button data-y=2>2y</button><button data-y=5>5y</button><button data-y=0>All</button>
<span class=sp></span><label style="margin-right:0"><input type=checkbox id=log> Log</label></div>
<div class=bar><label><input type=checkbox id=sig checked> Signals</label><label><input type=checkbox id=res checked> Results</label>
<label><input type=checkbox id=rsl checked> RS line</label><label><input type=checkbox id=vol checked> Volume</label>
<label><input type=checkbox id=bas checked> Base</label></div>
<div class=lg id=lg></div><div id=c></div>
<div class=hint>Scroll to zoom · drag to move through time · hover a marker for details</div>
<script src="__TVJS__"></script>
<script>
const D=__DATA__, C=__COLORS__, N=D.t.length, last=D.t[N-1], H=430, L=LightweightCharts, el=document.getElementById('c'), $=id=>document.getElementById(id);
const pos={}; D.t.forEach((t,i)=>pos[t]=i);
const ev={}, add=(t,s)=>(ev[t]=ev[t]||[]).push(s);
D.signals.forEach(m=>add(m.time,(m.buy?'▲ ':'▼ ')+m.text)); D.results.forEach(m=>add(m.time,'Result: profit '+m.text.replace(/^E ?/,'')));
D.rsmarks.forEach(m=>add(m.time,'RS line leads price'));
let ch=null, cur=5, moved=false;
const day=t=>typeof t==='string'?t:t.year?`${t.year}-${String(t.month).padStart(2,'0')}-${String(t.day).padStart(2,'0')}`:new Date(t*1000).toISOString().slice(0,10);
const f=v=>v==null?'–':v.toLocaleString('en-IN',{maximumFractionDigits:2});
const fv=v=>v==null?'–':v>=1e7?(v/1e7).toFixed(2)+' Cr':v>=1e5?(v/1e5).toFixed(1)+' L':v.toLocaleString('en-IN');
function legend(p){const t=p&&p.time?day(p.time):null,i=t&&pos[t]!=null?pos[t]:N-1,it=(n,col,v)=>`<span><i style="background:${col}"></i>${n} <b>${v}</b></span>`;
 $('lg').innerHTML=(t?'<span>'+t+'</span>':'')+it('Price',C.ink,f(D.c[i]))+it('20 EMA',C.e20,f(D.e20[i]))+it('200 EMA',C.e200,f(D.e200[i]))
  +($('rsl').checked?it('RS line',C.rs,f(D.rs[i])):'')+($('vol').checked?it('Vol',C.mut,fv(D.v[i])+(D.v50[i]?' · '+(D.v[i]/D.v50[i]).toFixed(1)+'x avg':'')):'')
  +(t&&ev[t]?'<span class=ev>'+ev[t].join(' · ')+'</span>':'')}
function build(){
 const lr=ch?ch.timeScale().getVisibleLogicalRange():null; if(ch)ch.remove();
 const rsOn=$('rsl').checked, volOn=$('vol').checked;
 ch=L.createChart(el,{width:el.clientWidth,height:H,layout:{background:{type:'solid',color:'rgba(0,0,0,0)'},textColor:C.mut,fontSize:11,
  panes:{separatorColor:C.grid,separatorHoverColor:C.grid}},grid:{vertLines:{visible:false},horzLines:{color:C.grid}},
  rightPriceScale:{borderVisible:false},timeScale:{borderVisible:false,minBarSpacing:0.05},crosshair:{mode:0}});
 const line=(k,o,pane)=>{const s=ch.addSeries(L.LineSeries,Object.assign({priceLineVisible:false,lastValueVisible:false,crosshairMarkerRadius:3},o),pane);
  s.setData(D.t.map((t,i)=>D[k][i]==null?{time:t}:{time:t,value:D[k][i]}));return s};
 const price=line('c',{color:C.ink,lineWidth:2},0); line('e20',{color:C.e20,lineWidth:1},0); line('e200',{color:C.e200,lineWidth:2},0);
 if($('log').checked)price.priceScale().applyOptions({mode:1});
 const M=[].concat($('sig').checked?D.signals.map(m=>({time:m.time,position:m.position,shape:m.shape,color:m.buy?C.buy:C.sell,
   size:m.text.startsWith('BT')?.7:1,text:m.text.startsWith('BT')?undefined:m.text.split(' ')[0]})):[],
  $('res').checked?D.results.map(m=>({time:m.time,position:'aboveBar',shape:'circle',size:.5,color:m.good?C.good:C.mut})):[])
  .sort((a,b)=>a.time<b.time?-1:a.time>b.time?1:0);
 if(M.length)L.createSeriesMarkers(price,M);
 D.lines.forEach(x=>{if(x.kind==='you'||$('bas').checked)price.createPriceLine({price:x.price,title:x.kind==='you'?'Your buy':x.kind==='pivot'?'Pivot':'Zone +5%',
  lineWidth:1,axisLabelVisible:true,color:x.kind==='you'?C.you:C.ink,lineStyle:x.kind==='zone'?1:x.kind==='pivot'?2:0})});
 let pane=1;
 if(rsOn){const r=line('rs',{color:C.rs,lineWidth:1,crosshairMarkerVisible:false},pane);r.priceScale().applyOptions({visible:false});
  if(D.rsmarks.length)L.createSeriesMarkers(r,D.rsmarks.map(m=>({time:m.time,position:'belowBar',shape:'circle',size:.6,color:C.rs})));pane++}
 if(volOn){const v=ch.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceLineVisible:false,lastValueVisible:false},pane);
  v.setData(D.t.map((t,i)=>({time:t,value:D.v[i],color:D.heavy[i]?(D.up[i]?C.buy:C.sell):C.volbar})));
  line('v50',{color:C.mut,lineWidth:1,crosshairMarkerVisible:false,priceFormat:{type:'volume'}},pane)}
 const sf=rsOn&&volOn?[6,1.6,2.2]:rsOn?[7,2]:volOn?[7,2.2]:[1];
 ch.panes().forEach((p,i)=>p.setStretchFactor(sf[i]));
 price.priceScale().applyOptions({scaleMargins:{top:.06,bottom:.04}});
 ch.subscribeCrosshairMove(legend);legend();
 if(lr)ch.timeScale().setVisibleLogicalRange(lr);else range(cur)}
function range(y){cur=y;moved=false;document.querySelectorAll('.bar button').forEach(b=>b.classList.toggle('on',+b.dataset.y===y));
 const d=new Date(last);d.setFullYear(d.getFullYear()-y);const from=d.toISOString().slice(0,10);
 if(!y||D.t[0]>from){ch.timeScale().fitContent();return} ch.timeScale().setVisibleRange({from,to:last})}
['wheel','mousedown','touchstart'].forEach(e=>el.addEventListener(e,()=>moved=true));
document.querySelectorAll('.bar button').forEach(b=>b.onclick=()=>range(+b.dataset.y));
['sig','res','rsl','vol','bas','log'].forEach(id=>$(id).onchange=build);
build();let rw=el.clientWidth;new ResizeObserver(()=>{if(el.clientWidth!==rw){rw=el.clientWidth;ch.resize(rw,H);if(!moved)range(cur)}}).observe(el);
</script>"""


def tv_chart(L):
    fg, mut, line, grid, volbar = (
        ("#fafafa", "#a3a8b8", "rgba(250,250,250,.2)", "rgba(250,250,250,.08)", "rgba(195,194,183,.28)") if DARK else
        ("#31333f", "#6b6e7b", "rgba(49,51,63,.2)", "rgba(49,51,63,.08)", "rgba(82,81,78,.22)"))
    colors = {"ink": INK, "e20": EMA20, "e200": EMA200, "mut": mut, "grid": grid, "volbar": volbar,
              "buy": "#199e70" if DARK else "#1baf7a", "sell": "#e66767" if DARK else "#e34948",
              "good": "#9085e9" if DARK else "#6250d6", "rs": "#d55181" if DARK else "#e87ba4",
              "you": "#c98500" if DARK else "#eda100"}
    out = TV_HTML
    for k, v in {"__DATA__": json.dumps(L, separators=(",", ":")), "__COLORS__": json.dumps(colors),
                 "__TVJS__": TV_JS, "__FG__": fg, "__MUT__": mut, "__LINE__": line, "__EMA200__": EMA200}.items():
        out = out.replace(k, v)
    components.html(out, height=560)


@st.cache_data(show_spinner=False)
def chart_layers(sym, scan):           # scan = latest scan date, so a new scan refreshes the cache
    return stockchart.layers(sym, q("SELECT date, symbol FROM picks WHERE list='canslim'"),
                             q("SELECT * FROM paper_trades"), q("SELECT * FROM holdings"))


def chart_panel():
    sym = st.session_state.get("chart")
    if not sym:
        return
    bg, line = ("#0e1117", "rgba(250,250,250,.16)") if DARK else ("#ffffff", "rgba(49,51,63,.16)")
    st.html(f"""<style>
      .st-key-chartpanel {{position: fixed; top: 3.75rem; right: 1rem; width: min(560px, calc(100vw - 2rem));
        max-height: calc(100vh - 4.75rem); overflow-y: auto; z-index: 999990; background: {bg};
        border: 1px solid {line}; border-radius: 10px; padding: 10px 14px 6px; box-shadow: 0 8px 28px rgba(0,0,0,.22);}}
      @media (min-width: 1300px) {{ [data-testid="stMainBlockContainer"] {{padding-right: 600px !important;}} }}
    </style>""")
    with st.container(key="chartpanel"):
        h, x = st.columns([6, 1], vertical_alignment="center")
        h.markdown(f"**{sym}** · price, 20-day and 200-day EMA")
        x.button("✕", key="chart_close", help="Close the chart", on_click=_open_chart, args=(None,))
        df = price_ema(sym)
        if df.empty:
            st.warning(f"No price file for {sym} in data/prices.")
            return
        L = chart_layers(sym, dates[0] if dates else "")
        tv_chart(L)
        yrs = 5
        d = df.loc[df.index[-1] - pd.DateOffset(years=yrs):]
        last, start = df.iloc[-1], d.close.iloc[0]
        a, b, c_ = st.columns(3)
        short = d.index[0] > df.index[-1] - pd.DateOffset(years=yrs) + pd.Timedelta(days=10)
        a.metric("Close", f"{last.close:,.2f}", f"{(last.close / start - 1):+.0%} " +
                 (f"since {d.index[0]:%Y}" if short else f"in {yrs}y"))
        b.metric("vs 20 EMA", f"{last.close / last.ema20 - 1:+.1%}")
        c_.metric("vs 200 EMA", f"{last.close / last.ema200 - 1:+.1%}")
        if L.get("base"):
            st.markdown(f"**Base:** {L['base']}")
        st.caption(f"Last close {df.index[-1]:%d %b %Y}. Adjusted for splits and bonuses; averages use the full "
                   f"history from {df.index[0]:%Y}. [Screener](https://www.screener.in/company/{sym}/)")
        st.caption("**Signals** ▲ buy ▼ sell — BT: backtest of the current rules 2016–26 · List / Off list: joined or "
                   "left the live CAN SLIM list · Paper: paper portfolio · You: your holdings (line = your buy price). "
                   "**Results** E = result day, net profit vs a year ago (purple = +25% or better). **RS line** = price ÷ "
                   "Nifty 500; 'RS leads' = RS line at a 52-week high while the price is still 5%+ below its own high "
                   "(book: often comes before a breakout). **Volume** coloured on days 40%+ above the 50-day average "
                   "(green up, red down); line = 50-day average. **Base** = pivot (dashed) and top of the buy zone (dotted).")


dates = q("SELECT DISTINCT date FROM snapshot ORDER BY date DESC").date.tolist()
page = st.sidebar.radio("Page", ["Today", "Other frameworks", "Sectors", "Insights", "Holdings", "Research",
                                 "Paper portfolio", "Watching", "Stock", "Journal"])
st.sidebar.caption(f"Database: {db.DB}\n\nLatest scan: {dates[0] if dates else 'none'}")
st.sidebar.caption("Research only. No orders are placed.")
st.sidebar.divider()
st.sidebar.markdown("**Created by Amrendra Kumar**")
st.sidebar.markdown("**Srijon Roy**")
st.sidebar.caption("Click any stock (a table row or a symbol chip) to see its chart on the right.")
chart_panel()

# ------------------------------------------------------------------ Today
if page == "Today":
    if not dates:
        st.warning("No scans in the database yet. Run the daily scan (run_daily.bat).")
        st.stop()
    d = st.selectbox("Scan date", dates)
    mk = q("SELECT state FROM market WHERE date=?", [d])
    state = mk.state.iloc[0] if len(mk) else "?"
    if state in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE"):
        st.success(f"Market: {state} — new buys allowed")
    else:
        st.error(f"Market: {state} — the system makes NO new buys. Lists are for watching.")
    prev = q("SELECT MAX(date) d FROM picks WHERE list='canslim' AND date<?", [d]).d.iloc[0]
    cs = q("SELECT rank, symbol, close, rs, industry FROM picks WHERE date=? AND list='canslim' ORDER BY rank", [d])
    if prev:
        before = set(q("SELECT symbol FROM picks WHERE date=? AND list='canslim'", [prev]).symbol)
        cs["new?"] = ["" if s in before else "NEW" for s in cs.symbol]
        dropped = sorted(before - set(cs.symbol))
    from canslim.autobrief import brief_info
    bi = {s: brief_info(s) for s in cs.symbol}
    cs["brief"] = [f"{bi[s][1]}/5 ({bi[s][2]}/24) {bi[s][0]}" if bi[s][1] else "—" for s in cs.symbol]
    st.subheader(f"CAN SLIM — {len(cs)} pass every rule")
    st.caption("brief = suggested conviction from the research brief (Research page), checklist total, brief date. "
               "Briefs for new names are written automatically after the evening scan.")
    table(cs, "t_cs", hide_index=True, width="stretch",
                 column_config={"rs": st.column_config.NumberColumn(format="%.0f")})
    if prev and dropped:
        st.caption(f"Dropped since {prev}: " + ", ".join(dropped))
        chips(dropped, "c_dropped", "Chart a dropped stock")
    a, b = st.columns(2)
    with a:
        st.subheader("Emerging / turnaround (higher risk)")
        table(q("SELECT rank, symbol, close, rs, industry, note FROM picks WHERE date=? AND list='emerging' "
                "ORDER BY rank", [d]), "t_em", hide_index=True, width="stretch")
    with b:
        st.subheader("Earnings monitor (price confirming)")
        table(q("SELECT symbol, close, rs, industry, note FROM picks WHERE date=? AND list='earnings' "
                "ORDER BY rs DESC", [d]), "t_earn", hide_index=True, width="stretch")
    st.caption("Full report with bases and buy points: data/reports/latest.html")

# ------------------------------------------------------------------ Holdings
elif page == "Holdings":
    st.title("Holdings")
    with st.expander("How the light works", expanded=False):
        st.markdown(holdings.__doc__)
    c = con()
    stt = holdings.status(c)
    H = holdings.open_holdings(c)
    c.close()
    if H.empty:
        st.info("No open holdings. Add one below when you buy.")
    else:
        v = stt.merge(H[["id", "buy_date", "qty", "buy_price"]], left_on="holding_id", right_on="id")
        v["light"] = v.light.map(lambda x: f"{LIGHT.get(x, '')} {x}")
        v["value"] = v.qty * v.close
        v["P&L"] = v.qty * (v.close - v.buy_price)
        cv = q("SELECT symbol, score FROM conviction WHERE id IN (SELECT MAX(id) FROM conviction GROUP BY symbol)")
        v["conviction"] = v.symbol.map(dict(zip(cv.symbol, cv.score)))
        table(v[["light", "symbol", "conviction", "buy_date", "qty", "buy_price", "close", "gain", "from_peak",
                        "sys_rank", "rs", "value", "P&L", "reasons"]], "t_hold",
                     hide_index=True, width="stretch",
                     column_config={"gain": st.column_config.NumberColumn(format="percent"),
                                    "from_peak": st.column_config.NumberColumn(format="percent"),
                                    "rs": st.column_config.NumberColumn(format="%.0f"),
                                    "value": st.column_config.NumberColumn(format="%.0f"),
                                    "P&L": st.column_config.NumberColumn(format="%.0f")})
        st.caption(f"Status as of {stt.date.iloc[0] if len(stt) else '?'} (latest scan). "
                   "The daily run also stores each day's light, so the history is kept.")

        st.subheader("Log a decision / sell")
        names = {f"{r.symbol} (bought {r.buy_date} @ {r.buy_price:g})": r for r in H.itertuples()}
        pick = st.selectbox("Holding", list(names))
        h = names[pick]
        cur = stt[stt.holding_id == h.id].iloc[0] if len(stt) else None
        st.markdown(f"**Plan at entry** — why: {h.thesis or '—'}  \n**Wrong if:** {h.wrong_if or '—'}")
        if cur is not None:
            st.markdown(f"**Today:** {LIGHT.get(cur.light, '')} {cur.light} — {cur.reasons}")
        with st.form("decide", clear_on_submit=True):
            action = st.radio("Action", ["HOLD", "SELL", "NOTE"], horizontal=True,
                              help="HOLD on a RED light is an override: say why. SELL closes the position.")
            reason = st.text_area("Reason (required) — what do you see that the rules don't?")
            col1, col2 = st.columns(2)
            sell_price = col1.number_input("Sell price (for SELL)", min_value=0.0,
                                           value=float(cur.close) if cur is not None and cur.close else 0.0)
            sell_date = col2.date_input("Date", value=date.today())
            if st.form_submit_button("Save"):
                if not reason.strip():
                    st.error("Write a reason. The log is only useful if every decision has one.")
                else:
                    exec_("INSERT INTO decisions(date, symbol, holding_id, light, action, reason, price) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (str(sell_date), h.symbol, int(h.id), cur.light if cur is not None else None,
                           action, reason.strip(), float(cur.close) if action != "SELL" else sell_price))
                    if action == "SELL":
                        exec_("UPDATE holdings SET sell_date=?, sell_price=?, sell_reason=? WHERE id=?",
                              (str(sell_date), sell_price, reason.strip(), int(h.id)))
                    st.success("Saved.")
                    st.rerun()
        hist = q("SELECT date, light, reasons, close, sys_rank FROM holding_status WHERE holding_id=? "
                 "ORDER BY date DESC", [int(h.id)])
        if len(hist):
            st.caption("Light history")
            st.dataframe(hist, hide_index=True, width="stretch")

    st.subheader("Add a holding")
    syms = q("SELECT DISTINCT symbol FROM snapshot ORDER BY symbol").symbol.tolist()
    with st.form("add", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        sym = c1.text_input("NSE symbol", placeholder="e.g. CUPID").strip().upper()
        bd = c2.date_input("Buy date", value=date.today())
        qty = c3.number_input("Quantity", min_value=0.0, step=1.0)
        bp = c4.number_input("Buy price", min_value=0.0)
        thesis = st.text_area("Why I'm buying (required)", placeholder="RS 97, profit +140%, broke out of a cup at 852")
        wrong = st.text_area("I'm wrong if (required)", placeholder="closes below the 200-day, or next quarter's profit growth halves")
        if st.form_submit_button("Add holding"):
            if not (sym and qty > 0 and bp > 0 and thesis.strip() and wrong.strip()):
                st.error("Fill in symbol, quantity, price, and both plan fields.")
            elif holdings.closes(sym).empty:
                st.error(f"No price file for {sym} in data/prices. Check the NSE symbol.")
            else:
                hid = exec_("INSERT INTO holdings(symbol, buy_date, qty, buy_price, thesis, wrong_if) VALUES(?,?,?,?,?,?)",
                            (sym, str(bd), qty, bp, thesis.strip(), wrong.strip()))
                exec_("INSERT INTO decisions(date, symbol, holding_id, light, action, reason, price) VALUES(?,?,?,?,?,?,?)",
                      (str(bd), sym, hid, None, "BUY", thesis.strip(), bp))
                if sym not in syms:
                    st.warning(f"{sym} is not in the system's universe, so its light will be GREY.")
                st.success(f"Added {sym}.")
                st.rerun()

    closed = q("SELECT symbol, buy_date, buy_price, sell_date, sell_price, qty, sell_reason FROM holdings "
               "WHERE sell_date IS NOT NULL ORDER BY sell_date DESC")
    if len(closed):
        closed["return"] = closed.sell_price / closed.buy_price - 1
        closed["P&L"] = closed.qty * (closed.sell_price - closed.buy_price)
        st.subheader("Closed")
        table(closed, "t_closed", hide_index=True, width="stretch",
                     column_config={"return": st.column_config.NumberColumn(format="percent")})

# ------------------------------------------------------------------ Insights
elif page == "Insights":
    from pathlib import Path
    st.title("Market insights")
    st.caption("What the research on NSE history found. Newest first. Each finding comes from a test in the "
               "project (script named under Source); 'Adopted' means the rule is now part of the system.")
    folder = Path(__file__).resolve().parent / "data" / "research" / "insights"
    items = []
    for f in sorted(folder.glob("*.md"), reverse=True):
        text = f.read_text(encoding="utf-8")
        meta, body = {}, text
        if text.startswith("---"):
            head, _, body = text[3:].partition("\n---")
            for line in head.strip().splitlines():
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        meta["body"] = body.strip()
        meta["tags"] = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
        items.append(meta)
    if not items:
        st.info("No findings yet.")
        st.stop()
    badge = {"Adopted": "🟢 Adopted", "Rejected": "🔴 Rejected", "Not adopted": "🟠 Not adopted",
             "Research only": "🔵 Research only"}
    a, b, c_ = st.columns([2, 2, 3])
    tags = a.multiselect("Topic", sorted({t for it in items for t in it["tags"]}))
    stats = b.multiselect("Status", sorted({it.get("status", "") for it in items}))
    find = c_.text_input("Search")
    shown = [it for it in items
             if (not tags or set(tags) & set(it["tags"])) and (not stats or it.get("status") in stats)
             and (not find or find.lower() in (it.get("title", "") + it["body"]).lower())]
    st.subheader("Key takeaways")
    for it in shown:
        st.markdown(f"- **{it.get('title', '')}** — {it.get('takeaway', '')}")
    st.divider()
    for it in shown:
        with st.expander(f"{it.get('date', '')} · {it.get('title', '')}  ·  "
                         f"{badge.get(it.get('status', ''), it.get('status', ''))}"):
            st.markdown(f"**Takeaway:** {it.get('takeaway', '')}")
            st.markdown(it["body"])
            chips(stockchart.mentioned(it["body"], known_symbols()), f"c_ins_{it.get('date', '')}_{it.get('title', '')}")
            st.caption(f"Topics: {', '.join(it['tags'])}  ·  Source: {it.get('source', '')}")

# ------------------------------------------------------------------ Other frameworks
elif page == "Other frameworks":
    import json
    from pathlib import Path
    from canslim import frameworks as fw
    st.title("Other frameworks")
    st.caption("Seven other ways of picking stocks, run every day next to CAN SLIM (canslim/frameworks.py). Each list is "
               "separate; nothing here changes the CAN SLIM picks. Rules are taken from the original sources and were "
               "fixed before testing. Research only.")
    fdates = q("SELECT DISTINCT date FROM picks WHERE list LIKE 'fw_%' ORDER BY date DESC").date.tolist()
    if not fdates:
        st.info("No framework lists yet. They are made by the daily scan (run_daily.bat).")
        st.stop()
    d = st.selectbox("Scan date", fdates)
    sj = Path(__file__).resolve().parent / "data" / "tune" / "frameworks" / "summary.json"
    summ = json.loads(sj.read_text()) if sj.exists() else None
    if summ:
        bt = pd.DataFrame(summ["results"]).set_index("framework")
        st.subheader("Backtest 2016–2026 (weekly, 0.3% cost per side)")
        cols = [c for c in ["CAGR %", "Sharpe", "maxDD %", "avg invested %", "CAGR 2016-19", "CAGR 2020-22",
                            "CAGR 2023-26", "corr with CAN SLIM"] if c in bt]
        st.dataframe(bt[cols], use_container_width=True)
        bad = summ.get("lookahead_bad", {})
        st.caption(f"Backtest run {summ.get('run')}. Look-ahead check on {summ.get('lookahead_date')}: "
                   + ("passed — no score changed when future data was removed."
                      if bad and not any(bad.values()) else f"stocks whose score changed: {bad}"))
    with st.expander("Data notes (read before trusting old numbers)"):
        st.markdown(fw.__doc__.split("Data notes (also shown in the app):")[-1])
    tabs = st.tabs([fw.RULES[k][0].split(" (")[0] for k in fw.RULES])
    for tab, (key, (title, rule)) in zip(tabs, fw.RULES.items()):
        with tab:
            st.markdown(f"**{title}**")
            st.markdown(rule)
            if summ and title in bt.index:
                r = bt.loc[title]
                st.caption(f"Backtest: {r['CAGR %']}%/yr, Sharpe {r['Sharpe']}, worst drop {r['maxDD %']}%, "
                           f"invested {r.get('avg invested %', '')}% of the time.")
            lst = q("SELECT rank, symbol, close, note FROM picks WHERE date=? AND list=? ORDER BY rank", [d, f"fw_{key}"])
            if not len(lst):
                st.info("No stock passes these rules today.")
                continue
            inp = pd.DataFrame([json.loads(n) if n else {} for n in lst.note])
            view = pd.concat([lst.drop(columns="note"), inp], axis=1)
            view["Check on Screener"] = "https://www.screener.in/company/" + view.symbol + "/"
            table(view, f"t_fw_{key}", use_container_width=True, hide_index=True,
                         column_config={"Check on Screener": st.column_config.LinkColumn(display_text="open")})
            st.caption("Spot-check: open two or three stocks on Screener and compare P/E, ROCE, debt and growth with the "
                       "columns above. Small differences are normal (Screener shows the latest year; some columns here are "
                       "minimums or averages over 10 years).")

# ------------------------------------------------------------------ Sectors
elif page == "Sectors":
    st.title("Sector radar")
    st.caption("Industries (Screener basic industry) with at least 5 liquid stocks, ranked weekly by the average RS of "
               "their stocks; strength 100 = strongest. Tested 2016–26 (canslim/sectortest.py): the top 20% beat the "
               "bottom 20% by about 4% over the next 3 months; a group usually stays in the top 20% for about 2 months "
               "(15% last 6+ months); groups that drop out lagged the market by 1–5% over the next 3–12 months. "
               "Holdings in a group that dropped out get an amber warning.")
    rdates = q("SELECT DISTINCT date FROM sector_radar ORDER BY date DESC").date.tolist()
    if not rdates:
        st.info("No radar yet. It is made by the daily scan (run_daily.bat).")
        st.stop()
    d = st.selectbox("Scan date", rdates)
    rad = q("SELECT grp AS 'Group', stocks AS 'Stocks', strength AS 'Strength', weeks_top AS 'Weeks in top 20%', "
            "weeks_top_last_year AS 'Top-20% weeks, last year', status AS 'Status', "
            "weeks_since_drop AS 'Weeks since dropped out' FROM sector_radar WHERE date=? ORDER BY strength DESC", [d])
    a, b, c_ = st.columns(3)
    a.metric("Strong now (top 20%)", int((rad.Strength >= 80).sum()))
    b.metric("Dropped out, last 13 weeks", int((rad.Status == "Dropped out").sum()))
    c_.metric("Groups ranked", len(rad))
    show = st.multiselect("Status", ["Leading", "New leader", "Dropped out", "Weak", ""],
                          default=["Leading", "New leader", "Dropped out"])
    st.dataframe(rad[rad.Status.isin(show)], use_container_width=True, hide_index=True)
    g = st.selectbox("Stocks in group", rad.Group.tolist())
    mem = q("SELECT symbol, rs, sys_rank, n_fail FROM snapshot WHERE date=(SELECT MAX(date) FROM snapshot WHERE date<=?) "
            "AND industry=? ORDER BY rs DESC", [d, g])
    table(mem, "t_sector_mem", use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ Research
elif page == "Research":
    import re
    from canslim.docs import COMPANIES
    st.title("Research & conviction")
    st.caption("Briefs are written in Claude Code: type `/brief SYMBOL` there. They land in "
               "data/research/companies/<SYM>/brief.md and show up here. You set the conviction; the brief only suggests.")
    have = sorted(p.parent.name for p in COMPANIES.glob("*/brief.md")) if COMPANIES.exists() else []
    fetched = sorted(p.parent.name for p in COMPANIES.glob("*/facts.md")) if COMPANIES.exists() else []
    if not fetched:
        st.info("No research yet. In Claude Code, type: /brief SKYGOLD")
        st.stop()
    sym = st.selectbox("Company", sorted(set(have) | set(fetched)),
                       format_func=lambda s: s + ("" if s in have else "  (documents only, no brief yet)"))
    base = COMPANIES / sym
    brief = (base / "brief.md").read_text(encoding="utf-8") if (base / "brief.md").exists() else ""
    m = re.search(r"Suggested conviction:\s*(\d)", brief)
    suggested = int(m.group(1)) if m else None
    rows = re.findall(r"^\|\s*(\d{1,2})\s*\|([^|]+)\|\s*([0-2])\s*\|", brief, flags=re.M)
    total = sum(int(r[2]) for r in rows) if rows else None
    bdate = (re.search(r"Brief date:\s*(\S+)", brief) or [None, None])[1]
    a, b, c_ = st.columns(3)
    a.metric("Suggested conviction", f"{suggested}/5" if suggested else "–")
    b.metric("Checklist total", f"{total}/24" if total is not None else "–")
    last = q("SELECT score, date, notes FROM conviction WHERE symbol=? ORDER BY id DESC LIMIT 1", [sym])
    c_.metric("Your conviction", f"{int(last.score.iloc[0])}/5" if len(last) else "not set",
              help=f"set {last.date.iloc[0]}" if len(last) else None)
    chips([sym] + stockchart.mentioned(brief, known_symbols()), f"c_brief_{sym}", "Chart")
    t1, t2, t3 = st.tabs(["Brief", "Facts", "Sources"])
    with t1:
        st.markdown(brief or "_No brief yet. In Claude Code: `/brief " + sym + "`_")
    with t2:
        st.markdown((base / "facts.md").read_text(encoding="utf-8") if (base / "facts.md").exists() else "_none_")
    with t3:
        st.markdown((base / "sources.md").read_text(encoding="utf-8") if (base / "sources.md").exists() else "_none_")
    st.subheader("Set your conviction")
    with st.form("conv", clear_on_submit=True):
        score = st.slider("Conviction (1 = weak, 5 = very strong)", 1, 5, suggested or 3, key=f"conv_{sym}")
        notes = st.text_area("Why (required) — especially where you differ from the brief, and what you saw yourself")
        if st.form_submit_button("Save conviction"):
            if not notes.strip():
                st.error("Write why. Later, the journal compares your conviction with what happened.")
            else:
                exec_("INSERT INTO conviction(symbol, date, score, suggested, checklist_total, brief_date, notes) "
                      "VALUES(?,?,?,?,?,?,?)", (sym, str(date.today()), score, suggested, total, bdate, notes.strip()))
                st.success("Saved.")
                st.rerun()
    hist = q("SELECT date, score, suggested, checklist_total, notes FROM conviction WHERE symbol=? ORDER BY id DESC", [sym])
    if len(hist):
        st.caption("Conviction history")
        st.dataframe(hist, hide_index=True, width="stretch")

# ------------------------------------------------------------------ Paper portfolio
elif page == "Paper portfolio":
    from canslim import paper
    st.title("Paper portfolio")
    st.caption("The system trading its own daily lists from the first stored scan, by the backtested rules: "
               "10 slots, sell when a holding fails a rule or ranks > 30, buy only in a market uptrend, fills at the "
               "next open, 0.3% cost each way. Notional Rs 10 lakh. This is the live, out-of-sample record.")
    if st.button("Rebuild now"):
        st.write(paper.run())
    E = q("SELECT * FROM paper_equity ORDER BY date")
    if E.empty:
        st.info("No paper history yet. It's built by the daily run (or press Rebuild now).")
        st.stop()
    e0, e1 = E.iloc[0], E.iloc[-1]
    a, b, c_, d_ = st.columns(4)
    a.metric("Equity", f"Rs {e1.equity:,.0f}", pct(e1.equity / paper.CAPITAL - 1))
    b.metric("Nifty 500 same period", pct(e1.nifty500 / e0.nifty500 - 1))
    c_.metric("Positions", int(e1.n_pos))
    d_.metric("Market", e1.market)
    st.caption(f"Since {e0.date}.")
    ch = E.set_index("date")[["equity", "nifty500"]]
    ch = ch / ch.iloc[0] * 100
    st.line_chart(ch.rename(columns={"equity": "Paper portfolio", "nifty500": "Nifty 500"}))
    pend = q("SELECT * FROM paper_pending")
    if len(pend):
        st.subheader("Signals for the next open")
        table(pend, "t_pend", hide_index=True, width="stretch")
    T = q("SELECT * FROM paper_trades")
    op = T[T.status == "open"].copy()
    st.subheader(f"Open positions ({len(op)})")
    if len(op):
        snap = q("SELECT symbol, rs, sys_rank, n_fail, failed FROM snapshot WHERE date=?", [e1.date])
        op = op.merge(snap, on="symbol", how="left")
        op["value"] = op.shares * op.exit
        table(op[["symbol", "entry_date", "entry", "exit", "ret", "value", "rs", "sys_rank", "failed", "why"]]
                     .rename(columns={"exit": "close", "ret": "return", "why": "signal"}), "t_open",
                     hide_index=True, width="stretch",
                     column_config={"return": st.column_config.NumberColumn(format="percent"),
                                    "value": st.column_config.NumberColumn(format="%.0f"),
                                    "rs": st.column_config.NumberColumn(format="%.0f")})
    else:
        st.write("None. In cash.")
    cl = T[T.status == "closed"]
    st.subheader(f"Closed trades ({len(cl)})")
    if len(cl):
        a, b = st.columns(2)
        a.metric("Win rate", f"{(cl.ret > 0).mean():.0%}")
        b.metric("Average trade", pct(cl.ret.mean()))
        table(cl[["symbol", "entry_date", "entry", "exit_date", "exit", "ret", "why"]].sort_values(
            "exit_date", ascending=False), "t_cl", hide_index=True, width="stretch",
            column_config={"ret": st.column_config.NumberColumn(format="percent")})

# ------------------------------------------------------------------ Watching
elif page == "Watching":
    st.title("Sold, still watching")
    st.caption("Every stock that left the CAN SLIM list or was sold by the paper portfolio in the last 24 months, "
               "so a later comeback isn't missed. QUALIFIES AGAIN = passes every rule and ranks <= 30 today: the "
               "system would buy it back in an uptrend. Use the Stock page to look closer.")
    W = q("SELECT * FROM watching ORDER BY CASE status WHEN 'QUALIFIES AGAIN' THEN 0 WHEN '1 rule away' THEN 1 "
          "ELSE 2 END, rs DESC")
    if W.empty:
        st.info("Nothing yet.")
    else:
        table(W.drop(columns=["as_of"]), "t_watch", hide_index=True, width="stretch",
                     column_config={"since_left": st.column_config.NumberColumn(format="percent"),
                                    "rs": st.column_config.NumberColumn(format="%.0f")})
        st.caption(f"As of {W.as_of.iloc[0]}.")

# ------------------------------------------------------------------ Stock
elif page == "Stock":
    st.title("Stock lookup")
    sym = st.text_input("NSE symbol", value="CUPID").strip().upper()
    px = holdings.closes(sym)
    if px.empty:
        st.warning("No price file for that symbol.")
        st.stop()
    chips([sym], f"c_stock_{sym}", "Open in the chart panel (signals, base, RS line, volume, results)")
    years = st.slider("Years of chart", 1, 10, 2)
    p = px.loc[px.index[-1] - pd.DateOffset(years=years):]
    ch = pd.DataFrame({"close": p, "50-day": px.rolling(50).mean().reindex(p.index),
                       "200-day": px.rolling(200).mean().reindex(p.index)})
    st.line_chart(ch)
    snap = q("SELECT * FROM snapshot WHERE symbol=? ORDER BY date DESC", [sym])
    if len(snap):
        r = snap.iloc[0]
        a, b, c_, d_ = st.columns(4)
        a.metric("RS", f"{r.rs:.0f}" if pd.notna(r.rs) else "–")
        b.metric("System rank", f"{int(r.sys_rank)}" if pd.notna(r.sys_rank) else "not passing")
        c_.metric("Qtr profit growth", f"{r.np_yoy:.0f}%" if pd.notna(r.np_yoy) else "–")
        d_.metric("ROE", f"{r.roe:.0f}%" if pd.notna(r.roe) else "–")
        st.markdown(f"**Fails today:** {r.failed or 'nothing — passes every rule'}")
        st.caption("Daily snapshot history")
        st.dataframe(snap[["date", "close", "rs", "sys_rank", "n_fail", "failed", "np_yoy", "sales_yoy", "roe"]],
                     hide_index=True, width="stretch")
    else:
        st.info("Not in the system's universe on any stored day (no fundamentals or too illiquid).")
    lists = q("SELECT date, list, rank FROM picks WHERE symbol=? ORDER BY date DESC", [sym])
    st.caption("Days on a list")
    st.dataframe(lists, hide_index=True, width="stretch") if len(lists) else st.write("Never listed.")

# ------------------------------------------------------------------ Journal
elif page == "Journal":
    st.title("Decision journal")
    j = q("SELECT d.id, d.date, d.symbol, d.action, d.light, d.price, d.reason FROM decisions d ORDER BY d.date DESC, d.id DESC")
    if j.empty:
        st.info("No decisions yet. Every buy, hold, sell and note you log on the Holdings page lands here.")
        st.stop()
    table(j.drop(columns="id"), "t_journal", hide_index=True, width="stretch")
    st.subheader("Did overriding the rule help?")
    st.caption("Every HOLD logged while the light was RED (the rule said sell). Compares the price then with the "
               "latest close, or the sell price if you've since sold. Positive = the override beat the rule.")
    ov = j[(j.action == "HOLD") & (j.light == "RED")].copy()
    if ov.empty:
        st.write("No overrides yet.")
    else:
        H = q("SELECT id, symbol, sell_price FROM holdings")
        rows = []
        for r in ov.itertuples():
            hid = q("SELECT holding_id FROM decisions WHERE id=?", [int(r.id)]).holding_id.iloc[0]
            sp = H.set_index("id").sell_price.get(hid)
            now = sp if sp is not None and pd.notna(sp) else holdings.closes(r.symbol).iloc[-1]
            rows.append({"date": r.date, "symbol": r.symbol, "rule said sell at": r.price, "now / sold": now,
                         "override vs rule": now / r.price - 1 if r.price else None, "reason": r.reason})
        o = pd.DataFrame(rows)
        table(o, "t_override", hide_index=True, width="stretch",
                     column_config={"override vs rule": st.column_config.NumberColumn(format="percent")})
        st.metric("Average override result", pct(o["override vs rule"].mean()), help=f"{len(o)} overrides")
