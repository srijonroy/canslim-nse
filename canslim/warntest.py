"""Test: sector warnings as sell/avoid rules inside CAN SLIM (follow-up to sectortest.py).

Group = Screener basic industry, strength = mean RS percentile of members (>= 5 liquid members), ranked weekly.
A stock whose group is flagged gets no score that week, so it is not bought and a holding is sold.
Fixed before running:
  W1 group fell out: group was in the top 20% within the last 13 weeks and is now below the top 20%
  W2 weak group: group in the bottom 20%
  W3 weak group: group in the bottom half
Decision bar as in booktest.py (2016-22, both halves +0.03 Sharpe, DD no worse than 3 pts, big-cap Sharpe not lower,
pool >= 3); 2023-26 shown as a check. Stocks in groups with < 5 members are never flagged.

usage: python -m canslim.warntest   (writes data/tune/warntest/results.csv)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune
from canslim.sectortest import grp_mean

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "warntest"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    print("loading data ...", flush=True)
    lab = tune.Lab()
    final = json.loads((tune.OUT / "final.json").read_text())
    rules, cfg = final["rules"], pf.Config(**final["cfg"])
    S, U = lab.S, lab.U
    base = tune.book_score(S, U, lab.has_f, rules)
    idx, cols = base.index, base.columns
    ind = pd.Series(lab.ind).reindex(cols).dropna()
    Uk = U.reindex(columns=ind.index).fillna(False).astype(bool)
    rs_pct = S["rs_ibd"].where(U).rank(axis=1, pct=True).reindex(columns=ind.index)
    gp = grp_mean(rs_pct, Uk, ind).rank(axis=1, pct=True)          # weekly group strength percentile
    print(f"  {gp.notna().sum(axis=1).median():.0f} groups/week (median)", flush=True)
    flags_g = {
        "W1 group fell out of top 20%": (gp < 0.8) & (gp.shift(1) >= 0.8).rolling(13, min_periods=1).max().astype(bool),
        "W2 group in bottom 20%": gp <= 0.2,
        "W3 group in bottom half": gp <= 0.5,
    }

    def to_stock(Fg):
        out = pd.DataFrame(False, index=idx, columns=cols)
        Fg = Fg.reindex(idx).fillna(False)
        for g in Fg.columns:
            m = ind[ind == g].index
            out[m] = np.repeat(Fg[g].values[:, None].astype(bool), len(m), axis=1)
        return out

    variants = {"base (current)": base}
    for name, Fg in flags_g.items():
        f = to_stock(Fg)
        share = (f & base.notna()).loc[tune.TUNE[0]:tune.TUNE[1]].sum().sum() / base.loc[tune.TUNE[0]:tune.TUNE[1]].notna().sum().sum()
        print(f"  {name}: flags {100 * share:.1f}% of passing stock-weeks (2016-22)", flush=True)
        variants[name] = base.where(~f)

    rows = []
    for name, sc in variants.items():
        res = lab.run(sc, cfg)
        big = lab.run(sc.where(lab.big), cfg)
        chk = lab.run(sc, cfg, period=("2023-01-01", None))
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"],
               "pool median": float(sc.loc[tune.TUNE[0]:tune.TUNE[1]].notna().sum(axis=1).median()),
               "check 23-26 Sharpe": chk.stats["Sharpe"], "check 23-26 CAGR": chk.stats["CAGR %"],
               "check 23-26 maxDD": chk.stats["maxDD %"]}
        for h, (a, b) in tune.HALVES.items():
            row[f"Sharpe {h}"] = pf.stats(res.equity.loc[a:b])["Sharpe"]
        rows.append(row)
        print(f"  {name:<30} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
              f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})  maxDD {row['maxDD %']:>6}  "
              f"pool {row['pool median']:.0f} | check 23-26 Sharpe {row['check 23-26 Sharpe']} CAGR {row['check 23-26 CAGR']}",
              flush=True)
    t = pd.DataFrame(rows).set_index("variant")
    b = t.loc["base (current)"]
    t["passes bar"] = [n != "base (current)"
                       and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       and r["pool median"] >= 3
                       for n, r in t.iterrows()]
    t.to_csv(OUT / "results.csv")
    win = t[t["passes bar"]]
    print("\nDECISION: " + (", ".join(win.index) + " pass the bar" if len(win) else "no sector warning passes the bar"))


if __name__ == "__main__":
    main()
