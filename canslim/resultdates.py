"""When each quarterly result actually became public, from NSE's own filing timestamps (data/events/ann).

Why: data.fundamentals infers the announcement date from Screener's TTM-EPS stamps. The 2026-11-15 audit
(experiments/audit.py) found ~10% of those stamps EARLIER than NSE received the result (median 20 days, some
2-5 days after the quarter end), i.e. look-ahead in the backtest. The fix: a result counts as known from the
later of the two dates.

A filing is usable for a decision at the close of day D when NSE received it before the next 09:15 open, so its
effective date is (timestamp - 9h15m).date. NSE files results as "Financial Result Updates" in most months, but
only as "Outcome of Board Meeting" in some (all of Aug 2022, most of 2025-26), so board-meeting outcomes whose
text mentions results/financials count too. A filing belongs to the latest quarter that ended before it (within
150 days, and before the next quarter end).

usage: from canslim import resultdates; resultdates.for_quarters("TCS", quarter_ends)  -> Series of dates (NaT = none)
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANN = ROOT / "data" / "events" / "ann"
CACHE = ROOT / "data" / "events" / "result_filings.parquet"
RESULT_DESC = {"Financial Result Updates", "Financial Results Updates", "Integrated Filing- Financial",
               "Publish Audited Results", "Results"}
RESULT_TXT = re.compile(r"result|financial", re.I)
_BY = None


def norm(s) -> str:
    return str(s).replace("&", "and")          # price/fundamental files store '&' as 'and'


def filings(refresh: bool = False) -> pd.DataFrame:
    """Every NSE result filing: sym, ts (NSE timestamp), eff (usable at that day's close). Cached."""
    files = sorted(ANN.glob("*.json"))
    newest = max((f.stat().st_mtime for f in files), default=0)
    if not refresh and CACHE.exists() and CACHE.stat().st_mtime >= newest:
        return pd.read_parquet(CACHE)
    rows = []
    for f in files:
        for x in json.loads(f.read_text(encoding="utf-8")):
            d, txt = x.get("desc") or "", x.get("attchmntText") or ""
            if (d in RESULT_DESC or d.startswith("Results Update")
                    or (d == "Outcome of Board Meeting" and RESULT_TXT.search(txt))):
                rows.append((norm(x["symbol"]), x["sort_date"]))
    a = pd.DataFrame(rows, columns=["sym", "ts"])
    a["ts"] = pd.to_datetime(a["ts"], errors="coerce")
    a = a.dropna(subset=["ts"]).drop_duplicates().sort_values(["sym", "ts"]).reset_index(drop=True)
    a["eff"] = (a["ts"] - pd.Timedelta(hours=9, minutes=15)).dt.normalize()
    if len(a):
        a.to_parquet(CACHE)
    return a


def _by_sym() -> dict:
    global _BY
    if _BY is None:
        try:
            _BY = {s: g for s, g in filings().groupby("sym")}
        except Exception as e:                      # no event data (e.g. a fresh checkout): fall back silently
            print(f"  resultdates: NSE filings unavailable ({type(e).__name__}); using Screener dates only", flush=True)
            _BY = {}
    return _BY


def for_quarters(sym: str, quarter_ends, with_ts: bool = False):
    """NSE's first result filing for each quarter end (effective date; NaT if none found)."""
    qs = pd.DatetimeIndex(sorted(quarter_ends))
    g = _by_sym().get(sym)
    eff = pd.Series(pd.NaT, index=qs, dtype="datetime64[ns]")
    ts = eff.copy()
    if g is not None and len(qs):
        t = g["ts"].values                                   # sorted
        lo = (qs + pd.Timedelta(days=1)).values
        hi = (qs + pd.Timedelta(days=150)).values.copy()
        hi[:-1] = np.minimum(hi[:-1], (qs[1:] + pd.Timedelta(days=1)).values)
        i = np.searchsorted(t, lo, side="right")             # first filing strictly after qe + 1 day
        ok = (i < len(t)) & (t[np.minimum(i, len(t) - 1)] < hi)
        eff[ok] = g["eff"].values[i[ok]]
        ts[ok] = t[i[ok]]
    return (eff, ts) if with_ts else eff
