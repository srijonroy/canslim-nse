"""Test: book rules the system does not use yet ("Important Rules and Guidelines", pp. 424-426, 4th ed.).

Each variant = current tuned rules (data/tune/final.json) PLUS one book rule. Fixed before running:
  R3   "last two or three quarters' EPS up 25%-30% minimum"      -> profit growth >= 25% in each of the last 2 qtrs
  R6   "recent quarterly after-tax margins improving"            -> net margin up vs a year ago
  R7a  "top 10% of the 197 industry sub-groups" (book p.331: "concentrate on the top 20 groups") -> group RS top 20%
  R7b  same, strict                                             -> group RS top 10%
  R9   "RS rating of 85 or higher"                               -> RS >= 85 (was 80)
  R4   "each of the last three quarters' sales accelerating or last quarter up 25%+" -> sales accelerating or >= 25%
  S    ch.6 supply/demand: accumulation                          -> up-day volume > down-day volume (50 days)
  R17  "don't overdiversify"                                    -> 5 stocks (keep while rank <= 15)
  ALL  R3 + R6 + R7a together (the book applies them together)
Not testable here (no point-in-time data before 2023): R14 institutional sponsorship, R18 management ownership,
R22 buybacks / new management, R2 consensus estimates and cash flow vs EPS.

Decision bar (same as tune.py / holdtest.py), 2016-22 only:
  adopt only if Sharpe >= base + 0.03 in BOTH halves (16-19, 20-22), maxDD no worse than base by > 3 points,
  and large-cap-only Sharpe not below base. 9 variants are tried, so one may pass by luck: a pass also needs a
  median pool of >= 3 stocks, and is reported as "passes, verify live" rather than adopted blindly.

usage: python -m canslim.booktest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import tune
from canslim.data import CACHE

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "booktest"


def extra_panels(lab):
    ds = pd.read_pickle(CACHE / "winners_ds.pkl")
    idx, cols = lab.S["trend"].index, lab.P["close"].columns
    return {k: ds[k].unstack("sym").reindex(index=idx, columns=cols) for k in ("np_min2", "sales_accel")}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, base_cfg = final["rules"], pf.Config(**final["cfg"])
    print("loading data ...", flush=True)
    lab = tune.Lab()
    S, X = lab.S, extra_panels(lab)
    base = tune.book_score(S, lab.U, lab.has_f, rules)
    elig = lab.U & lab.has_f
    grp = S["group_rs"].where(elig).rank(axis=1, pct=True)
    rs85 = tune.book_score(S, lab.U, lab.has_f, {**rules, "rs": 85})
    masks = {
        "R3 2 qtrs profit >=25%": X["np_min2"] >= 25,
        "R6 net margin improving": S["npm_chg"] > 0,
        "R7a group top 20%": grp >= 0.8,
        "R7b group top 10%": grp >= 0.9,
        "R4 sales accel or >=25%": (X["sales_accel"] > 0) | (S["sales_yoy"] >= 25),
        "S accumulation (up vol > down vol)": S["ud_vol"] > 0,
    }
    variants = {"base (current)": (base, base_cfg), "R9 RS >= 85": (rs85, base_cfg)}
    for k, m in masks.items():
        variants[k] = (base.where(m.reindex_like(base).fillna(False).astype(bool)), base_cfg)
    variants["R17 5 stocks"] = (base, pf.Config(**{**base_cfg.__dict__, "n": 5, "keep_rank": 15}))
    allm = masks["R3 2 qtrs profit >=25%"] & masks["R6 net margin improving"] & masks["R7a group top 20%"]
    variants["ALL R3+R6+R7a"] = (base.where(allm.reindex_like(base).fillna(False).astype(bool)), base_cfg)

    rows = []
    for name, (sc, cfg) in variants.items():
        res = lab.run(sc, cfg)
        big = lab.run(sc.where(lab.big), cfg)
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"],
               "pool median": float(sc.loc[tune.TUNE[0]:tune.TUNE[1]].notna().sum(axis=1).median())}
        for h, (a, b) in tune.HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"], row[f"CAGR {h}"] = st["Sharpe"], st["CAGR %"]
        rows.append(row)
        print(f"  {name:<36} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
              f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})  maxDD {row['maxDD %']:>6}  "
              f"pool {row['pool median']:.0f}", flush=True)
    t = pd.DataFrame(rows).set_index("variant")
    b = t.loc["base (current)"]
    t["passes bar"] = [n != "base (current)"
                       and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       and r["pool median"] >= 3
                       for n, r in t.iterrows()]
    t.to_csv(OUT / "results.csv")
    cols = ["CAGR %", "Sharpe", "maxDD %", "Sharpe 16-19", "Sharpe 20-22", "big Sharpe", "pool median",
            "trades/yr", "win %", "passes bar"]
    print("\n=== 2016-2022\n" + t[cols].to_string())
    win = t[t["passes bar"]]
    print("\nDECISION:", ", ".join(win.index) + " pass the bar (verify live before adopting)" if len(win)
          else "no book rule passes the bar - keep the current system")


if __name__ == "__main__":
    main()
