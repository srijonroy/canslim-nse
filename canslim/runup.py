"""Test: should stocks up > 100% in six months be skipped (or demoted) as new buys?

The 100% figure came from looking at recent picks, so it is tested here on the
2016-2022 tuning period only, with the tuned system (data/tune/final.json) as the base.

Decision rule (fixed before running, same bar as tune.py stages 3-4):
  adopt a variant only if Sharpe improves >= 0.03 in BOTH halves (2016-19, 2020-22)
  and large-cap Sharpe does not fall. 75% / 150% are sensitivity checks, not candidates.

usage: python -m canslim.runup
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "runup"
SIX_M = 126


def trade_split(trades: pd.DataFrame, r6: pd.DataFrame, cut: float) -> pd.DataFrame:
    """Trade outcomes split by 6-month run-up on the day the buy was decided."""
    t = trades.copy()
    prev = r6.shift(1)                  # buy decided at the prior close, filled at the open
    t["runup"] = [prev.at[d, s] for s, d in zip(t.sym, t.entry_date)]
    t["group"] = np.where(t.runup > cut, f"> {cut:.0%}", f"<= {cut:.0%}")
    return t.groupby("group").ret.agg(trades="count", avg_ret=lambda x: round(x.mean() * 100, 1),
                                      median_ret=lambda x: round(x.median() * 100, 1),
                                      win_pct=lambda x: round((x > 0).mean() * 100, 0))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tune.OUT = OUT                      # keep data/tune/trials.csv untouched
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, cfg = final["rules"], pf.Config(**final["cfg"])
    print("loading cached build ...", flush=True)
    lab = tune.Lab()
    c = lab.P["close"]
    r6_daily = c / c.shift(SIX_M) - 1
    sc = tune.book_score(lab.S, lab.U, lab.has_f, rules)
    r6 = r6_daily.reindex(index=sc.index, columns=sc.columns)

    base = lab.evaluate("tuned (baseline)", rules, cfg, stage="base")
    res = lab.run(sc, cfg)
    print("\nTrades in 2016-22 by 6-month run-up at entry (baseline system):")
    print(trade_split(res.trades, r6_daily, 1.0).to_string(), flush=True)

    rows = {}
    for cut in (0.75, 1.0, 1.5):
        ok = ~(r6 > cut)
        rows[cut] = lab.evaluate(f"skip new buys if 6m > {cut:.0%}", rules, cfg,
                                 entry_ok=ok.loc[:tune.TUNE[1]], stage="runup")

    # demotion: keep them eligible, but rank below every non-extended passing stock
    orig = tune.book_score

    def demoted(S, U, has_f, r):
        s = orig(S, U, has_f, r)
        return s - (r6.reindex_like(s) > 1.0).astype(float)
    tune.book_score = demoted
    dem = lab.evaluate("demote if 6m > 100%", rules, cfg, stage="runup")
    tune.book_score = orig

    print("\n=== Decision (pre-set bar: +0.03 Sharpe in both halves, large caps not worse)")
    for name, row in [("skip > 100%", rows[1.0]), ("demote > 100%", dem)]:
        ok = tune.better(row, base, 0.03) and row["big_Sharpe"] >= base["big_Sharpe"]
        print(f"  {name:<14} -> {'ADOPT' if ok else 'reject'}  "
              f"(halves {row['Sharpe 16-19'] - base['Sharpe 16-19']:+.2f} / "
              f"{row['Sharpe 20-22'] - base['Sharpe 20-22']:+.2f}, big {row['big_Sharpe'] - base['big_Sharpe']:+.2f})")
    print(f"\ntrials: {len(tune.TRIALS)} -> {OUT / 'trials.csv'}")


if __name__ == "__main__":
    main()
