"""CAN SLIM tracker -- local app over data/canslim.db.

Pages: Today (lists + market), Insights (research findings, data/research/insights/*.md), Holdings (traffic light, add / log / sell), Stock (history of any symbol),
Journal (every decision, and whether overriding the rule helped).
Research only. Nothing here places orders.

usage: run_app.bat   (or: python -m streamlit run tracker_app.py)
"""
from datetime import date

import pandas as pd
import streamlit as st

from canslim import db, holdings

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


dates = q("SELECT DISTINCT date FROM snapshot ORDER BY date DESC").date.tolist()
page = st.sidebar.radio("Page", ["Today", "Insights", "Holdings", "Research", "Paper portfolio", "Watching", "Stock",
                                 "Journal"])
st.sidebar.caption(f"Database: {db.DB}\n\nLatest scan: {dates[0] if dates else 'none'}")
st.sidebar.caption("Research only. No orders are placed.")

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
    st.dataframe(cs, hide_index=True, width="stretch",
                 column_config={"rs": st.column_config.NumberColumn(format="%.0f")})
    if prev and dropped:
        st.caption(f"Dropped since {prev}: " + ", ".join(dropped))
    a, b = st.columns(2)
    with a:
        st.subheader("Emerging / turnaround (higher risk)")
        st.dataframe(q("SELECT rank, symbol, close, rs, industry, note FROM picks WHERE date=? AND list='emerging' "
                       "ORDER BY rank", [d]), hide_index=True, width="stretch")
    with b:
        st.subheader("Earnings monitor (price confirming)")
        st.dataframe(q("SELECT symbol, close, rs, industry, note FROM picks WHERE date=? AND list='earnings' "
                       "ORDER BY rs DESC", [d]), hide_index=True, width="stretch")
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
        st.dataframe(v[["light", "symbol", "conviction", "buy_date", "qty", "buy_price", "close", "gain", "from_peak",
                        "sys_rank", "rs", "value", "P&L", "reasons"]],
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
        st.dataframe(closed, hide_index=True, width="stretch",
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
            st.caption(f"Topics: {', '.join(it['tags'])}  ·  Source: {it.get('source', '')}")

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
        st.dataframe(pend, hide_index=True, width="stretch")
    T = q("SELECT * FROM paper_trades")
    op = T[T.status == "open"].copy()
    st.subheader(f"Open positions ({len(op)})")
    if len(op):
        snap = q("SELECT symbol, rs, sys_rank, n_fail, failed FROM snapshot WHERE date=?", [e1.date])
        op = op.merge(snap, on="symbol", how="left")
        op["value"] = op.shares * op.exit
        st.dataframe(op[["symbol", "entry_date", "entry", "exit", "ret", "value", "rs", "sys_rank", "failed", "why"]]
                     .rename(columns={"exit": "close", "ret": "return", "why": "signal"}),
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
        st.dataframe(cl[["symbol", "entry_date", "entry", "exit_date", "exit", "ret", "why"]].sort_values(
            "exit_date", ascending=False), hide_index=True, width="stretch",
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
        st.dataframe(W.drop(columns=["as_of"]), hide_index=True, width="stretch",
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
    st.dataframe(j.drop(columns="id"), hide_index=True, width="stretch")
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
        st.dataframe(o, hide_index=True, width="stretch",
                     column_config={"override vs rule": st.column_config.NumberColumn(format="percent")})
        st.metric("Average override result", pct(o["override vs rule"].mean()), help=f"{len(o)} overrides")
