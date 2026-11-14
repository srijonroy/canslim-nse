"""Test: let winners run while the business keeps growing; cut losers early.

Today a holding is sold when it drops out of the top 30 or fails ANY entry rule, so the median trade lasts
23 days. Earlier ride tests (holdtest.py) used price exits (200-day line, trailing stops) and failed.
Here a winner is held on its FUNDAMENTALS: once up >= 20% it is no longer sold for rank or rule failures, only
when the latest quarterly profit growth (year on year, known at the time) fades.

Variants (fixed before running):
  A   +20% -> hold until profit growth < 0
  B   +20% -> hold until profit growth < 15%
  C   +20% -> hold until profit growth < 25% AND lower than in the previous quarter (the HEG rule)
  D   B, or a close below the 200-day average, whichever comes first
  E   B, plus an 8% stop on positions that never reached +20%
  F   D, plus the same 8% stop

Decision bar (fixed before running, same as holdtest), 2016-22 only:
  Sharpe >= base + 0.03 in BOTH halves, maxDD no worse than base by more than 3 points, large-cap Sharpe not
  below base. 2023-26 is shown as a check only (already seen; never used to choose).

usage: python -m canslim.growthhold
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import tune
from canslim.holdtest import holding_stats

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "growthhold"
G = {"ride_after": 0.20}
VARIANTS = {
    "base (current)": ({}, None),
    "A hold till growth < 0": ({**G, "ride_exit": "growth"}, "a"),
    "B hold till growth < 15%": ({**G, "ride_exit": "growth"}, "b"),
    "C hold till growth slows (<25%, falling)": ({**G, "ride_exit": "growth"}, "c"),
    "D = B or below 200-day": ({**G, "ride_exit": "growth_ma200"}, "b"),
    "E = B + 8% stop on losers": ({**G, "ride_exit": "growth", "stop": 0.08}, "b"),
    "F = D + 8% stop on losers": ({**G, "ride_exit": "growth_ma200", "stop": 0.08}, "b"),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, base = final["rules"], final["cfg"]
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, rules)
    g, acc = lab.S["np_yoy"], lab.S["accel"]
    hold = {"a": (g >= 0).where(g.notna()), "b": (g >= 15).where(g.notna()),
            "c": (~((g < 25) & (acc < 0))).where(g.notna())}
    rows, trades = [], {}
    for name, (kw, hk) in VARIANTS.items():
        cfg = pf.Config(**{**base, **kw})
        ho = hold.get(hk)
        res, big = lab.run(sc, cfg, hold_ok=ho), lab.run(sc.where(lab.big), cfg, hold_ok=ho)
        chk = lab.run(sc, cfg, period=tune.HOLD, hold_ok=ho)
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"]}
        for h, (a, b) in tune.HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"], row[f"CAGR {h}"] = st["Sharpe"], st["CAGR %"]
        row.update(holding_stats(res))
        row.update({"23-26 CAGR": chk.stats["CAGR %"], "23-26 Sharpe": chk.stats["Sharpe"],
                    "23-26 maxDD": chk.stats["maxDD %"]})
        rows.append(row)
        trades[name] = res.trades.assign(variant=name)
        print(f"  {name:<42} CAGR {row['CAGR %']:>5} Sharpe {row['Sharpe']:>5} ({row['Sharpe 16-19']:>5} | "
              f"{row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5}) DD {row['maxDD %']:>6} inv {row['invested %']:.0f}% "
              f"hold {row.get('median days'):.0f}d >1y {row.get('held >1y')} 2x {row.get('trades >+100%')} "
              f"win {row['win %']:.0f}% +{row['avg win %']}/{row['avg loss %']} "
              f"|| 23-26: {row['23-26 CAGR']} / {row['23-26 Sharpe']} / {row['23-26 maxDD']}", flush=True)
    t = pd.DataFrame(rows).set_index("variant")
    b = t.iloc[0]
    t["passes bar"] = [i > 0 and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       for i, (_, r) in enumerate(t.iterrows())]
    t.to_csv(OUT / "results.csv")
    pd.concat(trades.values()).to_csv(OUT / "trades.csv", index=False)
    win = t[t["passes bar"]]
    print("\nDECISION:", ", ".join(win.index) + " pass the bar" if len(win) else "no variant passes the bar")


if __name__ == "__main__":
    main()
