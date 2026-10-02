"""Test: book rule 14, institutional sponsorship, on BSE shareholding history (canslim/shp.py, Dec 2015 on).

Each variant = current rules (data/tune/final.json, incl. R6) PLUS one sponsorship filter, using only the quarters
already filed on each day (point-in-time). Fixed before running:
  I1  number of institutional holders up vs the previous filed quarter     (O'Neil: "number of funds owning")
  I2  number of mutual-fund schemes holding up vs the previous quarter
  I3  institutional % of shares up vs the previous quarter                 (what Screener's FII+DII shows)
  I4  number of institutional holders not falling (>= previous quarter)    (softer version of I1)
Stocks with no BSE filing on a day fail the filter (counted and reported).

Decision bar (same as booktest.py), 2016-22: Sharpe >= base + 0.03 in BOTH halves, maxDD no worse than base by
> 3 points, large-cap Sharpe not below base, median pool >= 3. 2023-26 is reported but already seen.

usage: python -m canslim.insttest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import portfolio as pf
from canslim import shp, tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "insttest"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, cfg = final["rules"], pf.Config(**final["cfg"])
    print("loading data ...", flush=True)
    lab = tune.Lab()
    base = tune.book_score(lab.S, lab.U, lab.has_f, rules)
    syms = list(base.columns[base.notna().any()])
    idx = base.index
    P = {f: shp.panel(f, idx, syms).reindex(columns=base.columns) for f in
         ("inst_n_chg", "mf_n_chg", "inst_pct_chg", "inst_n")}
    have = P["inst_n"].notna() & base.notna()
    print(f"pool stock-days with filing data: {have.sum().sum() / base.notna().sum().sum():.1%}", flush=True)
    masks = {"I1 institutions (count) up": P["inst_n_chg"] > 0,
             "I2 MF schemes (count) up": P["mf_n_chg"] > 0,
             "I3 institutional % up": P["inst_pct_chg"] > 0,
             "I4 institutions (count) not falling": P["inst_n_chg"] >= 0}
    variants = {"base (current)": base}
    variants.update({k: base.where(m.fillna(False).astype(bool)) for k, m in masks.items()})

    rows = []
    for name, sc in variants.items():
        res, big = lab.run(sc, cfg), lab.run(sc.where(lab.big), cfg)
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"],
               "pool median": float(sc.loc[tune.TUNE[0]:tune.TUNE[1]].notna().sum(axis=1).median())}
        for h, (a, b) in tune.HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"], row[f"CAGR {h}"] = st["Sharpe"], st["CAGR %"]
        late = pf.stats(lab.run(sc, cfg, period=("2023-01-01", str(idx[-1].date()))).equity)
        row["Sharpe 23-26"], row["maxDD 23-26"] = late["Sharpe"], late["maxDD %"]
        rows.append(row)
        print(f"  {name:<38} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
              f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})  maxDD {row['maxDD %']:>6}  "
              f"pool {row['pool median']:.0f} | 23-26 Sharpe {late['Sharpe']} maxDD {late['maxDD %']}", flush=True)
    t = pd.DataFrame(rows).set_index("variant")
    b = t.loc["base (current)"]
    t["passes bar"] = [n != "base (current)"
                       and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       and r["pool median"] >= 3
                       for n, r in t.iterrows()]
    t.to_csv(OUT / "results.csv")
    cols = ["CAGR %", "Sharpe", "maxDD %", "Sharpe 16-19", "Sharpe 20-22", "big Sharpe", "pool median",
            "trades/yr", "Sharpe 23-26", "maxDD 23-26", "passes bar"]
    print("\n=== 2016-2022 (23-26 shown, already seen)\n" + t[cols].to_string())
    win = t[t["passes bar"]]
    print("\nDECISION:", ", ".join(win.index) + " pass the bar" if len(win)
          else "no sponsorship filter passes the bar - keep the current system")


if __name__ == "__main__":
    main()
