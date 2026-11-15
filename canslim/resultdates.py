"""When each quarterly result actually became public, from the exchanges' own filing timestamps.

Why: data.fundamentals infers the announcement date from Screener's TTM-EPS stamps. The 2026-11-15 audit
(experiments/audit.py) found ~10% of those stamps EARLIER than NSE received the result (median 20 days, some
2-5 days after the quarter end), i.e. look-ahead in the backtest. A result now counts as known from the later
of Screener's stamp and the exchange date, found in this order (`checked()` returns the date and its source):

  nse        NSE filing in a result category ("Financial Result Updates", ...), or an "Outcome of Board
             Meeting" whose text mentions results/financials (how NSE files results in e.g. Aug 2022)
  bse        BSE "Result" filing, for the few companies with no NSE announcements at all (MCX, ABBOTINDIA,
             ICICILIFE); downloaded with `python -m canslim.resultdates --bse` into data/events/bse_results
  nse-board  a generic "Outcome of Board Meeting" (no text clue: most filings from Mar 2025 on) confirmed by a
             results follow-up within 5 days: newspaper publication, press release, investor presentation or
             results call whose text mentions results/financials/earnings
  usual-lag  no filing found and Screener's stamp is under 21 days after the quarter end (wrong 41-89% of the
  deadline   time where it can be checked): the company's own median lag on checked quarters (needs 4), else
             the SEBI deadline (45 days; 60 for the March quarter)
  screener   no filing found, stamp 21+ days after the quarter end (right ~95% of the time): kept

A filing is usable for a decision at the close of day D when the exchange received it before the next 09:15
open, so its effective date is (timestamp - 9h15m).date. A filing belongs to the latest quarter that ended
before it (within 150 days, and before the next quarter end).

usage: from canslim import resultdates; resultdates.checked("TCS", quarter_ends, screener_dates)
       python -m canslim.resultdates --bse [SYM,SYM]     (default: universe stocks NSE has no announcements for)
"""
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANN = ROOT / "data" / "events" / "ann"
BSE = ROOT / "data" / "events" / "bse_results"
CACHE = ROOT / "data" / "events" / "result_filings.parquet"
RESULT_DESC = {"Financial Result Updates", "Financial Results Updates", "Integrated Filing- Financial",
               "Publish Audited Results", "Results"}
RESULT_TXT = re.compile(r"result|financial", re.I)
CONFIRM_DESC = {"Copy of Newspaper Publication", "Newspaper Advertisements", "Press Release", "Investor Presentation",
                "Analysts/Institutional Investor Meet/Con. Call Updates"}
CONFIRM_TXT = re.compile(r"result|financial|earning", re.I)
CONFIRM_DAYS, EARLY_STAMP, MIN_OWN = 5, 21, 4
BSE_ONLY = ("MCX", "ABBOTINDIA", "ICICILIFE")
_BY = None


def norm(s) -> str:
    return str(s).replace("&", "and")          # price/fundamental files store '&' as 'and'


def filings(refresh: bool = False) -> pd.DataFrame:
    """Every result-related filing: sym, ts, eff (usable at that day's close), kind (result | bse | board |
    confirm). Cached; rebuilt when an announcement file is newer."""
    files = sorted(ANN.glob("*.json")) + sorted(BSE.glob("*.json"))
    newest = max((f.stat().st_mtime for f in files), default=0)
    if not refresh and CACHE.exists() and CACHE.stat().st_mtime >= newest:
        a = pd.read_parquet(CACHE)
        if "kind" in a.columns:
            return a
    rows = []
    for f in sorted(ANN.glob("*.json")):
        for x in json.loads(f.read_text(encoding="utf-8")):
            d, txt = x.get("desc") or "", x.get("attchmntText") or ""
            if d in RESULT_DESC or d.startswith("Results Update"):
                k = "result"
            elif d == "Outcome of Board Meeting":
                k = "result" if RESULT_TXT.search(txt) else "board"
            elif d in CONFIRM_DESC and CONFIRM_TXT.search(txt):
                k = "confirm"
            else:
                continue
            rows.append((norm(x["symbol"]), x["sort_date"], k))
    for f in sorted(BSE.glob("*.json")):
        rows += [(f.stem, t, "bse") for t in json.loads(f.read_text(encoding="utf-8"))["ts"]]
    a = pd.DataFrame(rows, columns=["sym", "ts", "kind"])
    a["ts"] = pd.to_datetime(a["ts"], errors="coerce", format="mixed")     # NSE "2019-05-31 23:07:00", BSE ISO with T
    a["ts"] = a["ts"].dt.floor("s").astype("datetime64[ns]")
    a = a.dropna(subset=["ts"]).drop_duplicates().sort_values(["sym", "ts"]).reset_index(drop=True)
    a["eff"] = (a["ts"] - pd.Timedelta(hours=9, minutes=15)).dt.normalize()
    if len(a):
        a.to_parquet(CACHE)
    return a


def _by_sym() -> dict:
    """sym -> {kind: sorted array of timestamps}; 'board' holds only confirmed board outcomes."""
    global _BY
    if _BY is None:
        _BY = {}
        try:
            a = filings()
        except Exception as e:                      # no event data (e.g. a fresh checkout): fall back silently
            print(f"  resultdates: exchange filings unavailable ({type(e).__name__}); using Screener dates only", flush=True)
            return _BY
        for s, g in a.groupby("sym"):
            t = {k: x["ts"].values for k, x in g.groupby("kind")}
            b, c = t.pop("board", None), t.pop("confirm", None)
            if b is not None and c is not None:
                j = np.searchsorted(c, b, side="left")                  # first follow-up at/after the board filing
                ok = (j < len(c)) & (c[np.minimum(j, len(c) - 1)] <= b + np.timedelta64(CONFIRM_DAYS, "D"))
                if ok.any():
                    t["board"] = b[ok]
            _BY[s] = t
    return _BY


def _first_in_window(t, qs) -> pd.Series:
    """First timestamp in t after each quarter end (within 150 days and before the next quarter end)."""
    out = pd.Series(pd.NaT, index=qs, dtype="datetime64[ns]")
    if t is None or not len(t) or not len(qs):
        return out
    lo = (qs + pd.Timedelta(days=1)).values
    hi = (qs + pd.Timedelta(days=150)).values.copy()
    hi[:-1] = np.minimum(hi[:-1], (qs[1:] + pd.Timedelta(days=1)).values)
    i = np.searchsorted(t, lo, side="right")
    ok = (i < len(t)) & (t[np.minimum(i, len(t) - 1)] < hi)
    out[ok] = t[i[ok]]
    return out


def for_quarters(sym: str, quarter_ends, tiers=("result", "bse", "board")) -> pd.DataFrame:
    """Per quarter end: ts (exchange timestamp), eff (usable at that day's close), src (nse | bse | nse-board)."""
    qs = pd.DatetimeIndex(sorted(quarter_ends))
    by = _by_sym().get(sym, {})
    ts = pd.Series(pd.NaT, index=qs, dtype="datetime64[ns]")
    src = pd.Series("", index=qs, dtype=object)
    for kind, label in (("result", "nse"), ("bse", "bse"), ("board", "nse-board")):
        if kind not in tiers:
            continue
        t = _first_in_window(by.get(kind), qs)
        fill = ts.isna() & t.notna()
        ts[fill], src[fill] = t[fill], label
    eff = (ts - pd.Timedelta(hours=9, minutes=15)).dt.normalize()
    return pd.DataFrame({"ts": ts, "eff": eff, "src": src})


def checked(sym: str, quarter_ends, screener_known) -> pd.DataFrame:
    """Final point-in-time date per quarter: known (never before the exchange filing) and src (see module doc).
    quarter_ends must be sorted; screener_known is aligned with it."""
    qs = pd.DatetimeIndex(quarter_ends)
    scr = pd.Series(pd.DatetimeIndex(screener_known), index=qs)
    f = for_quarters(sym, qs).reindex(qs)
    known, src = scr.copy(), f["src"].replace("", "screener")
    has = f["eff"].notna()
    known[has] = np.maximum(scr[has].values, f.loc[has, "eff"].values)
    lag = (scr - qs).dt.days
    weak = ~has & (lag < EARLY_STAMP)                 # no filing, and a stamp too soon after the quarter end
    if weak.any():
        own = (f.loc[has, "eff"] - qs[has.values]).dt.days
        for qe in qs[weak.values]:
            if len(own) >= MIN_OWN:
                d, s = int(own.median()), "usual-lag"
            else:
                d, s = (60 if qe.month == 3 else 45), "deadline"
            known[qe], src[qe] = max(scr[qe], qe + pd.Timedelta(days=d)), s
    return pd.DataFrame({"known": known, "src": src, "exchange_ts": f["ts"]})


# ---------------------------------------------------------------- BSE result filings (companies NSE lacks)
def fetch_bse(sym: str, first_year: int = 2015) -> int:
    """BSE 'Result' filings for one company, one calendar year per call (longer ranges return nothing)."""
    from canslim.prefissue import _page
    from canslim.shp import bse_codes
    code = bse_codes()[sym]
    BSE.mkdir(parents=True, exist_ok=True)
    f = BSE / f"{sym}.json"
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"years_done": [], "ts": []}
    this = pd.Timestamp.today().year
    for yr in range(first_year, this + 1):
        if yr in d["years_done"] and yr != this:
            continue
        p, got, total = 1, 0, None
        while True:
            end = f"{yr}1231" if yr != this else f"{pd.Timestamp.today():%Y%m%d}"     # a future end date -> HTTP 400
            t, total = _page(code, f"{yr}0101", end, p)     # every category; BSE rejects a category filter
            # 'Financial Results' also carries half-yearly related-party disclosures: keep real results only
            d["ts"] += [x["NEWS_DT"] for x in t if x.get("CATEGORYNAME") == "Result"
                        and not re.search(r"related party", x.get("HEADLINE") or "", re.I)]
            got += len(t)
            if not t or got >= total:
                break
            p += 1
            time.sleep(0.5)
        if yr != this:
            d["years_done"].append(yr)
        d["ts"] = sorted(set(d["ts"]))
        f.write_text(json.dumps(d), encoding="utf-8")       # save per year: a block mid-way loses nothing
        time.sleep(1.0)                              # BSE blocks fast crawls (403 within a minute at 4 workers)
    d["ts"] = sorted(set(d["ts"]))
    f.write_text(json.dumps(d), encoding="utf-8")
    return len(d["ts"])


if __name__ == "__main__":
    if "--bse" in sys.argv:
        rest = [a for a in sys.argv[1:] if not a.startswith("--")]
        for s in (rest[0].split(",") if rest else BSE_ONLY):
            print(f"  {s}: {fetch_bse(s)} BSE result filings", flush=True)
        print(f"  cache rebuilt: {len(filings(refresh=True))} filings")
