"""Audit: after the system SELLS a stock, does it catch the stock again if it later becomes a big winner?

For every exit in the tuned system (2016-22), look 36 months ahead (prices up to today are used for the
look-ahead only; no rule is chosen here). For exits followed by a >= 3x run from the exit price:
  * did the system buy it back, how long after the exit, at what price vs the exit price
  * how much of the run (exit price -> peak) did the re-entries capture
Also: every stock in the liquid universe that went >= 5x within 2016-22 -- was it ever held, and when.

usage: python -m canslim.reentry
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "reentry"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    final = json.loads((OUT.parent / "final.json").read_text())
    print("loading data ...", flush=True)
    lab = tune.Lab()
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    cfg = pf.Config(**final["cfg"])
    # run to the end of the data so re-entries after 2022 are seen too
    res = lab.run(sc, cfg, period=("2016-01-01", None))
    t = res.trades.copy()
    t["entry_date"], t["exit_date"] = pd.to_datetime(t.entry_date), pd.to_datetime(t.exit_date)
    C = lab.P["close"]
    last_day = C.index[-1]
    rows = []
    for x in t[t.exit_date <= "2022-12-31"].itertuples():
        s = C[x.sym].dropna()
        fwd = s.loc[x.exit_date: x.exit_date + pd.DateOffset(months=36)]
        if len(fwd) < 60:
            continue
        peak_px, peak_d = fwd.max(), fwd.idxmax()
        run = peak_px / x.exit - 1
        later = t[(t.sym == x.sym) & (t.entry_date > x.exit_date) & (t.entry_date <= peak_d)]
        # still-open position bought back (not in trades list)
        captured = 0.0
        for y in later.itertuples():
            lo = max(y.entry, 1e-9)
            captured += np.log(min(y.exit, peak_px) / lo) if y.exit > lo else np.log(y.exit / lo)
        rows.append({"sym": x.sym, "exit_date": x.exit_date.date(), "exit": x.exit, "trade ret": round(x.ret, 3),
                     "peak after": round(peak_px, 2), "peak date": peak_d.date(), "run x": round(1 + run, 2),
                     "re-bought": len(later),
                     "first re-buy": later.entry_date.min().date() if len(later) else None,
                     "re-buy vs exit": round(later.entry.iloc[0] / x.exit - 1, 3) if len(later) else None,
                     "share of run captured": round(captured / np.log(1 + run), 2) if run > 0 else None})
    A = pd.DataFrame(rows)
    A.to_csv(OUT / "exits.csv", index=False)
    big = A[A["run x"] >= 3].drop_duplicates("sym", keep="first").sort_values("run x", ascending=False)
    print(f"\nexits 2016-22: {len(A)}; followed by a >=3x run within 36m: {len(big)} stocks")
    print(f"  re-bought at least once before the peak: {(big['re-bought'] > 0).sum()} / {len(big)}")
    print(f"  median share of the run captured: {big['share of run captured'].median()}")
    print(big.to_string(index=False))

    # universe-wide: liquid stocks that went >= 5x from any point within 2016-22 (trough -> later peak)
    liq = lab.S["turnover"] >= 1e7
    held = set(t.sym)
    rows = []
    for s in C.columns:
        p = C[s].loc["2016":"2022"].dropna()
        ok = liq[s].loc["2016":"2022"] if s in liq.columns else None
        if len(p) < 250 or ok is None or ok.mean() < 0.3:
            continue
        mult = p / p.cummin()
        if mult.max() < 5:
            continue
        pk = mult.idxmax(); tr = p.loc[:pk].idxmin()
        ht = t[(t.sym == s) & (t.entry_date >= tr) & (t.entry_date <= pk)]
        rows.append({"sym": s, "low date": tr.date(), "low": round(p[tr], 2), "peak date": pk.date(),
                     "peak": round(p[pk], 2), "x": round(mult.max(), 1), "trades in run": len(ht),
                     "first buy": ht.entry_date.min().date() if len(ht) else None,
                     "first buy price x from low": round(ht.entry.iloc[0] / p[tr], 2) if len(ht) else None,
                     "days held in run": int((ht.exit_date - ht.entry_date).dt.days.sum()) if len(ht) else 0,
                     "ever held": s in held})
    U = pd.DataFrame(rows).sort_values("x", ascending=False)
    U.to_csv(OUT / "five_baggers.csv", index=False)
    print(f"\nliquid stocks that went >= 5x (low -> high) inside 2016-22: {len(U)}")
    print(f"  held at some point during the run: {(U['trades in run'] > 0).sum()}")
    print(U.head(40).to_string(index=False))


if __name__ == "__main__":
    main()
