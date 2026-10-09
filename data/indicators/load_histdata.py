"""HistData.com SPXUSD 1-minute zips -> one 5-minute parquet.

HistData says EST without daylight saving, but the data follows New York local time WITH DST:
the daily break sits at 16:15-18:00 in both January and July, and only that matches ES futures
(5m return corr 0.95 vs -0.02 with a fixed UTC-5 offset).
Usage: python load_histdata.py <folder with DAT_ASCII_SPXUSD_M1_*.zip> <out.parquet>
"""
import sys, glob, zipfile, pandas as pd

src, out = sys.argv[1], sys.argv[2]
parts = []
for z in sorted(glob.glob(src + r"\DAT_ASCII_SPXUSD_M1_*.zip")):
    with zipfile.ZipFile(z) as f:
        name = [n for n in f.namelist() if n.endswith(".csv")][0]
        df = pd.read_csv(f.open(name), sep=";", header=None, names=["t", "Open", "High", "Low", "Close", "Volume"])
    df.index = pd.to_datetime(df.t, format="%Y%m%d %H%M%S").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    parts.append(df.drop(columns="t")[df.index.notna()])
    print(f"{z.split(chr(92))[-1]}: {len(df):,} 1m bars {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}", flush=True)
m1 = pd.concat(parts).sort_index()
m1 = m1[~m1.index.duplicated(keep="last")]
m5 = m1.resample("5min", label="left", closed="left").agg(
    {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna(subset=["Open"])
m5.to_parquet(out)
print(f"5m bars: {len(m5):,}  {m5.index[0]} -> {m5.index[-1]}  -> {out}")
