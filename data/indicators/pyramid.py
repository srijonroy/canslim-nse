"""Hougaard-style pyramiding on Always-In signals, results in R (= % of account at 1% risk).

Initial stop = signal bar's low (long) / high (short); 1R = entry - stop.
Add 1 unit each time a bar closes another +1R beyond the first entry (filled next open);
on each add the whole position's stop moves to the previous entry price, or tighter if needed so the
whole position never risks more than 1R (big bars can fill an add far beyond +1R).
Exit: stop hit (at stop, or at the open if gapped through) or the state leaves that side (next open).
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Project\asd\data\indicators")
from aitest import indicator, range_filter, COST

d = pd.read_parquet(sys.argv[1])
d.index = d.index.tz_convert("Asia/Kolkata")
x = indicator(d)
o, h, l, c, atr, idx = x["o"], x["h"], x["l"], x["c"], x["atr"], d.index
mins = idx.hour * 60 + idx.minute
filt = range_filter(x, minCross=3); filt[np.asarray((mins >= 90) & (mins < 750))] = 0

def trades(pos, use_stop=True, max_adds=0):
    rows, n = [], len(pos)
    for i in range(1, n - 3):
        s = pos[i]
        if s == 0 or s == pos[i - 1]: continue
        j = i + 1
        while j < n - 1 and pos[j] == s: j += 1
        if j >= n - 1: break
        e0 = o[i + 1]
        stop = l[i] if s == 1 else h[i]
        R = max(s * (e0 - stop), 0.25 * atr[i])           # floor: entry gapped past the signal bar
        stop = e0 - s * R
        entries = [e0]; ex = None; b = i + 1
        while b <= j:
            if use_stop and s * (stop - (l[b] if s == 1 else h[b])) >= 0:   # stop touched this bar
                ex = o[b] if s * (o[b] - stop) <= 0 else stop
                break
            if b < j and len(entries) <= max_adds and s * (c[b] - e0) >= len(entries) * R:
                entries.append(o[b + 1])
                cap = (sum(entries) - s * R) / len(entries)   # stop where the whole position loses exactly 1R
                stop = max(entries[-2], cap) if s == 1 else min(entries[-2], cap)  # previous entry, or tighter
            b += 1
        if ex is None: ex = o[j + 1]
        pts = sum(s * (ex - e) - COST for e in entries)
        rows.append(dict(t=idx[i], r=pts / R, adds=len(entries) - 1))
    return pd.DataFrame(rows)

def st(p):
    w, lo = p[p > 0], p[p <= 0]; eq = p.cumsum(); dd = -(eq - eq.cummax()).min()
    return (f"{100*len(w)/len(p):>5.0f}%{w.mean():>7.2f}{lo.mean():>7.2f}{w.mean()/-lo.mean():>6.2f}"
            f"{w.sum()/-lo.sum():>6.2f}{p.sum():>8.1f}{-dd:>8.1f}{p.sum()/dd:>7.2f}{p.max():>7.1f}{p.min():>7.1f}")

half = idx[len(idx) // 2]
V = [("A no stop, exit on flip (today)", False, 0), ("B stop at signal bar, no adds", True, 0),
     ("P1 stop + up to 1 add", True, 1), ("P2 stop + up to 2 adds", True, 2),
     ("P3 stop + up to 3 adds", True, 3), ("P5 stop + up to 5 adds", True, 5)]
print(f"ES 5m {idx[0]:%d %b} -> {idx[-1]:%d %b %Y}, cost {COST} pt per unit. Units: R = % of account at 1% risk")
for name, pos in (("FILTERED (v2 default)", filt), ("RAW Always-In", x["ai"])):
    print(f"\n{name:<34}{'win':>6}{'avgW':>7}{'avgL':>7}{'W/L':>6}{'PF':>6}{'totalR':>8}{'maxDD':>8}{'R/DD':>7}"
          f"{'best':>7}{'worst':>7}  1st|2nd half R   adds")
    for lab, us, ma in V:
        t = trades(pos, us, ma); a, b = t[t.t < half].r.sum(), t[t.t >= half].r.sum()
        print(f"  {lab:<32}" + st(t.r) + f"  {a:>6.1f} |{b:>6.1f}   {t.adds.mean():.2f}")
