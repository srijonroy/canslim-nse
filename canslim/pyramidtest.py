"""Test: pyramiding / adding to winners (book rule 12). Entry and exit rules unchanged; only position building.

Variants (fixed before running), as ((gain from first buy, fraction of the slot), ...):
  base  full slot at once (current)
  P1    book: 50% first, +30% at +2.5%, +20% at +5%
  P2    50% first, +50% at +5%
  P3    50% first, +50% at +10% (only clear winners reach full size)
Cash not yet added earns the backtest's cash yield.

Bar (same as earlier tests), judged on 2016-22: Sharpe >= base + 0.03 in BOTH halves (16-19, 20-22) and maxDD
no worse than base by more than 3 points. 2023-26 reported, not judged.

usage: python -m canslim.pyramidtest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import tune

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tune" / "pyramidtest"
VARIANTS = {"base (current)": (),
            "P1 book 50/30/20 at +2.5/+5%": ((0.0, 0.5), (0.025, 0.3), (0.05, 0.2)),
            "P2 50/50 at +5%": ((0.0, 0.5), (0.05, 0.5)),
            "P3 50/50 at +10%": ((0.0, 0.5), (0.10, 0.5))}
PERIODS = {"2016-22": tune.TUNE, "2023-26": (tune.HOLD[0], "2026-12-31")}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final = json.loads((ROOT / "data" / "tune" / "final.json").read_text())
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    rows = []
    for name, pyr in VARIANTS.items():
        cfg = pf.Config(**{**final["cfg"], "pyramid": pyr})
        for per, (a, b) in PERIODS.items():
            res = lab.run(sc, cfg, period=(a, b))
            t = res.trades
            row = {"variant": name, "period": per, **res.stats,
                   "invested %": round(res.exposure.mean() * 100, 1),
                   "trades fully built %": round((t.adds == len(pyr) - 1).mean() * 100, 0) if pyr else 100.0}
            if per == "2016-22":
                for h, (x, y) in tune.HALVES.items():
                    row[f"Sharpe {h}"] = pf.stats(res.equity.loc[x:y])["Sharpe"]
            rows.append(row)
            print(f"  {name:<30} {per}: CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5}  maxDD {row['maxDD %']:>6}  "
                  f"invested {row['invested %']:>5}%  fully built {row['trades fully built %']:>4}%"
                  + (f"  halves {row['Sharpe 16-19']} | {row['Sharpe 20-22']}" if per == "2016-22" else ""), flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "results.csv", index=False)
    base = R[(R.variant == "base (current)") & (R.period == "2016-22")].iloc[0]
    for name in list(VARIANTS)[1:]:
        v = R[(R.variant == name) & (R.period == "2016-22")].iloc[0]
        ok = all(v[f"Sharpe {h}"] >= base[f"Sharpe {h}"] + 0.03 for h in tune.HALVES) and v["maxDD %"] >= base["maxDD %"] - 3
        print(f"bar {name}: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
