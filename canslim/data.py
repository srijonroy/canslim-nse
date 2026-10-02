"""Research data layer: corporate-action-adjusted price panels + point-in-time fundamentals.

Fyers daily bars are NOT adjusted for bonuses/splits/demergers. NSE price bands
(2-20%) make a genuine overnight gap of -25% or worse almost impossible, so such
a gap is treated as a corporate action and all earlier bars are scaled by
open/prev_close (snapped to a clean ratio like 1/2, 1/5, 2/3 when within 2%).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "prices"
FUND = ROOT / "data" / "fundamentals"
CACHE = ROOT / "data" / "cache"
GAP = -0.25
CLEAN = [1 / 2, 1 / 3, 2 / 3, 1 / 4, 3 / 4, 1 / 5, 2 / 5, 1 / 10, 1 / 20, 3 / 5, 4 / 5, 1 / 1.5]


def adjust(df: pd.DataFrame) -> pd.DataFrame:
    df = df.astype(float)
    gap = df["open"] / df["close"].shift() - 1
    for d in gap[gap <= GAP].index[::-1]:
        f = df.at[d, "open"] / df["close"].shift().at[d]
        near = min(CLEAN, key=lambda r: abs(r - f))
        f = near if abs(near - f) / f < 0.02 else f
        before = df.index < d
        df.loc[before, ["open", "high", "low", "close"]] *= f
        df.loc[before, "volume"] /= f
    return df


def name_of(f: Path) -> str:
    return f.stem[4:-3]          # NSE_ABC-EQ -> ABC  ('&' stored as 'and')


def panels(refresh: bool = False) -> dict:
    """Wide DataFrames (date x symbol): open, high, low, close, volume. Cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    keys = ["open", "high", "low", "close", "volume"]
    cp = {k: CACHE / f"panel_{k}.parquet" for k in keys}
    newest = max((f.stat().st_mtime for f in PRICES.glob("*.parquet")), default=0)
    if not refresh and all(p.exists() and p.stat().st_mtime > newest for p in cp.values()):
        return {k: pd.read_parquet(p) for k, p in cp.items()}
    cols = {k: {} for k in keys}
    for f in PRICES.glob("NSE_*-EQ.parquet"):
        df = pd.read_parquet(f)
        if len(df) < 60:
            continue
        df = adjust(df[~df.index.duplicated()])
        for k in keys:
            cols[k][name_of(f)] = df[k]
    out = {k: pd.DataFrame(v).sort_index() for k, v in cols.items()}
    idx = out["close"].index
    out = {k: v.reindex(idx) for k, v in out.items()}
    for k, v in out.items():
        v.to_parquet(cp[k])
    return out


def index_close(name: str = "NIFTY500") -> pd.Series:
    return pd.read_parquet(PRICES / f"NSE_{name}-INDEX.parquet")["close"]


# ------------------------------------------------------------- fundamentals
def _dated(values) -> pd.Series:
    s = pd.Series({pd.Timestamp(d): v for d, v in (values or []) if v is not None}, dtype=float)
    s.index = pd.DatetimeIndex(s.index)
    return s[~s.index.duplicated()].sort_index()


def fundamentals() -> dict:
    """Per symbol, point-in-time quarterly table:
        quarter end, sales, net profit (= sales * NPM), announce date (when it became known)
    plus annual net profit / equity for ROE and the Screener industry path."""
    out = {}
    for f in FUND.glob("*.json"):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text())
        h = d.get("history") or {}
        sales, npm, eps = _dated(h.get("Quarter Sales")), _dated(h.get("NPM")), _dated(h.get("EPS"))
        q = pd.DataFrame({"sales": sales, "npm": npm}).dropna()
        if q.empty:
            continue
        q["np"] = q.sales * q.npm / 100
        # announce date = first TTM-EPS stamp after the quarter end (within 120 days);
        # fallback to the SEBI deadline (45 days; 60 for the March quarter)
        ann = []
        for qe in q.index:
            later = eps.index[(eps.index > qe) & (eps.index <= qe + pd.Timedelta(days=120))]
            ann.append(later[0] if len(later) else qe + pd.Timedelta(days=60 if qe.month == 3 else 45))
        q["known"] = ann
        a, b = d["annual"], d["balance"]

        def row(tbl, key):
            s = {}
            for k, v in (tbl.get(key) or {}).items():
                try:
                    s[pd.Timestamp(k) + pd.offsets.MonthEnd(0)] = v
                except Exception:
                    pass
            r = pd.Series(s, dtype=float).dropna().sort_index()
            r.index = pd.DatetimeIndex(r.index)
            return r
        eq = row(b, "Equity Capital").add(row(b, "Reserves"), fill_value=0)
        sh = d.get("shareholding", {})
        inst = row(sh, "FIIs").add(row(sh, "DIIs"), fill_value=0)
        ind = d.get("industry") or []
        out[f.stem] = {"q": q, "a_np": row(a, "Net Profit"), "equity": eq, "inst": inst,
                       "sector": ind[0] if ind else None, "industry": ind[-1] if ind else None,
                       "debt": row(b, "Borrowings")}
    return out
