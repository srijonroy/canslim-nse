"""NOISE intraday momentum on any market with a defined cash session (HistData M1 zips).

Same rules as noise_5m.txt / us500_systems.py: bands = 14-day average |move from the open| at that time
of day around max/min(open, prev close); checks every 30 min from 30 min after the open to 30 min before
the close; exit back inside max/min(band, session average price); flat at the session close.
HistData timestamps are New York local time (DST-aware) - verified on SPX vs ES futures.
Usage: python noise_multi.py
"""
import glob, zipfile, numpy as np, pandas as pd

SRC = {"spxusd": r"C:\Project\asd\data\us500\histdata", "default": r"C:\Project\asd\data\markets\histdata"}
# name: (histdata pair, session tz, open "HH:MM", close "HH:MM", Pepperstone spread in points)
MARKETS = {
    "US500":  ("spxusd", "America/New_York", "09:30", "16:00", 0.4),
    "NAS100": ("nsxusd", "America/New_York", "09:30", "16:00", 1.0),
    "XAUUSD": ("xauusd", "America/New_York", "08:20", "13:30", 0.2),
}
SPLIT, START = "2019-01-01", "2011-09-01"

def load_m1(pair):
    parts = []
    for z in sorted(glob.glob(SRC.get(pair, SRC["default"]) + rf"\DAT_ASCII_{pair.upper()}_M1_*.zip")):
        with zipfile.ZipFile(z) as f:
            df = pd.read_csv(f.open([n for n in f.namelist() if n.endswith(".csv")][0]), sep=";", header=None,
                             names=["t", "Open", "High", "Low", "Close", "Volume"])
        df.index = pd.to_datetime(df.t, format="%Y%m%d %H%M%S").dt.tz_localize(
            "America/New_York", ambiguous="NaT", nonexistent="NaT")
        parts.append(df[df.index.notna()].drop(columns="t"))
    m1 = pd.concat(parts).sort_index()
    return m1[~m1.index.duplicated(keep="last")]

def noise(m1, tz, t0, t1, spread):
    m1 = m1.tz_convert(tz)
    a = int(t0[:2]) * 60 + int(t0[3:]); b = int(t1[:2]) * 60 + int(t1[3:]); nslot = (b - a) // 5
    m5 = m1.resample("5min").agg({"Open": "first", "Close": "last"}).dropna()
    mm = m5.index.hour * 60 + m5.index.minute
    s = m5[(mm >= a) & (mm < b) & (m5.index.dayofweek < 5)].copy()
    s["date"] = s.index.normalize().tz_localize(None); s["slot"] = ((s.index.hour * 60 + s.index.minute) - a) // 5
    O = s.pivot_table(index="date", columns="slot", values="Open").reindex(columns=range(nslot))
    C = s.pivot_table(index="date", columns="slot", values="Close").reindex(columns=range(nslot))
    ok = O.notna().sum(axis=1) >= 0.9 * nslot
    O, C = O[ok].ffill(axis=1).bfill(axis=1), C[ok].ffill(axis=1).bfill(axis=1)
    days = O.index; o, c = O.to_numpy(), C.to_numpy()
    dopen, dclose = o[:, 0], c[:, -1]; prevc = np.r_[np.nan, dclose[:-1]]
    cost = spread / np.nanmedian(dclose[days >= "2026-01-01"])         # spread as a fraction of price
    sigma = pd.DataFrame(np.abs(c / dopen[:, None] - 1)).rolling(14).mean().shift(1).to_numpy()
    up = np.maximum(dopen, prevc)[:, None] * (1 + sigma); dn = np.minimum(dopen, prevc)[:, None] * (1 - sigma)
    avgp = np.cumsum(c, axis=1) / np.arange(1, nslot + 1)
    checks = list(range(5, nslot - 6, 6))
    tr = []
    for k in range(len(days)):
        if np.isnan(sigma[k, 0]) or np.isnan(prevc[k]) or days[k] < pd.Timestamp(START): continue
        pos = 0
        for j in checks:
            px = c[k, j]
            if pos == 1 and px < max(up[k, j], avgp[k, j]) or pos == -1 and px > min(dn[k, j], avgp[k, j]):
                tr.append((days[k], pos * (o[k, j + 1] / e - 1) - cost)); pos = 0
            if pos == 0:
                new = 1 if px > up[k, j] else -1 if px < dn[k, j] else 0
                if new: pos, e = new, o[k, j + 1]
        if pos: tr.append((days[k], pos * (c[k, -1] / e - 1) - cost))
    t = pd.DataFrame(tr, columns=["date", "r"])
    return t, len(days[days >= START]), 1e4 * cost

def report(name, t, ndays, cost_bp):
    w, l = t.r[t.r > 0], t.r[t.r <= 0]
    a, b = t[t.date < SPLIT], t[t.date >= SPLIT]
    yrs = t.groupby(t.date.dt.year).r.sum()
    return dict(market=name, cost_bp=round(cost_bp, 2), trades_yr=round(len(t) / (ndays / 252)), win=f"{100*len(w)/len(t):.0f}%",
                avgW_bp=round(1e4 * w.mean(), 1), avgL_bp=round(1e4 * l.mean(), 1), PF=round(w.sum() / -l.sum(), 2),
                pct_yr_1x=f"{100*t.r.sum()/(ndays/252):.1f}%", PF_11_18=round(a.r[a.r > 0].sum() / -a.r[a.r <= 0].sum(), 2),
                PF_19_26=round(b.r[b.r > 0].sum() / -b.r[b.r <= 0].sum(), 2), years_pos=f"{(yrs > 0).sum()}/{len(yrs)}")

if __name__ == "__main__":
    rows, per_year = [], {}
    for name, (pair, tz, t0, t1, spread) in MARKETS.items():
        try:
            m1 = load_m1(pair)
        except ValueError:
            print(name, "no data yet"); continue
        print(f"{name}: {len(m1):,} 1m bars {m1.index[0]:%Y-%m-%d} -> {m1.index[-1]:%Y-%m-%d}", flush=True)
        t, nd, cbp = noise(m1, tz, t0, t1, spread)
        r = report(name, t, nd, cbp)
        t2, _, _ = noise(m1, tz, t0, t1, 2 * spread)
        r["PF_2x_cost"] = round(t2.r[t2.r > 0].sum() / -t2.r[t2.r <= 0].sum(), 2)
        rows.append(r); per_year[name] = (100 * t.groupby(t.date.dt.year).r.sum()).round(1)
        t.to_csv(rf"C:\Project\asd\data\markets\noise_trades_{name}.csv", index=False)
    pd.set_option("display.width", 220)
    print("\nNOISE intraday momentum, 1x size, after spread. PF = profit factor; design 2011-18, hold-out 2019-26")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n% return per year at 1x size"); print(pd.DataFrame(per_year).to_string())
