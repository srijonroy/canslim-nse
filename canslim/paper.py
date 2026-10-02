"""Paper portfolio: the system trading its own daily lists, live, from the first stored scan onward.

Same rules as the backtest (canslim.portfolio with data/tune/final.json):
  * 10 slots, equal weight of current equity, max 3 per industry
  * SELL signal when a holding fails any rule or ranks > 30 among passing stocks (or drops out of the universe)
  * BUY the highest-RS passing stocks into free slots, only when the market is CONFIRMED_UPTREND or
    UPTREND_UNDER_PRESSURE
  * signals at the scan-day close, filled at the NEXT trading day's open; 0.3% cost each side;
    idle cash earns 6%/yr
Rebuilt from scratch from data/canslim.db on every run, so it is reproducible and can't drift.
Notional capital Rs 10,00,000. Nothing is ever ordered.

Also builds the "sold, still watching" list: every stock that left the CAN SLIM list or was sold by the paper
portfolio in the last 24 months, with where it is now and whether it qualifies again.

usage: python -m canslim.paper
"""
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import db
from canslim.holdings import PRICES

CAPITAL, N, KEEP_RANK, MAX_PER_GROUP, COST, CASH_YIELD = 1_000_000.0, 10, 30, 3, 0.003, 0.06
BUY_STATES = ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE")

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_trades(
  symbol TEXT, signal_date TEXT, entry_date TEXT, entry REAL, shares REAL, exit_signal_date TEXT, exit_date TEXT,
  exit REAL, ret REAL, why TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS paper_equity(
  date TEXT PRIMARY KEY, equity REAL, cash REAL, invested REAL, n_pos INTEGER, market TEXT, nifty500 REAL);
CREATE TABLE IF NOT EXISTS paper_pending(signal_date TEXT, symbol TEXT, side TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS watching(
  symbol TEXT, source TEXT, left_date TEXT, left_price REAL, close REAL, since_left REAL, rs REAL,
  sys_rank INTEGER, n_fail INTEGER, failed TEXT, status TEXT, as_of TEXT);
"""

_px = {}


def ohlc(sym: str) -> pd.DataFrame:
    if sym not in _px:
        f = PRICES / f"NSE_{sym.replace('&', 'and')}-EQ.parquet"
        df = pd.read_parquet(f) if f.exists() else pd.DataFrame(columns=["open", "close"])
        df.index = pd.to_datetime(df.index)
        _px[sym] = df
    return _px[sym]


def next_open(sym: str, after: str):
    """(date, open) of the first trading day after `after`, or None if not in the data yet."""
    df = ohlc(sym)
    nxt = df[df.index > pd.Timestamp(after)]
    nxt = nxt[nxt.open.notna()]
    return (nxt.index[0], float(nxt.open.iloc[0])) if len(nxt) else None


def close_on(sym: str, d: str):
    s = ohlc(sym).close.loc[:pd.Timestamp(d)].dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def run(c=None) -> dict:
    own = c is None
    c = c or db.connect()
    c.executescript(SCHEMA)
    dates = [r[0] for r in c.execute("SELECT DISTINCT date FROM snapshot ORDER BY date")]
    market = dict(c.execute("SELECT date, state FROM market"))
    n500 = pd.read_parquet(PRICES / "NSE_NIFTY500-INDEX.parquet")["close"]
    n500.index = pd.to_datetime(n500.index)
    cash, pos, trades, eq = CAPITAL, {}, [], []
    pend_buy, pend_sell, prev = [], {}, None
    for d in dates:
        # 1) fill yesterday's signals at the next open (only once that day's prices exist, i.e. <= d)
        if prev is not None:
            for s, why in list(pend_sell.items()):
                f = next_open(s, prev)
                if f and f[0] <= pd.Timestamp(d):
                    h = pos.pop(s)
                    cash += h["shares"] * f[1] * (1 - COST)
                    trades.append({**h, "exit_signal_date": prev, "exit_date": f"{f[0]:%Y-%m-%d}", "exit": f[1],
                                   "ret": f[1] / h["entry"] * (1 - COST) ** 2 - 1, "why": why, "status": "closed"})
                    del pend_sell[s]
            if pend_buy:
                equity = cash + sum(h["shares"] * close_on(s, prev) for s, h in pos.items())
                slot = equity / N
                for s in pend_buy:
                    f = next_open(s, prev)
                    if not f or f[0] > pd.Timestamp(d) or s in pos or cash < slot * 0.5:
                        continue
                    spend = min(slot, cash)
                    pos[s] = {"symbol": s, "signal_date": prev, "entry_date": f"{f[0]:%Y-%m-%d}", "entry": f[1],
                              "shares": spend * (1 - COST) / f[1]}
                    cash -= spend
                pend_buy = []
            cash *= (1 + CASH_YIELD) ** ((pd.Timestamp(d) - pd.Timestamp(prev)).days / 365)
        # 2) mark to market
        inv = sum(h["shares"] * close_on(s, d) for s, h in pos.items())
        st = market.get(d, "?")
        eq.append({"date": d, "equity": cash + inv, "cash": cash, "invested": inv, "n_pos": len(pos), "market": st,
                   "nifty500": float(n500.loc[:pd.Timestamp(d)].iloc[-1])})
        # 3) signals at the close
        snap = pd.read_sql_query("SELECT symbol, sys_rank, n_fail, industry, rs FROM snapshot WHERE date=?",
                                 c, params=[d]).set_index("symbol")
        for s in pos:
            if s in pend_sell:
                continue
            if s not in snap.index:
                pend_sell[s] = "left the universe"
            elif snap.at[s, "n_fail"] > 0:
                pend_sell[s] = "fails a rule"
            elif pd.isna(snap.at[s, "sys_rank"]) or snap.at[s, "sys_rank"] > KEEP_RANK:
                pend_sell[s] = f"rank > {KEEP_RANK}"
        if st in BUY_STATES:
            keep = [s for s in pos if s not in pend_sell]
            free = N - len(keep)
            groups = snap.industry.reindex(keep).value_counts().to_dict()
            for s, r in snap[snap.n_fail == 0].sort_values("sys_rank").iterrows():
                if free <= 0:
                    break
                if s in pos:
                    continue
                if r.industry and groups.get(r.industry, 0) >= MAX_PER_GROUP:
                    continue
                pend_buy.append(s)
                groups[r.industry] = groups.get(r.industry, 0) + 1
                free -= 1
        prev = d
    last = dates[-1] if dates else None
    for s, h in pos.items():
        px = close_on(s, last)
        trades.append({**h, "exit_signal_date": None, "exit_date": None, "exit": px,
                       "ret": px / h["entry"] - 1, "why": "SELL signal - fills next open" if s in pend_sell else "",
                       "status": "open"})
    T = pd.DataFrame(trades, columns=["symbol", "signal_date", "entry_date", "entry", "shares", "exit_signal_date",
                                      "exit_date", "exit", "ret", "why", "status"])
    E = pd.DataFrame(eq)
    P = pd.DataFrame([{"signal_date": last, "symbol": s, "side": "BUY", "reason": "top passing, free slot"}
                      for s in pend_buy] +
                     [{"signal_date": last, "symbol": s, "side": "SELL", "reason": w} for s, w in pend_sell.items()],
                     columns=["signal_date", "symbol", "side", "reason"])
    W = watching(c, T, last)
    for name, df in (("paper_trades", T), ("paper_equity", E), ("paper_pending", P), ("watching", W)):
        c.execute(f"DELETE FROM {name}")
        if len(df):
            df.to_sql(name, c, if_exists="append", index=False)
    c.commit()
    if own:
        c.close()
    e = E.iloc[-1] if len(E) else None
    return {"as_of": last, "equity": None if e is None else round(e.equity), "positions": len(pos),
            "closed": int((T.status == "closed").sum()), "pending": len(P), "watching": len(W)}


def watching(c, T: pd.DataFrame, as_of: str | None) -> pd.DataFrame:
    if as_of is None:
        return pd.DataFrame()
    cutoff = f"{pd.Timestamp(as_of) - pd.DateOffset(months=24):%Y-%m-%d}"
    picks = pd.read_sql_query("SELECT date, symbol, close FROM picks WHERE list='canslim' AND date>=? ORDER BY date",
                              c, params=[cutoff])
    rows = {}
    days = sorted(picks.date.unique())
    for i in range(1, len(days)):
        before = picks[picks.date == days[i - 1]].set_index("symbol")
        now = set(picks[picks.date == days[i]].symbol)
        for s in before.index.difference(list(now)):
            rows[s] = {"symbol": s, "source": "left CAN SLIM list", "left_date": days[i],
                       "left_price": close_on(s, days[i])}
    for t in T[(T.status == "closed") & (T.exit_date >= cutoff)].itertuples():
        rows[t.symbol] = {"symbol": t.symbol, "source": "sold by paper portfolio", "left_date": t.exit_date,
                          "left_price": t.exit}
    if not rows:
        return pd.DataFrame()
    W = pd.DataFrame(rows.values())
    on_list = set(picks[picks.date == days[-1]].symbol) if days else set()
    W = W[~W.symbol.isin(on_list)]
    snap = pd.read_sql_query("SELECT symbol, rs, sys_rank, n_fail, failed FROM snapshot WHERE date=?",
                             c, params=[as_of]).set_index("symbol")
    W = W.join(snap, on="symbol")
    W["close"] = [close_on(s, as_of) for s in W.symbol]
    W["since_left"] = W.close / W.left_price - 1

    def status(r):
        if pd.isna(r.n_fail):
            return "out of the universe"
        if r.n_fail == 0 and pd.notna(r.sys_rank) and r.sys_rank <= KEEP_RANK:
            return "QUALIFIES AGAIN"
        if r.n_fail == 1:
            return "1 rule away"
        return "not qualifying"
    W["status"] = W.apply(status, axis=1)
    W["as_of"] = as_of
    return W[["symbol", "source", "left_date", "left_price", "close", "since_left", "rs", "sys_rank", "n_fail",
              "failed", "status", "as_of"]]


if __name__ == "__main__":
    print(run())
