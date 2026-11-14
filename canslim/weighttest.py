"""Test: position sizing and number of slots. Entry and exit rules unchanged (data/tune/final.json).

Variants (fixed before running):
  base        10 equal slots (current)
  rank        10 slots; ranks 1-3 get 1.5 slots, 4-7 one slot, 8+ half a slot
  invvol      10 slots; calmer stocks get more (median pool volatility / own 60-day volatility, clipped 0.5-1.5)
  n5/n15/n20  5, 15 or 20 equal slots (keep_rank unchanged at 30)

Decision bar (fixed before running, same as holdtest), 2016-22 only (2023+ already seen):
  adopt only if Sharpe >= base + 0.03 in BOTH halves (16-19, 20-22), maxDD no worse than base by more than
  3 points, and the large-cap-only Sharpe is not below base.

usage: python -m canslim.weighttest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "weighttest"
VARIANTS = {"base (10 equal)": {}, "rank-weighted": {"weighting": "rank"}, "volatility-weighted": {"weighting": "invvol"},
            "5 slots": {"n": 5}, "15 slots": {"n": 15}, "20 slots": {"n": 20}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, base = final["rules"], final["cfg"]
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, rules)
    rows = []
    for name, kw in VARIANTS.items():
        cfg = pf.Config(**{**base, **kw})
        res, big = lab.run(sc, cfg), lab.run(sc.where(lab.big), cfg)
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"]}
        for h, (a, b) in tune.HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"], row[f"CAGR {h}"] = st["Sharpe"], st["CAGR %"]
        rows.append(row)
        print(f"  {name:<20} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
              f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})  maxDD {row['maxDD %']:>6}  "
              f"invested {row['invested %']:.0f}%", flush=True)
    t = pd.DataFrame(rows).set_index("variant")
    b = t.iloc[0]
    t["passes bar"] = [i > 0 and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       for i, (_, r) in enumerate(t.iterrows())]
    t.to_csv(OUT / "results.csv")
    win = t[t["passes bar"]]
    print("\nDECISION:", ", ".join(win.index) + " pass the bar" if len(win) else "no variant passes the bar - keep 10 equal slots")


if __name__ == "__main__":
    main()
