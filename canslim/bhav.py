"""Every NSE stock's daily bars from the official bhavcopies in data/bhavcopy (2005+), INCLUDING stocks that later
delisted or merged - the Fyers price files only hold stocks listed today. Cached as one long table.

Series kept: EQ (normal), BE/BZ (trade-to-trade, where weak or penalised stocks often end their life).

usage: from canslim import bhav; df = bhav.load()      # date, sym, series, isin, open, high, low, close, volume, value
"""
import io
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BHAV = ROOT / "data" / "bhavcopy"
CACHE = ROOT / "data" / "cache" / "bhav_eq.parquet"
SERIES = ("EQ", "BE", "BZ")
NEW = {"TckrSymb": "SYMBOL", "SctySrs": "SERIES", "OpnPric": "OPEN", "HghPric": "HIGH", "LwPric": "LOW",
       "ClsPric": "CLOSE", "TtlTradgVol": "TOTTRDQTY", "TtlTrfVal": "TOTTRDVAL", "TradDt": "DATE"}


def read_day(f: Path) -> pd.DataFrame:
    with zipfile.ZipFile(f) as z:
        x = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), dtype=str)
    x.columns = [c.strip() for c in x.columns]
    x = x.rename(columns=NEW)
    x["SERIES"] = x["SERIES"].str.strip()
    x = x[x["SERIES"].isin(SERIES)]
    out = pd.DataFrame({"date": pd.Timestamp(f.name[:8]), "sym": x["SYMBOL"].str.strip(),
                        "series": x["SERIES"], "isin": x.get("ISIN", pd.Series(dtype=str)).str.strip()})
    for k, c in (("open", "OPEN"), ("high", "HIGH"), ("low", "LOW"), ("close", "CLOSE"),
                 ("volume", "TOTTRDQTY"), ("value", "TOTTRDVAL")):
        out[k] = pd.to_numeric(x[c], errors="coerce").astype("float32")
    return out


def load(start="2014-01-01", refresh=False) -> pd.DataFrame:
    files = sorted(f for y in BHAV.iterdir() if y.is_dir() for f in y.glob("*.csv.zip") if f.name[:8] >= start.replace("-", ""))
    if CACHE.exists() and not refresh:
        df = pd.read_parquet(CACHE)
        have = set(df.date.dt.strftime("%Y%m%d").unique())
        files = [f for f in files if f.name[:8] not in have]
    else:
        df = None
    if files:
        print(f"reading {len(files)} bhavcopies ...", flush=True)
        parts = []
        for i, f in enumerate(files, 1):
            try:
                parts.append(read_day(f))
            except Exception as e:                       # a broken download should not stop the build
                print(f"  skip {f.name}: {e}", flush=True)
            if i % 500 == 0:
                print(f"  {i}/{len(files)}", flush=True)
        new = pd.concat(parts, ignore_index=True)
        df = new if df is None else pd.concat([df, new], ignore_index=True)
        for c in ("sym", "series", "isin"):
            df[c] = df[c].astype("category")
        df = df.sort_values(["sym", "date"], kind="stable").reset_index(drop=True)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(CACHE)
    return df
