"""Download NSE event feeds for event studies (one request at a time, ~1.2 s apart; resumable).

  ann   corporate announcements, monthly files from 2012 (category 'desc', symbol, time, text)
  pit   insider-trading disclosures (SEBI PIT), monthly from 2016
  ca    corporate actions (bonus, split, buyback, dividend ... with ex-date), yearly from 2010
  bulk  bulk deals, one request per day (the API returns at most 70 rows per call; days at 70 are flagged)

Files: data/events/<feed>/<period>.json. A finished past period is never fetched again; the current
month/year is always refreshed.

usage: python -m canslim.events_dl ann pit ca [bulk]
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

from canslim.prefissue import nse_session

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "events"
BASE = "https://www.nseindia.com/api/"
ANN_KEEP = ["symbol", "sm_name", "desc", "an_dt", "sort_date", "attchmntText", "seq_id", "smIndustry"]

_s = None


def get(url):
    global _s
    for i in range(5):
        try:
            if _s is None:
                _s = nse_session()
            r = _s.get(BASE + url, timeout=90)
            j = r.json()
            time.sleep(1.2)
            return j if isinstance(j, list) else j.get("data", [])
        except Exception as e:
            print(f"    retry {i + 1} ({str(e)[:80]})", flush=True)
            _s = None
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"failed: {url}")


def periods(start, freq):
    today = pd.Timestamp.today().normalize()
    for p in pd.date_range(start, today, freq=freq):
        end = p + (pd.offsets.MonthEnd(0) if freq == "MS" else pd.offsets.YearEnd(0))
        yield p, min(end, today), end >= today


def run(feed):
    (OUT / feed).mkdir(parents=True, exist_ok=True)
    if feed == "bulk":
        return run_bulk()
    start, freq = {"ann": ("2012-01-01", "MS"), "pit": ("2016-01-01", "MS"), "ca": ("2010-01-01", "YS")}[feed]
    t0 = time.time()
    for a, b, current in periods(start, freq):
        name = a.strftime("%Y-%m" if freq == "MS" else "%Y")
        f = OUT / feed / f"{name}.json"
        if f.exists() and not current:
            continue
        rng = f"from_date={a:%d-%m-%Y}&to_date={b:%d-%m-%Y}"
        if feed == "ann":
            rows = [{k: (x.get(k) or "")[:600] if k == "attchmntText" else x.get(k) for k in ANN_KEEP}
                    for x in get(f"corporate-announcements?index=equities&{rng}")]
        elif feed == "pit":
            rows = get(f"corporates-pit?index=equities&{rng}")
        else:
            rows = get(f"corporates-corporateActions?index=equities&{rng}")
        f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"[{feed}] {name}: {len(rows)} rows  ({time.time() - t0:.0f}s)", flush=True)


def run_bulk():
    t0 = time.time()
    today = pd.Timestamp.today().normalize()
    for m in pd.date_range("2016-01-01", today, freq="MS"):
        f = OUT / "bulk" / f"{m:%Y-%m}.json"
        current = m + pd.offsets.MonthEnd(0) >= today
        if f.exists() and not current:
            continue
        rows, full_days = [], []
        for d in pd.bdate_range(m, min(m + pd.offsets.MonthEnd(0), today)):
            day = get(f"historicalOR/bulk-block-short-deals?optionType=bulk_deals&from={d:%d-%m-%Y}&to={d:%d-%m-%Y}")
            rows += day
            if len(day) >= 70:
                full_days.append(f"{d:%Y-%m-%d}")
        f.write_text(json.dumps({"rows": rows, "truncated_days": full_days}, ensure_ascii=False), encoding="utf-8")
        print(f"[bulk] {m:%Y-%m}: {len(rows)} deals, {len(full_days)} days cut at 70  ({time.time() - t0:.0f}s)",
              flush=True)


if __name__ == "__main__":
    for feed in sys.argv[1:] or ["ann", "pit", "ca"]:
        run(feed)
