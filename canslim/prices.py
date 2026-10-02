"""Daily OHLCV store for the NSE universe, backed by Fyers history API.

One parquet file per symbol in data/prices/. First run downloads history;
later runs only fetch days after the last stored bar. Safe to interrupt and rerun.

usage: python -m canslim.prices [--years 3] [--limit N]
"""
import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from canslim.fyers_auth import get_client

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PRICES = DATA / "prices"
MASTER_URL = "https://public.fyers.in/sym_details/NSE_CM.csv"
INDICES = ["NSE:NIFTY50-INDEX", "NSE:NIFTY500-INDEX", "NSE:NIFTYBANK-INDEX",
           "NSE:NIFTYMIDCAP100-INDEX", "NSE:NIFTYSMLCAP100-INDEX"]
CHUNK_DAYS = 360          # Fyers allows ~366 days per daily-resolution request
MIN_INTERVAL = 0.3        # seconds between calls (limit is 10/s, 200/min)


def universe() -> list:
    """All NSE cash-market EQ series symbols from the Fyers symbol master."""
    path = DATA / "NSE_CM.csv"
    if not path.exists() or time.time() - path.stat().st_mtime > 7 * 86400:
        import requests
        DATA.mkdir(exist_ok=True)
        path.write_bytes(requests.get(MASTER_URL, timeout=60).content)
    m = pd.read_csv(path, header=None)
    # equities only: ISIN INE...; ETFs / MF units carry INF... ISINs
    syms = m[9][m[9].str.endswith("-EQ") & m[5].astype(str).str.startswith("INE")].tolist()
    return sorted(set(syms))


def _file(sym: str) -> Path:
    return PRICES / (sym.replace(":", "_").replace("&", "and") + ".parquet")


def _fetch(fyers, sym: str, start: date, end: date) -> pd.DataFrame:
    frames, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=CHUNK_DAYS), end)
        for attempt in range(4):
            time.sleep(MIN_INTERVAL)
            r = fyers.history({"symbol": sym, "resolution": "D", "date_format": "1",
                               "range_from": cur.isoformat(), "range_to": stop.isoformat(),
                               "cont_flag": "1"})
            if r.get("s") == "ok":
                break
            if r.get("code") == 429 or "limit" in str(r.get("message", "")).lower():
                time.sleep(15 * (attempt + 1))
                continue
            r = {"candles": []}   # no data for this window (unlisted then, etc.)
            break
        if r.get("candles"):
            frames.append(pd.DataFrame(r["candles"], columns=["ts", "open", "high", "low", "close", "volume"]))
        cur = stop + timedelta(days=1)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames)
    # Fyers daily bars are stamped at IST midnight expressed as epoch; convert to a plain date
    df["date"] = pd.to_datetime(df["ts"], unit="s").dt.normalize()
    return df.drop(columns="ts").drop_duplicates("date").set_index("date").sort_index()


def update(symbols: list, years: int, fyers, quiet: bool = False) -> None:
    PRICES.mkdir(parents=True, exist_ok=True)
    # only completed sessions: before 16:00 IST today's bar is still forming
    now = datetime.now()
    today = date.today() if now.hour >= 16 else date.today() - timedelta(days=1)
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        f = _file(sym)
        old = pd.read_parquet(f) if f.exists() else None
        start = (old.index[-1].date() + timedelta(days=1)) if old is not None and len(old) \
            else today - timedelta(days=365 * years)
        if start > today:
            continue
        new = _fetch(fyers, sym, start, today)
        if not new.empty:
            new = new[new.index <= pd.Timestamp(today)]
        if new.empty and old is None:
            continue
        df = pd.concat([old, new]) if old is not None else new
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df.to_parquet(f)
        if not quiet and (i % 25 == 0 or i == len(symbols)):
            el = time.time() - t0
            print(f"[{i}/{len(symbols)}] {sym} bars={len(df)}  elapsed {el/60:.1f}m  "
                  f"eta {el/i*(len(symbols)-i)/60:.1f}m", flush=True)


def backfill(symbols: list, since: date, fyers, quiet: bool = False) -> None:
    """Extend stored history back to `since` (fetches only the missing older part)."""
    PRICES.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        f = _file(sym)
        old = pd.read_parquet(f) if f.exists() else None
        end = (old.index[0].date() - timedelta(days=1)) if old is not None and len(old) else date.today()
        if end < since or f.with_suffix(".bf").exists():
            continue
        # listed after the 3-year window began -> no older history exists; skip the empty calls
        if old is not None and len(old) and old.index[0].date() > date.today() - timedelta(days=365 * 3 - 20):
            f.with_suffix(".bf").touch()
            continue
        new = _fetch(fyers, sym, since, end)
        cur = pd.read_parquet(f) if f.exists() else None      # the forward job may have written meanwhile
        df = pd.concat([new, cur]) if cur is not None else new
        if not df.empty:
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.to_parquet(f)
        f.with_suffix(".bf").touch()                           # marker: done (even if no older data)
        if not quiet and (i % 25 == 0 or i == len(symbols)):
            el = time.time() - t0
            print(f"[{i}/{len(symbols)}] {sym} bars={len(df)}  elapsed {el/60:.1f}m  "
                  f"eta {el/i*(len(symbols)-i)/60:.1f}m", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="only first N symbols (testing)")
    ap.add_argument("--backfill-from", default="", help="YYYY-MM-DD: extend history backwards")
    ap.add_argument("--reverse", action="store_true")
    a = ap.parse_args()
    fy = get_client()
    syms = INDICES + universe()
    if a.limit:
        syms = INDICES + universe()[: a.limit]
    if a.reverse:
        syms = syms[::-1]
    if a.backfill_from:
        # forward-fill each symbol first (so recent listings are recognised), then extend back
        print(f"{len(syms)} symbols, 3y update + backfill from {a.backfill_from}", flush=True)
        since, t0 = date.fromisoformat(a.backfill_from), time.time()
        for i, sym in enumerate(syms, 1):
            update([sym], a.years, fy, quiet=True)
            backfill([sym], since, fy, quiet=True)
            if i % 25 == 0:
                el = time.time() - t0
                print(f"[{i}/{len(syms)}] {sym} elapsed {el/60:.1f}m eta {el/i*(len(syms)-i)/60:.1f}m", flush=True)
    else:
        print(f"{len(syms)} symbols, {a.years}y history", flush=True)
        update(syms, a.years, fy)
    print("done", datetime.now().isoformat(timespec="seconds"), flush=True)
