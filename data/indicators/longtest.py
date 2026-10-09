"""Long-history re-run of the Always-In tests (filter, follow-through, pyramiding), year by year.

Cost = 0.4 pt per unit at a 6700 index level (Pepperstone US500 spread), scaled with price.
Fixed-size results are in basis points of price; risk-sized results are in R (= % of account at 1% risk,
stop at the signal bar's extreme).
Usage: python longtest.py <5m parquet>
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Project\asd\data\indicators")
from aitest import indicator, range_filter

d = pd.read_parquet(sys.argv[1])
d.index = d.index.tz_convert("Asia/Kolkata")
x = indicator(d)
o, h, l, c, atr, idx = x["o"], x["h"], x["l"], x["c"], x["atr"], d.index
cost = 0.4 * c / 6700
mins = idx.hour * 60 + idx.minute
filt = range_filter(x, minCross=3); filt[np.asarray((mins >= 90) & (mins < 750))] = 0

def run(pos):
    """One row per signal with every variant's result."""
    rows, n = [], len(pos)
    for i in range(1, n - 3):
        s = pos[i]
        if s == 0 or s == pos[i - 1]: continue
        j = i + 1
        while j < n - 1 and pos[j] == s: j += 1
        if j >= n - 1: break
        k, ex, e0 = cost[i], o[j + 1], o[i + 1]
        ft = s * (c[i + 1] - c[i]) > 0 and pos[i + 1] == s and j > i + 1
        bp = lambda e: 1e4 * (s * (ex - e) - k) / e0
        r = dict(t=idx[i], now=bp(e0), ft=ft, wait=bp(o[i + 2]) if ft else np.nan,
                 cut=bp(e0) if ft else 1e4 * (s * (o[i + 2] - e0) - k) / e0)
        stop0 = l[i] if s == 1 else h[i]
        R = max(s * (e0 - stop0), 0.25 * atr[i])
        r["R_nostop"] = (s * (ex - e0) - k) / R
        for ma in (0, 1, 2, 3):
            stop = e0 - s * R; entries = [e0]; xp = None; b = i + 1
            while b <= j:
                if s * (stop - (l[b] if s == 1 else h[b])) >= 0:
                    xp = o[b] if s * (o[b] - stop) <= 0 else stop; break
                if b < j and len(entries) <= ma and s * (c[b] - e0) >= len(entries) * R:
                    entries.append(o[b + 1])
                    cap = (sum(entries) - s * R) / len(entries)
                    stop = max(entries[-2], cap) if s == 1 else min(entries[-2], cap)
                b += 1
            if xp is None: xp = ex
            r[f"P{ma}"] = sum(s * (xp - e) - k for e in entries) / R
        rows.append(r)
    return pd.DataFrame(rows)

def summ(p):
    p = p.dropna()
    if p.empty: return dict(n=0)
    w, lo = p[p > 0], p[p <= 0]; eq = p.cumsum()
    return dict(n=len(p), win=round(100 * len(w) / len(p)), avg=round(p.mean(), 2), total=round(p.sum(), 1),
                pf=round(w.sum() / -lo.sum(), 2) if len(lo) else np.inf, maxdd=round((eq - eq.cummax()).min(), 1))

pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
print(f"SPX 5m {idx[0]:%Y-%m-%d} -> {idx[-1]:%Y-%m-%d}, {len(idx):,} bars")
for name, pos in (("FILTERED (v2 default)", filt), ("RAW Always-In", x["ai"])):
    t = run(pos); t["year"] = t.t.dt.year
    V = {"A now (bp)": t.now, "  FT signals, enter now (bp)": t.now[t.ft], "  no-FT signals (bp)": t.now[~t.ft],
         "B wait for FT (bp)": t.wait, "D now, cut if no FT (bp)": t.cut,
         "A' 1% risk, no stop (R)": t.R_nostop, "B' 1% risk + stop (R)": t.P0,
         "P1 +1 add (R)": t.P1, "P2 +2 adds (R)": t.P2, "P3 +3 adds (R)": t.P3}
    print(f"\n=================== {name}: whole period")
    print(pd.DataFrame({k: summ(v) for k, v in V.items()}).T.to_string())
    print(f"\n{name}: total per year")
    yt = pd.DataFrame({k: v.groupby(t.year[v.index]).sum().round(0) for k, v in V.items() if not k.startswith("  ")})
    yt.loc["years > 0"] = (yt > 0).sum().astype(str) + "/" + str(len(yt))
    print(yt.to_string())
