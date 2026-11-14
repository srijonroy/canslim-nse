"""Test: breakout volume as a confirmer ("techno-funda": the fundamentals pass AND the stock had a volume surge).

A "volume day" = close up >= 2% on volume >= k x the prior 50-day average.
Variants (fixed before running): buy a passing stock only if it had a volume day
  V2x10   k=2 within the last 10 trading days
  V3x20   k=3 within the last 20
  V5x20   k=5 within the last 20
Also, without changing the portfolio: split the CURRENT system's trades by whether a volume day preceded entry.

Decision bar (fixed before running, same as holdtest), 2016-22 only (2023+ already seen):
  adopt only if Sharpe >= base + 0.03 in BOTH halves, maxDD no worse than base by more than 3 points, and the
  large-cap-only Sharpe is not below base.

usage: python -m canslim.voltest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "voltest"
VARIANTS = {"base (current)": None, "2x volume in 10 days": (2, 10), "3x volume in 20 days": (3, 20),
            "5x volume in 20 days": (5, 20)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final = json.loads((OUT.parent / "final.json").read_text())
    cfg = pf.Config(**final["cfg"])
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    C, V = lab.P["close"], lab.P["volume"]
    ratio = V / V.rolling(50, min_periods=40).mean().shift(1)
    up = C.pct_change(fill_method=None) >= 0.02

    def recent(k, n):                       # known at the close of each day: no look-ahead
        return ((ratio >= k) & up).rolling(n, min_periods=1).max().fillna(0).astype(bool)

    rows, base_trades = [], None
    for name, kn in VARIANTS.items():
        ok = None if kn is None else recent(*kn).reindex(sc.index).reindex(columns=sc.columns).fillna(False)
        res, big = lab.run(sc, cfg, entry_ok=ok), lab.run(sc.where(lab.big), cfg, entry_ok=ok)
        if kn is None:
            base_trades = res.trades
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"]}
        for h, (a, b) in tune.HALVES.items():
            row[f"Sharpe {h}"] = pf.stats(res.equity.loc[a:b])["Sharpe"]
        rows.append(row)
        print(f"  {name:<22} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
              f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})  maxDD {row['maxDD %']:>6}  "
              f"invested {row['invested %']:.0f}%  win {row['win %']:.0f}%  trades/yr {row['trades/yr']:.0f}", flush=True)
    t = pd.DataFrame(rows).set_index("variant")
    b = t.iloc[0]
    t["passes bar"] = [i > 0 and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       for i, (_, r) in enumerate(t.iterrows())]
    t.to_csv(OUT / "results.csv")
    # the current system's own trades, split by a volume day before the buy signal (day before entry)
    print("\ncurrent system's trades, split by a volume day before entry:")
    days = C.index
    sp = []
    for name, kn in list(VARIANTS.items())[1:]:
        R = recent(*kn)
        flag = [bool(R.at[days[days.get_loc(pd.Timestamp(e)) - 1], s]) for s, e in zip(base_trades.sym, base_trades.entry_date)]
        for half, (a, bb) in {"all": tune.TUNE, **tune.HALVES}.items():
            m = (pd.to_datetime(base_trades.entry_date) >= a) & (pd.to_datetime(base_trades.entry_date) <= bb)
            for f in (True, False):
                r = base_trades.ret[m & (pd.Series(flag, index=base_trades.index) == f)]
                sp.append({"rule": name, "period": half, "volume day": f, "trades": len(r),
                           "avg %": round(r.mean() * 100, 1), "median %": round(r.median() * 100, 1),
                           "win %": round((r > 0).mean() * 100, 0)})
    sp = pd.DataFrame(sp)
    sp.to_csv(OUT / "trade_split.csv", index=False)
    print(sp.to_string(index=False))
    win = t[t["passes bar"]]
    print("\nDECISION:", ", ".join(win.index) + " pass the bar" if len(win) else "no variant passes the bar")


if __name__ == "__main__":
    main()
