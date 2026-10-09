"""Does waiting for a follow-through bar after an Always-In signal help?

For every signal (state flips to LONG or SHORT) the trade is held until the state leaves that side.
  now  : enter at the open of the bar after the signal bar (what we do today)
  FT   : enter one bar later, only if the bar after the signal is a follow-through bar
FT strict = same-colour bar closing beyond the signal bar's close; FT loose = closes beyond the signal bar's close.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Project\asd\data\indicators")
from aitest import indicator, range_filter, COST

DATA = sys.argv[1]
d = pd.read_parquet(DATA)
d.index = d.index.tz_convert("Asia/Kolkata")
x = indicator(d)
o, h, l, c, idx = x["o"], x["h"], x["l"], x["c"], d.index
mins = idx.hour * 60 + idx.minute
quiet = np.asarray((mins >= 90) & (mins < 750))          # 01:30-12:30 IST
filt = range_filter(x, minCross=3); filt[quiet] = 0

def signals(pos):
    rows, n = [], len(pos)
    for i in range(1, n - 3):
        s = pos[i]
        if s == 0 or s == pos[i - 1]: continue
        j = i + 1
        while j < n - 1 and pos[j] == s: j += 1
        if j >= n - 1: break
        ex = o[j + 1]; f = i + 1
        ft_loose = s * (c[f] - c[i]) > 0
        ft_strict = ft_loose and s * (c[f] - o[f]) > 0
        still = pos[f] == s                                # state hasn't already flipped away
        hz = lambda e, k: s * (c[min(e + k, n - 1)] - o[e]) - COST
        rows.append(dict(t=idx[i], side=s, bars=j - i,
                         now=s * (ex - o[i + 1]) - COST,
                         wait=s * (ex - o[i + 2]) - COST if still and j > i + 1 else np.nan,
                         ft_loose=ft_loose and still, ft_strict=ft_strict and still,
                         now_1h=hz(i + 1, 12), wait_1h=hz(i + 2, 12)))
    return pd.DataFrame(rows)

def line(name, p):
    p = p.dropna()
    if p.empty: return f"  {name:<44}{0:>5}"
    w = p[p > 0]; lo = p[p <= 0]
    pf = w.sum() / -lo.sum() if len(lo) else np.inf
    return f"  {name:<44}{len(p):>5}{100*len(w)/len(p):>6.0f}%{p.mean():>8.2f}{p.sum():>8.0f}{pf:>6.2f}"

half = idx[len(idx) // 2]
print(f"ES 5m {idx[0]:%d %b} -> {idx[-1]:%d %b %Y}, {len(idx)} bars, cost {COST} pt/trade")
for name, pos in (("RAW Always-In", x["ai"]), ("FILTERED (v2 default: range C3 + skip Asia)", filt)):
    s = signals(pos)
    for per, ss in (("all", s), ("1st half", s[s.t < half]), ("2nd half", s[s.t >= half])):
        print(f"\n=== {name} | {per}")
        print(f"  {'':<44}{'n':>5}{'win':>7}{'avg':>8}{'total':>8}{'PF':>6}")
        print(line("A enter now, every signal", ss.now))
        print(line("   ...signals that DID get loose FT", ss.now[ss.ft_loose]))
        print(line("   ...signals that did NOT get loose FT", ss.now[~ss.ft_loose]))
        print(line("B wait for loose FT, enter next bar", ss.wait[ss.ft_loose]))
        print(line("C wait for strict FT, enter next bar", ss.wait[ss.ft_strict]))
        if per == "all":
            print("  fixed 1-hour hold instead of hold-to-flip:")
            print(line("A enter now, every signal (1h)", ss.now_1h))
            print(line("B wait for loose FT (1h)", ss.wait_1h[ss.ft_loose]))
            print(line("C wait for strict FT (1h)", ss.wait_1h[ss.ft_strict]))
