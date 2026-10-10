"""Test: do the red-flag events from the event study improve the CAN SLIM portfolio?

Red flags (from data/research/insights/2026-10-10_what-moves-stocks.md, negative in both periods, plus
pledge invocation): CFO resigns, exchange price/volume query, QIP, tender buyback, pledge invoked,
bulk BUY by an individual or company. A flag is active for 90 calendar days after the event became public.

Variants (fixed before running):
  base  current system (data/tune/final.json)
  A     no new buys of a stock with an active flag (holdings unaffected)
  B     A + an active flag also removes the stock from the ranking, so a holding is sold at the next rebalance

Bar (same as earlier tests), judged on 2016-22: Sharpe >= base + 0.03 in BOTH halves (16-19, 20-22) and maxDD
no worse than base by more than 3 points. 2023-26 reported, not judged. The flags were chosen by looking at
event returns over 2016-26, so a pass is weaker evidence than a fresh test.

usage: python -m canslim.flagtest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import tune

ROOT = Path(__file__).resolve().parent.parent
EV = ROOT / "data" / "research" / "events"
OUT = ROOT / "data" / "tune" / "flagtest"
FLAGS = {"announcements": ["CFO resigns", "exchange query: price/volume spurt", "QIP", "buyback"],
         "pledges": ["pledge INVOKED (lender took shares)"],
         "bulk": ["bulk BUY by individual", "bulk BUY by company"]}
DAYS = 90
PERIODS = {"2016-22": tune.TUNE, "2023-26": (tune.HOLD[0], "2026-12-31")}


def flag_mask(index, columns) -> pd.DataFrame:
    ev = pd.concat([pd.read_csv(EV / f / "events.csv", usecols=["sym", "day0", "type"], parse_dates=["day0"])
                    .query("type in @types") for f, types in FLAGS.items()])
    ev = ev[ev.sym.isin(columns)]
    m = pd.DataFrame(False, index=index, columns=columns)
    for s, g in ev.groupby("sym"):
        for d in g.day0:
            m.loc[(m.index > d) & (m.index <= d + pd.Timedelta(days=DAYS)), s] = True
    print(f"  {len(ev)} flag events; share of stock-weeks flagged: {m.values.mean():.2%}", flush=True)
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    final = json.loads((ROOT / "data" / "tune" / "final.json").read_text())
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    cfg = pf.Config(**final["cfg"])
    flag = flag_mask(sc.index, sc.columns)
    hit = (flag & sc.notna()).sum().sum() / max(sc.notna().sum().sum(), 1)
    print(f"  share of passing stock-weeks that carry a flag: {hit:.1%}", flush=True)
    variants = {"base (current)": (sc, None), "A no buys while flagged": (sc, ~flag),
                "B A + sell when flagged": (sc.where(~flag), None)}
    rows = []
    for name, (score, eo) in variants.items():
        for per, (a, b) in PERIODS.items():
            res = lab.run(score, cfg, period=(a, b), entry_ok=eo)
            row = {"variant": name, "period": per, **res.stats}
            if per == "2016-22":
                for h, (x, y) in tune.HALVES.items():
                    row[f"Sharpe {h}"] = pf.stats(res.equity.loc[x:y])["Sharpe"]
            rows.append(row)
            print(f"  {name:<26} {per}: CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5}  maxDD {row['maxDD %']:>6}"
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
