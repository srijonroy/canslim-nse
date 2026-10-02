"""NSE index history: daily OHLC + volume + turnover + P/E, P/B, dividend yield. Standalone (not part of canslim).

Sources
  1) NSE archive ind_close_all_DDMMYYYY.csv  -- every NSE index, one file per day, Jul 2012 -> today.
     Columns: open, high, low, close, volume, turnover (Rs cr), pe, pb, div_yield.  Plain download, no login.
  2) niftyindices.com historical data         -- OHLC only (no volume is published), 2005 -> Jul 2012.
     Needs the debug Chrome on :9222 (Akamai blocks plain scripts).

Output
  data/indices/raw/YYYY/ind_close_all_DDMMYYYY.csv   cached daily files (never re-downloaded)
  data/indices/<INDEX NAME>.parquet                  one file per index, 2005 -> today
  data/indices/_all.parquet                          everything, long format

usage: python indexdata.py              (download what is missing, then rebuild the parquet files)
       python indexdata.py --no-old     (skip the 2005-2012 niftyindices part)
"""
import argparse
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "indices"
RAW = OUT / "raw"
OLD = OUT / "old"
START_ARCHIVE = pd.Timestamp("2012-07-01")
START_OLD = pd.Timestamp("2005-01-01")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
COLS = {"Index Name": "index", "Index Date": "date", "Open Index Value": "open", "High Index Value": "high",
        "Low Index Value": "low", "Closing Index Value": "close", "Volume": "volume",
        "Turnover (Rs. Cr.)": "turnover_cr", "P/E": "pe", "P/B": "pb", "Div Yield": "div_yield"}
# names used before NSE renamed CNX -> Nifty (2015); everything else maps by upper-casing
RENAME = {"S&P CNX NIFTY": "NIFTY 50", "CNX NIFTY": "NIFTY 50", "S&P CNX 500": "NIFTY 500", "CNX 500": "NIFTY 500",
          "CNX NIFTY JUNIOR": "NIFTY NEXT 50", "NIFTY JUNIOR": "NIFTY NEXT 50", "CNX 100": "NIFTY 100",
          "CNX 200": "NIFTY 200", "CNX MIDCAP": "NIFTY MIDCAP 100", "NIFTY MIDCAP": "NIFTY MIDCAP 100",
          "CNX SMALLCAP": "NIFTY SMALLCAP 100", "NIFTY SMALLCAP": "NIFTY SMALLCAP 100",
          "CNX MIDCAP 200": "NIFTY MIDCAP 150", "BANK NIFTY": "NIFTY BANK", "CNX BANK": "NIFTY BANK",
          "NIFTY FREE FLOAT SMALLCAP 100": "NIFTY SMALLCAP 100", "NIFTY FREE FLOAT MIDCAP 100": "NIFTY MIDCAP 100",
          "CNX FREE FLOAT SMALLCAP 100": "NIFTY SMALLCAP 100", "CNX FREE FLOAT MIDCAP 100": "NIFTY MIDCAP 100",
          "INDIA VIX": "INDIA VIX", "S&P CNX DEFTY": "NIFTY DEFTY"}
_s = requests.Session()
_s.headers.update(UA)


def fname(name: str) -> str:
    return re.sub(r'[<>:"/\|?*]', "_", name)


def norm(name: str) -> str:
    n = re.sub(r"\s+", " ", str(name).strip().upper())
    if n in RENAME:
        return RENAME[n]
    n = n.replace("S&P ", "")
    if n.startswith("CNX NIFTY"):
        n = n[4:]
    return RENAME.get(n, n.replace("CNX ", "NIFTY ", 1) if n.startswith("CNX ") else n)


# ---------- 1) NSE daily archive, Jul 2012 -> today ----------
def _day(d: pd.Timestamp):
    f = RAW / f"{d.year}" / f"ind_close_all_{d:%d%m%Y}.csv"
    if f.exists():
        return d, "cached"
    for i in range(3):
        try:
            r = _s.get(f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv", timeout=30)
            if r.status_code == 404 or not r.text.startswith("Index"):
                return d, "none"                       # holiday / no file
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(r.text, encoding="utf-8")
            return d, "new"
        except Exception:
            time.sleep(2 * (i + 1))
    return d, "error"


def download_archive(workers=4):
    days = pd.bdate_range(START_ARCHIVE, pd.Timestamp.today().normalize())
    seen_none = OUT / "_no_file_days.txt"            # holidays found earlier, so they are not re-tried
    skip = set(seen_none.read_text().split()) if seen_none.exists() else set()
    todo = [d for d in days if f"{d:%Y-%m-%d}" not in skip]
    print(f"archive: {len(days)} weekdays since {START_ARCHIVE:%b %Y}, {len(todo)} to check", flush=True)
    n = {"new": 0, "cached": 0, "none": 0, "error": 0}
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for i, (d, st) in enumerate(ex.map(_day, todo), 1):
            n[st] += 1
            if st == "none" and d < pd.Timestamp.today().normalize() - pd.Timedelta(days=3):
                skip.add(f"{d:%Y-%m-%d}")
            if i % 250 == 0 or i == len(todo):
                print(f"  [{i}/{len(todo)}] up to {d:%Y-%m-%d}: {n}  ({time.time() - t0:.0f}s)", flush=True)
    seen_none.write_text("\n".join(sorted(skip)))


def read_archive() -> pd.DataFrame:
    fr = []
    for f in sorted(RAW.rglob("*.csv")):
        try:
            x = pd.read_csv(f, dtype=str)
        except Exception:
            continue
        x = x.rename(columns={c: COLS.get(c.strip(), c.strip()) for c in x.columns})
        fr.append(x[[c for c in COLS.values() if c in x.columns]])
    a = pd.concat(fr, ignore_index=True)
    a["date"] = pd.to_datetime(a["date"], dayfirst=True, errors="coerce")
    for c in ["open", "high", "low", "close", "volume", "turnover_cr", "pe", "pb", "div_yield"]:
        a[c] = pd.to_numeric(a[c].str.replace(",", "").str.strip().replace({"-": None}), errors="coerce")
    a["raw_name"] = a["index"]
    a["index"] = a["index"].map(norm)
    a["source"] = "nse_archive"
    return a.dropna(subset=["date", "close"])


# ---------- 2) niftyindices.com OHLC, 2005 -> Jul 2012 ----------
JS = """async ([u, body]) => { const r = await fetch(u, {method: 'POST', body: body,
          headers: {'Content-Type': 'application/json; charset=utf-8', 'X-Requested-With': 'XMLHttpRequest'}});
          return [r.status, await r.text()]; }"""


GAPS = [("01-Apr-2015", "15-Jun-2015")]          # NSE archive has no files for most of Apr-Jun 2015


def download_old(names, ranges=None, tag=""):
    from playwright.sync_api import sync_playwright
    OLD.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        pg = b.contexts[0].new_page()
        pg.goto("https://www.niftyindices.com/reports/historical-data", timeout=90000)
        pg.wait_for_timeout(4000)
        for k, nm in enumerate(names, 1):
            f = OLD / f"{tag}{fname(nm)}.json"
            if f.exists():
                continue
            rows = []
            for a, e in ranges or [(f"01-Jan-{y}", f"31-Dec-{y}") for y in range(START_OLD.year, START_ARCHIVE.year + 1)]:
                ci = json.dumps({"name": nm, "startDate": a, "endDate": e,
                                 "indexName": nm}).replace('"', "'")
                try:
                    st, t = pg.evaluate(JS, ["https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString",
                                             json.dumps({"cinfo": ci})])
                    rows += json.loads(t) if st == 200 and t.startswith("[") else []
                except Exception as e:
                    print(f"  {nm} {a}: {e}", flush=True)
            f.write_text(json.dumps(rows))
            print(f"  old [{k}/{len(names)}] {nm:<40} {len(rows)} days", flush=True)
        pg.close()


def read_old() -> pd.DataFrame:
    fr = []
    for f in OLD.glob("*.json"):
        j = json.loads(f.read_text())
        if j:
            x = pd.DataFrame(j)
            fr.append(pd.DataFrame({"index": x["INDEX_NAME"].map(norm), "raw_name": x["INDEX_NAME"],
                                    "date": pd.to_datetime(x["HistoricalDate"], format="%d %b %Y", errors="coerce"),
                                    **{c: pd.to_numeric(x[c.upper()].str.replace(",", ""), errors="coerce")
                                       for c in ["open", "high", "low", "close"]}}))
    if not fr:
        return pd.DataFrame()
    o = pd.concat(fr, ignore_index=True)
    o["source"] = "niftyindices"
    return o.dropna(subset=["date", "close"])                    # archive rows win on overlapping days


def build():
    a = read_archive()
    o = read_old()
    al = pd.concat([o, a], ignore_index=True)
    al["prio"] = (al.source == "nse_archive").astype(int)            # archive wins where both exist
    al = (al.sort_values(["index", "date", "prio"]).drop_duplicates(["index", "date"], keep="last")
            .drop(columns="prio").reset_index(drop=True))
    # bad prints in NSE's files: a one-day jump of >= 8% that fully reverses the next day (within 2%) -> flagged, OHLC blanked
    r = al.groupby("index").close.pct_change()
    nxt = al.groupby("index").close.shift(-1) / al.groupby("index").close.shift(1) - 1
    al["bad_print"] = (r.abs() >= 0.08) & (nxt.abs() < 0.02) & (al["index"] != "INDIA VIX")
    al.loc[al.bad_print, ["open", "high", "low", "close"]] = None
    print(f"bad prints blanked: {int(al.bad_print.sum())}", al.loc[al.bad_print, ["index", "date"]].head(10).values.tolist())
    al.to_parquet(OUT / "_all.parquet")
    for nm, g in al.groupby("index"):
        g.drop(columns="index").set_index("date").to_parquet(OUT / f"{fname(nm)}.parquet")
    s = al.groupby("index").agg(first=("date", "min"), last=("date", "max"), days=("date", "size"),
                                vol_from=("date", lambda d: d[al.loc[d.index, "volume"].fillna(0) > 0].min()))
    s.to_csv(OUT / "_summary.csv")
    print(f"\n{len(s)} indices -> {OUT}")
    print(s.loc[[i for i in ["NIFTY 50", "NIFTY 500", "NIFTY NEXT 50", "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100",
                             "NIFTY BANK", "INDIA VIX"] if i in s.index]].to_string())
    return al


# ---------- 3) whole-market volume and breadth from NSE stock bhavcopies, 2005 -> today ----------
# No index volume exists before Jul 2012, so this is the substitute (and what O'Neil uses: exchange volume).
BHAV = ROOT / "data" / "bhavcopy"
NEW_FMT = pd.Timestamp("2024-07-08")                # NSE switched to the UDiFF bhavcopy on this day
EQ_SERIES = {"EQ", "BE", "BZ"}                      # ordinary equity, trade-for-trade; excludes bonds, ETFs, SME


def _bhav_url(d):
    if d >= NEW_FMT:
        return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    mon = d.strftime("%b").upper()
    return f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{d.year}/{mon}/cm{d:%d}{mon}{d.year}bhav.csv.zip"


def _bhav_day(d):
    f = BHAV / f"{d.year}" / f"{d:%Y%m%d}.csv.zip"
    if f.exists():
        return d, "cached"
    for i in range(3):
        try:
            r = _s.get(_bhav_url(d), timeout=30)
            if r.status_code == 404 or r.content[:2] != b"PK":
                return d, "none"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(r.content)
            return d, "new"
        except Exception:
            time.sleep(2 * (i + 1))
    return d, "error"


def download_bhav(start="2005-01-01", workers=4):
    days = pd.bdate_range(start, pd.Timestamp.today().normalize())
    seen_none = BHAV / "_no_file_days.txt"
    BHAV.mkdir(parents=True, exist_ok=True)
    skip = set(seen_none.read_text().split()) if seen_none.exists() else set()
    todo = [d for d in days if f"{d:%Y-%m-%d}" not in skip]
    print(f"bhavcopy: {len(todo)} weekdays to check since {start}", flush=True)
    n = {"new": 0, "cached": 0, "none": 0, "error": 0}
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for i, (d, st) in enumerate(ex.map(_bhav_day, todo), 1):
            n[st] += 1
            if st == "none" and d < pd.Timestamp.today().normalize() - pd.Timedelta(days=3):
                skip.add(f"{d:%Y-%m-%d}")
            if i % 500 == 0 or i == len(todo):
                print(f"  bhav [{i}/{len(todo)}] up to {d:%Y-%m-%d}: {n}  ({time.time() - t0:.0f}s)", flush=True)
    seen_none.write_text("\n".join(sorted(skip)))


def _bhav_read(f) -> pd.DataFrame:
    import zipfile
    with zipfile.ZipFile(f) as z:
        x = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), dtype=str)
    x.columns = [c.strip() for c in x.columns]
    if "TckrSymb" in x.columns:                                         # new format
        x = x.rename(columns={"TckrSymb": "SYMBOL", "SctySrs": "SERIES", "ClsPric": "CLOSE",
                              "PrvsClsgPric": "PREVCLOSE", "TtlTradgVol": "TOTTRDQTY", "TtlTrfVal": "TOTTRDVAL",
                              "TtlNbOfTxsExctd": "TOTALTRADES"})
    x["SERIES"] = x["SERIES"].str.strip()
    x = x[x["SERIES"].isin(EQ_SERIES)]
    for c in ["CLOSE", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TOTALTRADES"]:
        x[c] = pd.to_numeric(x.get(c), errors="coerce")
    return x


def build_market():
    rows = []
    for f in sorted(BHAV.rglob("*.csv.zip")):
        x = _bhav_read(f)
        ch = x["CLOSE"] - x["PREVCLOSE"]
        rows.append({"date": pd.Timestamp(f.name[:8]), "stocks": len(x), "volume": x["TOTTRDQTY"].sum(),
                     "turnover_cr": round(x["TOTTRDVAL"].sum() / 1e7, 2),
                     "trades": x["TOTALTRADES"].sum() if x["TOTALTRADES"].notna().any() else None,
                     "advances": int((ch > 0).sum()), "declines": int((ch < 0).sum()),
                     "unchanged": int((ch == 0).sum())})
    m = pd.DataFrame(rows).set_index("date").sort_index()
    m.to_parquet(OUT / "_market_volume.parquet")
    print(f"\nmarket volume/breadth: {len(m)} days {m.index.min():%Y-%m-%d} -> {m.index.max():%Y-%m-%d} "
          f"-> {OUT / '_market_volume.parquet'}")
    print(m.iloc[[0, len(m) // 2, -1]].to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-old", action="store_true")
    ap.add_argument("--market-only", action="store_true", help="only the whole-market volume/breadth part")
    ap.add_argument("--no-market", action="store_true")
    a = ap.parse_args()
    if not a.market_only:
        RAW.mkdir(parents=True, exist_ok=True)
        download_archive()
        if not a.no_old:
            names = sorted(read_archive()["index"].unique())
            print(f"niftyindices: OHLC 2005-2012 for {len(names)} indices", flush=True)
            download_old(names)
            in_2015 = sorted(read_archive().query("date.dt.year == 2015")["index"].unique())
            download_old(in_2015, GAPS, tag="gap2015_")
        build()
    if not a.no_market:
        download_bhav()
        build_market()


if __name__ == "__main__":
    main()
