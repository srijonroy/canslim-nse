"""Test: let winners run. Entry unchanged (tuned CAN SLIM); only the SELL rule for holdings already up changes.

Today every holding is sold when it drops out of the top 30 or fails ANY entry rule (e.g. >15% off the high),
so the median trade lasts 23 days and nothing was held a year (2016-22).

Variants (fixed before running):
  base   current rule
  B      once up >= 20%: no rank exit; sell only on a close below the 200-day MA
  C      once up >= 20%: ... close below the 150-day MA (book's 30-week line)
  D      once up >= 20%: ... close 25% below the peak close since entry
  E      once up >= 20%: ... close 30% below the peak close since entry
  F      once up >= 50%: ... close below the 200-day MA

Decision bar (fixed before running), 2016-22 only (2023+ already seen):
  adopt a variant only if Sharpe >= base + 0.03 in BOTH halves (16-19, 20-22), maxDD no worse than base by
  more than 3 points, and the large-cap-only (>= Rs 25 Cr/day) Sharpe is not below base. If several pass,
  take the highest full-period Sharpe.

usage: python -m canslim.holdtest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "holdtest"
VARIANTS = {
    "base (current)": {},
    "B +20% then 200-day": {"ride_after": 0.20, "ride_exit": "ma200"},
    "C +20% then 150-day": {"ride_after": 0.20, "ride_exit": "ma150"},
    "D +20% then 25% trail": {"ride_after": 0.20, "ride_exit": "trail", "trail": 0.25},
    "E +20% then 30% trail": {"ride_after": 0.20, "ride_exit": "trail", "trail": 0.30},
    "F +50% then 200-day": {"ride_after": 0.50, "ride_exit": "ma200"},
    # round 2, added after B-F failed and the re-entry audit (canslim/reentry.py) showed big winners being
    # re-bought and churned out again: ride mode only for a stock bought AGAIN after an earlier sale.
    # Same bar. Not independent of round 1 (same 2016-22 data, idea came from looking at it).
    "G re-buy +10% then 150-day": {"ride_after": 0.10, "ride_exit": "ma150", "ride_scope": "reentry"},
    "H re-buy +10% then 25% trail": {"ride_after": 0.10, "ride_exit": "trail", "trail": 0.25, "ride_scope": "reentry"},
    "I re-buy +20% then 150-day": {"ride_after": 0.20, "ride_exit": "ma150", "ride_scope": "reentry"},
    "J re-buy +20% then 25% trail": {"ride_after": 0.20, "ride_exit": "trail", "trail": 0.25, "ride_scope": "reentry"},
}


def holding_stats(res):
    t = res.trades.copy()
    if t.empty:
        return {}
    t["days"] = (pd.to_datetime(t.exit_date) - pd.to_datetime(t.entry_date)).dt.days
    gain = t.ret.clip(lower=0)
    return {"median days": float(t.days.median()), "held >6m": int((t.days > 182).sum()),
            "held >1y": int((t.days > 365).sum()), "max days": int(t.days.max()),
            "trades >+100%": int((t.ret >= 1).sum()),
            "% of gains from >6m holds": round(100 * gain[t.days > 182].sum() / max(gain.sum(), 1e-9), 1)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, base = final["rules"], final["cfg"]
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, rules)
    rows, trades = [], {}
    for name, kw in VARIANTS.items():
        cfg = pf.Config(**{**base, **kw})
        res = lab.run(sc, cfg)
        big = lab.run(sc.where(lab.big), cfg)
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"]}
        for h, (a, b) in tune.HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"], row[f"CAGR {h}"], row[f"maxDD {h}"] = st["Sharpe"], st["CAGR %"], st["maxDD %"]
        row.update(holding_stats(res))
        rows.append(row)
        trades[name] = res.trades.assign(variant=name)
        print(f"  {name:<24} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
              f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})  maxDD {row['maxDD %']:>6}  "
              f"median hold {row.get('median days')}d  >1y {row.get('held >1y')}", flush=True)
    t = pd.DataFrame(rows).set_index("variant")
    b = t.loc["base (current)"]
    t["passes bar"] = [
        n != "base (current)"
        and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
        and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
        for n, r in t.iterrows()]
    t.to_csv(OUT / "results.csv")
    pd.concat(trades.values()).to_csv(OUT / "trades.csv", index=False)
    print("\n=== 2016-2022")
    print(t.drop(columns=[c for c in ("vol %", "Calmar") if c in t.columns]).T.to_string())
    win = t[t["passes bar"]]
    print("\nDECISION:", win["Sharpe"].idxmax() + " passes the bar" if len(win) else "no variant passes the bar - keep current rule")


if __name__ == "__main__":
    main()
