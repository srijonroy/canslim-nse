"""Test: put the CAN SLIM portfolio's idle cash to work.

The system is only ~39% invested on average (2016-22) because about 4 stocks pass the rules on a typical day and
no new buys are made outside an uptrend. Idle cash earns the liquid-fund rate (6%/yr) in the backtest.
Here the idle cash goes into a second holding instead; the CAN SLIM trades themselves are unchanged.

Variants (fixed before running):
  base     idle cash at 6%/yr (current)
  N1       idle cash in the Nifty 500 index, always
  N2       idle cash in the Nifty 500 only while the market model says uptrend, else 6%
  G1       idle cash in the Graham list portfolio (as simulated in fwtest.py: 20 stocks, itself part cash), always
  G2       idle cash in the Graham portfolio only while the market model says uptrend, else 6%

How: each day the idle fraction at the previous close earns the second holding's return instead of the cash
rate; changing the size of the second holding costs 0.3% of the amount moved. The Nifty 500 is the price index
(no dividends, about 1.2%/yr understated).

Decision bar (fixed before running, same as holdtest), 2016-22 only:
  Sharpe >= base + 0.03 in BOTH halves, maxDD no worse than base by more than 3 points, large-cap Sharpe not
  below base. 2023 onward is shown as a check only (already seen; never used to choose).

usage: python -m canslim.idletest
"""
import json
from pathlib import Path

import pandas as pd

from canslim import frameworks as fw
from canslim import fwtest
from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "idletest"
COST, RF = 0.003, (1.06) ** (1 / 252) - 1
UP = ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE")


def overlay(res, sleeve_ret: pd.Series, on: pd.Series | None) -> pd.Series:
    """Equity curve when the idle fraction earns `sleeve_ret` instead of the cash rate."""
    eq = res.equity
    r = eq.pct_change().fillna(0)
    w = (1 - res.exposure).clip(0, 1)
    if on is not None:
        w = w * on.reindex(w.index).fillna(False).astype(float)
    wp = w.shift(1).fillna(0)                                   # decided at the previous close
    extra = wp * (sleeve_ret.reindex(r.index).fillna(0) - RF) - COST * w.diff().abs().fillna(0).shift(1).fillna(0)
    return (1 + r + extra).cumprod()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final = json.loads((OUT.parent / "final.json").read_text())
    cfg = pf.Config(**final["cfg"])
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    n500 = pd.read_parquet(Path(__file__).resolve().parent.parent / "data" / "prices" / "NSE_NIFTY500-INDEX.parquet")["close"]
    n500.index = pd.to_datetime(n500.index)
    up = lab.ms.isin(UP)
    dates = lab.U.index[lab.U.index >= "2015-06-01"]
    gr = fw.compute(lab.P, lab.U, lab.S["rs_ibd"], dates, loaded=fw.load())["graham"]
    rows = []
    for period, (a, b) in {"2016-22": tune.TUNE, "2023+": tune.HOLD}.items():
        res, big = lab.run(sc, cfg, period=(a, b)), lab.run(sc.where(lab.big), cfg, period=(a, b))
        graham = lab.run(gr["score"], fwtest.CFG["graham"], period=(a, b), entry_ok=gr["entry"])
        sleeves = {"N": n500.pct_change(), "G": graham.equity.pct_change()}
        variants = {"base (cash at 6%)": None, "N1 Nifty 500 always": ("N", None), "N2 Nifty 500 in uptrends": ("N", up),
                    "G1 Graham list always": ("G", None), "G2 Graham list in uptrends": ("G", up)}
        for name, v in variants.items():
            e = res.equity if v is None else overlay(res, sleeves[v[0]], v[1])
            eb = big.equity if v is None else overlay(big, sleeves[v[0]], v[1])
            st = pf.stats(e)
            row = {"period": period, "variant": name, "CAGR %": st["CAGR %"], "Sharpe": st["Sharpe"],
                   "maxDD %": st["maxDD %"], "big Sharpe": pf.stats(eb)["Sharpe"]}
            if period == "2016-22":
                for h, (x, y) in tune.HALVES.items():
                    row[f"Sharpe {h}"] = pf.stats(e.loc[x:y])["Sharpe"]
                    row[f"CAGR {h}"] = pf.stats(e.loc[x:y])["CAGR %"]
            rows.append(row)
            print(f"  {period:<8} {name:<28} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5}  maxDD {row['maxDD %']:>6}"
                  + (f"  (16-19 {row['Sharpe 16-19']:>5} | 20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})"
                     if period == "2016-22" else f"  (big {row['big Sharpe']:>5})"), flush=True)
    t = pd.DataFrame(rows)
    T = t[t.period == "2016-22"].set_index("variant")
    b = T.iloc[0]
    T["passes bar"] = [i > 0 and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       for i, (_, r) in enumerate(T.iterrows())]
    t.to_csv(OUT / "results.csv", index=False)
    win = T[T["passes bar"]]
    print("\nDECISION:", ", ".join(win.index) + " pass the bar" if len(win) else "no variant passes the bar")


if __name__ == "__main__":
    main()
