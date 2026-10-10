"""Test: promoter (management) ownership, book rule 18, as an extra CAN SLIM rule.

Data: BSE shareholding pattern per quarter from Dec 2015 (canslim/shp.py, field 10098 = total public holding;
promoter % = 100 - public). Point-in-time: a quarter is usable from its BSE filing date.

Variants (fixed before running), each added on top of the current rules (a stock failing it also leaves
the ranking, like any other rule); stocks without data pass:
  R1  promoter holding >= 50%
  R2  promoter holding >= 35%
  R3  promoter holding not down by more than 1 point vs a year earlier

Bar (same as earlier tests), judged on 2016-22: Sharpe >= base + 0.03 in BOTH halves (16-19, 20-22) and maxDD
no worse than base by more than 3 points. 2023-26 reported, not judged.

usage: python -m canslim.promotertest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import shp, tune

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tune" / "promotertest"
PERIODS = {"2016-22": tune.TUNE, "2023-26": (tune.HOLD[0], "2026-12-31")}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final = json.loads((ROOT / "data" / "tune" / "final.json").read_text())
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    pool = list(sc.columns[sc.notna().any()])
    prom = shp.panel("promoter_pct", sc.index, pool).reindex(columns=sc.columns)
    year_ago = prom.shift(52)
    passing = sc.notna()
    cover = prom.where(passing).notna().sum().sum() / passing.sum().sum()
    print(f"  promoter data for {cover:.0%} of passing stock-weeks; median promoter holding of passing stocks "
          f"{prom.where(passing).stack().median():.1f}%", flush=True)
    rules = {"R1 promoter >= 50%": prom >= 50, "R2 promoter >= 35%": prom >= 35,
             "R3 promoter not down >1pt in a year": (prom - year_ago) >= -1}
    variants = {"base (current)": sc}
    for name, ok in rules.items():
        variants[name] = sc.where(ok | prom.isna() | (name.startswith("R3") & year_ago.isna()))
    cfg = pf.Config(**final["cfg"])
    rows = []
    for name, score in variants.items():
        for per, (a, b) in PERIODS.items():
            res = lab.run(score, cfg, period=(a, b))
            row = {"variant": name, "period": per, **res.stats,
                   "pool median": float(score.loc[a:b].notna().sum(axis=1).median())}
            if per == "2016-22":
                for h, (x, y) in tune.HALVES.items():
                    row[f"Sharpe {h}"] = pf.stats(res.equity.loc[x:y])["Sharpe"]
            rows.append(row)
            print(f"  {name:<38} {per}: CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5}  maxDD {row['maxDD %']:>6}  "
                  f"pool {row['pool median']:.0f}"
                  + (f"  halves {row['Sharpe 16-19']} | {row['Sharpe 20-22']}" if per == "2016-22" else ""), flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "results.csv", index=False)
    base = R[(R.variant == "base (current)") & (R.period == "2016-22")].iloc[0]
    for name in list(variants)[1:]:
        v = R[(R.variant == name) & (R.period == "2016-22")].iloc[0]
        ok = all(v[f"Sharpe {h}"] >= base[f"Sharpe {h}"] + 0.03 for h in tune.HALVES) and v["maxDD %"] >= base["maxDD %"] - 3
        print(f"bar {name}: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
