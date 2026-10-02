"""Holdings tracker: a daily traffic light for each open position.

  RED    the system's tested sell signal: the stock fails a CAN SLIM rule or ranks below 30 among passing
         stocks (canslim.portfolio, keep_rank=30). On 2016-22 this beat every "hold longer" rule tried
         (canslim/holdtest.py). Default action: sell. Overriding is allowed, but log the reason.
  AMBER  still passes and ranks <= 30, but an early warning is on (NOT tested as a sell rule, information only):
         ranked 21-30, close below the 50-day MA, 15%+ below the peak close since purchase, or RS down 15+
         points since purchase.
  GREEN  passes, ranks <= 20, no warning. Sit tight.
  GREY   not in the system's universe (no fundamentals or too illiquid), so the system can't judge it.

Prices are the raw (unadjusted) closes in data/prices, matching what the user actually paid.
A split or bonus after the buy date will show as a fake loss until the holding is edited.
"""
from pathlib import Path

import pandas as pd

from canslim import db

PRICES = Path(__file__).resolve().parent.parent / "data" / "prices"
KEEP_RANK, GREEN_RANK = 30, 20


def closes(sym: str) -> pd.Series:
    f = PRICES / f"NSE_{sym.replace('&', 'and')}-EQ.parquet"
    if not f.exists():
        return pd.Series(dtype=float)
    s = pd.read_parquet(f)["close"]
    s.index = pd.to_datetime(s.index)
    return s.dropna()


def open_holdings(c) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM holdings WHERE sell_date IS NULL ORDER BY buy_date", c)


def snapshot_on(c, d=None) -> tuple[str | None, pd.DataFrame]:
    d = d or c.execute("SELECT MAX(date) FROM snapshot").fetchone()[0]
    if d is None:
        return None, pd.DataFrame()
    s = pd.read_sql_query("SELECT * FROM snapshot WHERE date=?", c, params=[d]).set_index("symbol")
    return d, s


def rs_on(c, sym: str, d: str):
    r = c.execute("SELECT rs FROM snapshot WHERE symbol=? AND date<=? ORDER BY date DESC LIMIT 1", (sym, d)).fetchone()
    return r[0] if r else None


def light_for(h, snap: pd.DataFrame, px: pd.Series, rs_at_buy) -> dict:
    sym = h["symbol"]
    since = px.loc[pd.Timestamp(h["buy_date"]):]
    last = float(px.iloc[-1]) if len(px) else None
    peak = float(max(since.max(), h["buy_price"])) if len(since) else h["buy_price"]
    out = {"symbol": sym, "holding_id": int(h["id"]), "close": last,
           "gain": (last / h["buy_price"] - 1) if last else None,
           "from_peak": (last / peak - 1) if last else None, "sys_rank": None, "rs": None}
    if sym not in snap.index:
        return {**out, "light": "GREY", "reasons": "not in the system universe (no fundamentals or illiquid)"}
    r = snap.loc[sym]
    rank = None if pd.isna(r.sys_rank) else int(r.sys_rank)
    out.update(sys_rank=rank, rs=None if pd.isna(r.rs) else float(r.rs))
    if r.n_fail > 0:
        return {**out, "light": "RED", "reasons": f"fails: {r.failed}"}
    if rank is None or rank > KEEP_RANK:
        return {**out, "light": "RED", "reasons": f"ranked {rank} of passing stocks (system keeps <= {KEEP_RANK})"}
    warn = []
    if rank > GREEN_RANK:
        warn.append(f"rank {rank} (close to the {KEEP_RANK} cut-off)")
    if len(px) >= 50 and last < px.iloc[-50:].mean():
        warn.append("below 50-day average")
    if out["from_peak"] is not None and out["from_peak"] <= -0.15:
        warn.append(f"{out['from_peak']:.0%} from peak since buy")
    if rs_at_buy is not None and out["rs"] is not None and out["rs"] <= rs_at_buy - 15:
        warn.append(f"RS {out['rs']:.0f} vs {rs_at_buy:.0f} at buy")
    if warn:
        return {**out, "light": "AMBER", "reasons": "; ".join(warn)}
    return {**out, "light": "GREEN", "reasons": f"passes all rules, rank {rank}"}


def status(c, d=None) -> pd.DataFrame:
    d, snap = snapshot_on(c, d)
    H = open_holdings(c)
    if d is None or H.empty:
        return pd.DataFrame()
    rows = []
    for _, h in H.iterrows():
        px = closes(h["symbol"]).loc[:pd.Timestamp(d)]
        rows.append({"date": d, **light_for(h, snap, px, rs_on(c, h["symbol"], h["buy_date"]))})
    return pd.DataFrame(rows)


def store_status(c, d=None) -> pd.DataFrame:
    st = status(c, d)
    if len(st):
        c.execute("DELETE FROM holding_status WHERE date=?", (st.date.iloc[0],))
        st[["date", "holding_id", "symbol", "light", "reasons", "close", "gain", "from_peak", "sys_rank", "rs"]] \
            .to_sql("holding_status", c, if_exists="append", index=False)
        c.commit()
    return st
