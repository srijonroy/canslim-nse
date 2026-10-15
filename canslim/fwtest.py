"""Backtest the other frameworks (canslim/frameworks.py) next to CAN SLIM, 2016-2026, weekly, 0.3% cost per side.

Portfolio settings fixed before running (no tuning):
  value / quality styles (coffee, magic, qglp, garp, graham): 20 stocks, keep while ranked within 60,
      no stop, always invested (these styles don't time the market), max 4 per industry
  trend: 10 stocks, keep while ranked within 30, 8% stop, no new buys unless the market is in an uptrend
  stage: 10 stocks, buy only within 4 weeks of a breakout, keep while in stage 2 and ranked within 30,
      no new buys unless the market is in an uptrend
CAN SLIM = current system (data/tune/final.json). Nifty 500 = buy and hold (price index, no dividends).

Also a look-ahead check: scores on a past date computed from data cut off at that date must equal scores computed
with all data. If they differ, the code is using the future.

usage: python -m canslim.fwtest   (writes data/tune/frameworks/)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import data
from canslim import frameworks as fw
from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "frameworks"
PER = {"2016-19": ("2016-01-01", "2019-12-31"), "2020-22": ("2020-01-01", "2022-12-31"),
       "2023-26": ("2023-01-01", "2026-12-31")}
VALUE = pf.Config(n=20, keep_rank=60, stop=None, market="none", max_per_group=4)
CFG = {"coffee": VALUE, "magic": VALUE, "qglp": VALUE, "garp": VALUE, "graham": VALUE,
       "trend": pf.Config(n=10, keep_rank=30, stop=0.08, market="no_new"),
       "stage": pf.Config(n=10, keep_rank=30, stop=None, market="no_new")}


def log(m):
    print(m, flush=True)


def lookahead_check(lab, loaded, dates):
    """Scores on date T from data cut at T vs from all data."""
    T = dates[len(dates) // 2]
    full = fw.compute(lab.P, lab.U, lab.S["rs_ibd"], pd.DatetimeIndex([T]), loaded=loaded)
    Pc = {k: v.loc[:T] for k, v in lab.P.items()}
    cut = fw.compute(Pc, lab.U.loc[:T], lab.S["rs_ibd"].loc[:T], pd.DatetimeIndex([T]), loaded=loaded)
    bad = {}
    for k in full:
        a, b = full[k]["score"].iloc[0], cut[k]["score"].iloc[0]
        same = ((a - b).abs() < 1e-9) | (a.isna() & b.isna())
        bad[k] = int((~same).sum())
    return T, bad


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    log("loading data ...")
    lab = tune.Lab()
    dates = lab.U.index[lab.U.index >= "2015-06-01"]
    loaded = fw.load()
    log(f"  fundamentals for {len(loaded[0])} stocks; computing scores on {len(dates)} weeks ...")
    res = fw.compute(lab.P, lab.U, lab.S["rs_ibd"], dates, loaded=loaded)
    for k, r in res.items():
        n = r["score"].loc["2016":].notna().sum(axis=1)
        log(f"  {k:<10} stocks passing per week: median {n.median():.0f}, min {n.min():.0f}, max {n.max():.0f}")

    T, bad = lookahead_check(lab, loaded, dates)
    log(f"\nlook-ahead check on {T.date()}: stocks whose score changes when future data is removed: {bad}")

    final = json.loads((tune.OUT / "final.json").read_text())
    runs = {"CAN SLIM (current)": (tune.book_score(lab.S, lab.U, lab.has_f, final["rules"]), pf.Config(**final["cfg"]), None)}
    for k, r in res.items():
        runs[fw.RULES[k][0]] = (r["score"], CFG[k], r["entry"])
    period = ("2016-01-01", None)
    rows, eq = [], {}
    for name, (sc, cfg, entry) in runs.items():
        out = lab.run(sc, cfg, period=period, entry_ok=entry)
        eq[name] = out.equity
        row = {"framework": name, **{k: out.stats.get(k) for k in ("CAGR %", "Sharpe", "maxDD %", "trades/yr", "win %")},
               "avg invested %": round(100 * float(out.exposure.mean()), 0)}
        for p, (a, b) in PER.items():
            st = pf.stats(out.equity.loc[a:b])
            row[f"CAGR {p}"], row[f"Sharpe {p}"] = st["CAGR %"], st["Sharpe"]
        rows.append(row)
        log(f"  {name:<45} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5}  maxDD {row['maxDD %']:>6}  "
            f"invested {row['avg invested %']:>3.0f}%  | CAGR 16-19 {row['CAGR 2016-19']:>5} 20-22 {row['CAGR 2020-22']:>5} "
            f"23-26 {row['CAGR 2023-26']:>5}")
    idx = data.index_close("NIFTY500").loc["2016-01-01":]
    row = {"framework": "Nifty 500 (buy and hold)", **{k: pf.stats(idx).get(k) for k in ("CAGR %", "Sharpe", "maxDD %")},
           "avg invested %": 100}
    for p, (a, b) in PER.items():
        st = pf.stats(idx.loc[a:b])
        row[f"CAGR {p}"], row[f"Sharpe {p}"] = st["CAGR %"], st["Sharpe"]
    rows.append(row)
    t = pd.DataFrame(rows).set_index("framework")
    E = pd.DataFrame(eq).ffill()
    corr = E.pct_change().corr()["CAN SLIM (current)"].round(2)
    t["corr with CAN SLIM"] = corr
    t.to_csv(OUT / "results.csv")
    E.to_csv(OUT / "equity.csv")
    summary = {"run": pd.Timestamp.now().strftime("%Y-%m-%d"), "lookahead_date": str(T.date()), "lookahead_bad": bad,
               "results": json.loads(t.reset_index().to_json(orient="records"))}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    cols = ["CAGR %", "Sharpe", "maxDD %", "avg invested %", "CAGR 2016-19", "CAGR 2020-22", "CAGR 2023-26",
            "trades/yr", "corr with CAN SLIM"]
    log("\n=== 2016-2026, weekly, 0.3% cost per side\n" + t[cols].to_string())


if __name__ == "__main__":
    main()
