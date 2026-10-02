"""SQLite store for everything the daily scan produces, plus the user's holdings and decision log.

File: data/canslim.db. Written by canslim.daily after each run; read by the tracker app (tracker_app.py).

Tables
  market(date, state)
  snapshot(date, symbol, ...)          every liquid stock with fundamentals, every day: rules, RS, system rank
  picks(date, list, rank, symbol, ...) list = canslim | emerging | earnings
  holdings(id, symbol, buy_date, qty, buy_price, thesis, wrong_if, sell_date, sell_price, sell_reason)
  holding_status(date, holding_id, light, reasons, close, ...)   the traffic light, stored daily
  decisions(id, date, symbol, holding_id, light, action, reason)  the user's journal

usage: python -m canslim.db --backfill     (load the CSVs already in data/history)
"""
import argparse
import os
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("CANSLIM_DB", ROOT / "data" / "canslim.db"))  # env override for tests
HISTORY = ROOT / "data" / "history"

SNAP_COLS = ["close", "rs", "prox_high", "trend", "np_yoy", "sales_yoy", "streak", "ttm_cagr3", "roe",
             "turnover", "industry", "sector", "group_rank", "n_fail", "failed", "sys_rank"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS market(date TEXT PRIMARY KEY, state TEXT);
CREATE TABLE IF NOT EXISTS snapshot(
  date TEXT, symbol TEXT, close REAL, rs REAL, prox_high REAL, trend REAL, np_yoy REAL, sales_yoy REAL,
  streak REAL, ttm_cagr3 REAL, roe REAL, turnover REAL, industry TEXT, sector TEXT, group_rank REAL,
  n_fail INTEGER, failed TEXT, sys_rank INTEGER, PRIMARY KEY(date, symbol));
CREATE TABLE IF NOT EXISTS picks(
  date TEXT, list TEXT, rank INTEGER, symbol TEXT, close REAL, rs REAL, market TEXT, industry TEXT, note TEXT,
  PRIMARY KEY(date, list, symbol));
CREATE TABLE IF NOT EXISTS holdings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, buy_date TEXT NOT NULL, qty REAL NOT NULL,
  buy_price REAL NOT NULL, thesis TEXT, wrong_if TEXT, sell_date TEXT, sell_price REAL, sell_reason TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS holding_status(
  date TEXT, holding_id INTEGER, symbol TEXT, light TEXT, reasons TEXT, close REAL, gain REAL,
  from_peak REAL, sys_rank INTEGER, rs REAL, PRIMARY KEY(date, holding_id));
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, symbol TEXT NOT NULL, holding_id INTEGER,
  light TEXT, action TEXT NOT NULL, reason TEXT, price REAL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS conviction(
  id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, date TEXT NOT NULL, score INTEGER NOT NULL,
  suggested INTEGER, checklist_total INTEGER, brief_date TEXT, notes TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS ix_snap_sym ON snapshot(symbol, date);
CREATE INDEX IF NOT EXISTS ix_picks_sym ON picks(symbol, date);
"""


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


def _ds(d) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def system_rank(snap: pd.DataFrame) -> pd.Series:
    """Rank by RS among stocks passing every rule -- the rank the backtest keeps a holding on (<= 30)."""
    ok = snap[snap.n_fail == 0]
    return ok.rs.rank(ascending=False, method="first").astype(int).reindex(snap.index)


def store_snapshot(c, d, snap: pd.DataFrame, closes: pd.Series | None = None):
    s = snap.copy()
    if "failed" in s and s.failed.map(lambda x: isinstance(x, list)).any():
        s["failed"] = s.failed.map(lambda x: "; ".join(x) if isinstance(x, list) else x)
    if "sys_rank" not in s:
        s["sys_rank"] = system_rank(s)
    if closes is not None:
        s["close"] = closes.reindex(s.index)
    for col in SNAP_COLS:
        if col not in s:
            s[col] = None
    out = s[SNAP_COLS].reset_index(names="symbol").assign(date=_ds(d))
    c.execute("DELETE FROM snapshot WHERE date=?", (_ds(d),))
    out.to_sql("snapshot", c, if_exists="append", index=False)


def store_list(c, d, name: str, rows: pd.DataFrame):
    """rows: index or column 'symbol'; optional rank, close, rs, market, industry, note."""
    c.execute("DELETE FROM picks WHERE date=? AND list=?", (_ds(d), name))
    if rows is None or not len(rows):
        return
    r = rows.copy()
    if "symbol" not in r:
        r = r.reset_index(names="symbol")
    if "rank" not in r:
        r["rank"] = range(1, len(r) + 1)
    for col in ("close", "rs", "market", "industry", "note"):
        if col not in r:
            r[col] = None
    r = r[["rank", "symbol", "close", "rs", "market", "industry", "note"]].assign(date=_ds(d), list=name)
    r.to_sql("picks", c, if_exists="append", index=False)


def store_market(c, d, state: str):
    c.execute("INSERT OR REPLACE INTO market VALUES(?,?)", (_ds(d), state))


def earnings_note(r) -> str:
    tags = (["margin up"] if r.get("margin_up") else []) + (["2 strong qtrs"] if r.get("two_strong") else [])
    return ", ".join(tags) + f" | profit {r.get('np_yoy', float('nan')):.0f}% | result {str(r.get('result_date'))[:10]}"


def store_earnings_list(c, d, name: str, df: pd.DataFrame | None):
    """name = earnings (only rows where the price confirms) | emerging."""
    if df is None or not len(df):
        store_list(c, d, name, None)
        return
    x = df.copy()
    if name == "earnings" and "price_ok" in x:
        x = x[x.price_ok.astype(bool)]
    x["note"] = [earnings_note(r) for _, r in x.iterrows()]
    store_list(c, d, name, x[[k for k in ("close", "rs", "industry", "note") if k in x]])


def backfill():
    """Load what the daily scan already wrote to data/history/*.csv."""
    c = connect()
    picks = pd.read_csv(HISTORY / "picks.csv", parse_dates=["date"])
    for d, g in picks.groupby("date"):
        store_list(c, d, "canslim", g.drop(columns="date"))
        store_market(c, d, g.market.iloc[0])
    n = 0
    for f in sorted(HISTORY.glob("snapshot_*.csv")):
        d = pd.Timestamp(f.stem.split("_")[1])
        from canslim.holdings import closes
        s = pd.read_csv(f, index_col=0)
        s["failed"] = s.failed.fillna("")
        s["close"] = [closes(sym).loc[:d].iloc[-1] if len(closes(sym).loc[:d]) else None for sym in s.index]
        store_snapshot(c, d, s)
        n += 1
    for kind in ("earnings_monitor", "emerging"):
        for f in sorted(HISTORY.glob(f"{kind}_*.csv")):
            d = pd.Timestamp(f.stem.split("_")[-1])
            store_earnings_list(c, d, "earnings" if kind == "earnings_monitor" else "emerging",
                                pd.read_csv(f, index_col=0))
    c.commit()
    print(f"backfilled: {picks.date.nunique()} days of picks, {n} snapshots -> {DB}")
    for t in ("market", "snapshot", "picks"):
        print(f"  {t}: {c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows")
    c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    if ap.parse_args().backfill:
        backfill()
