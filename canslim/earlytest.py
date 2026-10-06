"""Test: can the system get into winners EARLIER without hurting results?

Problem (2026-10-06): picks appear after big moves. 2016-22: for 5x+ runs the system bought, the median first
buy came 5.4x off the low with 1.9x left (~25% of the log-move). Each variant changes only how early it buys.
Fixed before running (base = current tuned rules incl. R6, ranked by RS, Rs 5 Cr build universe):
  E1  rank by LEAST stretched (smallest % above the 200-day) instead of highest RS. Same rules, same exits.
  E2  enter only "fresh qualifiers": stocks that started passing every rule within the last 8 weeks.
      Ranking and exits unchanged (entry filter only).
  E3  earlier trend rule: replace the full 50 > 150 > 200 template with "price above a rising 200-day"
      (200-day higher than 4 weeks ago) and RS >= 70 instead of 80. Other rules unchanged.
  E4  trade the earnings-monitor rule: profit up >= 50% in each of the last 2 quarters, price above the 50-day,
      within 15% of the high, ranked by RS. No quality rules (that's what the monitor list is).
Earliness, per trade: entry price / lowest close of the prior year ("x off 1y low") and % above the 200-day.

Decision bar (same as booktest/insttest), 2016-22: Sharpe >= base + 0.03 in BOTH halves, maxDD no worse than
base by > 3 points, large-cap Sharpe not below base, median pool >= 3. 2023-26 shown but already seen.

usage: python -m canslim.earlytest
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune
from canslim.data import CACHE

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "earlytest"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 260)
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, cfg = final["rules"], pf.Config(**final["cfg"])
    print("loading data ...", flush=True)
    lab = tune.Lab()
    S, C = lab.S, lab.P["close"]
    idx, cols = S["trend"].index, S["trend"].columns
    ma200 = C.rolling(200, min_periods=180).mean()
    ext200 = (C / ma200 - 1).reindex(idx).reindex(columns=cols)
    ma200_up = (ma200 > ma200.shift(20)).reindex(idx).reindex(columns=cols).fillna(False)
    above200 = (C > ma200).reindex(idx).reindex(columns=cols).fillna(False)
    low1y = C.rolling(250, min_periods=120).min()

    base = tune.book_score(S, lab.U, lab.has_f, rules)

    # E1: same pool, ranked by least stretched (higher score = closer to the 200-day)
    e1 = (-ext200).where(base.notna()).rank(axis=1, pct=True).where(base.notna())

    # E2: entry only within 8 weekly bars of the start of the current qualifying run
    q = base.notna().astype(int)
    run = q.apply(lambda s: s.groupby((s != s.shift()).cumsum()).cumsum())   # length of current passing streak
    fresh = (run >= 1) & (run <= 8)
    # entry_ok is checked on trading days; map weekly flags forward to the daily index
    fresh_d = fresh.reindex(C.index).ffill().fillna(False).astype(bool)

    # E3: earlier trend + RS >= 70
    r3 = {**rules, "trend": False, "rs": 70}
    e3 = tune.book_score(S, lab.U, lab.has_f, r3)
    e3 = e3.where(above200 & ma200_up)

    # E4: earnings-monitor rule, ranked by RS
    ds = pd.read_pickle(CACHE / "winners_ds.pkl")
    np_min2 = ds["np_min2"].unstack("sym").reindex(index=idx, columns=cols)
    elig = lab.U & lab.has_f
    rs = S["rs_ibd"].where(elig).rank(axis=1, pct=True)
    e4 = rs.where(elig & (np_min2 >= 50) & (S["ext50"] > 0) & (S["prox_high"] >= 0.85))

    variants = {"base (current)": (base, None), "E1 rank by least stretched": (e1, None),
                "E2 fresh qualifiers only (<= 8 wks)": (base, fresh_d),
                "E3 price > rising 200-day, RS >= 70": (e3, None), "E4 earnings-monitor rule": (e4, None)}

    rows = []
    for name, (sc, ok) in variants.items():
        res = lab.run(sc, cfg, entry_ok=ok)
        big = lab.run(sc.where(lab.big), cfg, entry_ok=ok)
        T = res.trades
        if len(T):
            ed = pd.to_datetime(T.entry_date)
            xlow = [T.entry.iloc[i] / low1y.at[d, s] if s in low1y.columns and d in low1y.index else np.nan
                    for i, (s, d) in enumerate(zip(T.sym, ed))]
            e200 = [C.at[d, s] / ma200.at[d, s] - 1 if s in C.columns and d in C.index else np.nan
                    for s, d in zip(T.sym, ed)]
        else:
            xlow, e200 = [np.nan], [np.nan]
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"],
               "pool median": float(sc.loc[tune.TUNE[0]:tune.TUNE[1]].notna().sum(axis=1).median()),
               "entry x off 1y low": round(float(np.nanmedian(xlow)), 2),
               "entry % above 200d": round(float(np.nanmedian(e200)) * 100, 0),
               "big winners (>=100%)": int((T.ret >= 1).sum()) if len(T) else 0}
        for h, (a, b) in tune.HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"], row[f"CAGR {h}"] = st["Sharpe"], st["CAGR %"]
        late = pf.stats(lab.run(sc, cfg, period=("2023-01-01", str(idx[-1].date())), entry_ok=ok).equity)
        row["Sharpe 23-26"], row["maxDD 23-26"], row["CAGR 23-26"] = late["Sharpe"], late["maxDD %"], late["CAGR %"]
        rows.append(row)
        print(f"  {name:<38} CAGR {row['CAGR %']:>5} Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
              f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5}) maxDD {row['maxDD %']:>6} "
              f"pool {row['pool median']:.0f} | entry {row['entry x off 1y low']}x off low, "
              f"{row['entry % above 200d']:.0f}% above 200d | 23-26 Sharpe {late['Sharpe']}", flush=True)

    t = pd.DataFrame(rows).set_index("variant")
    b = t.loc["base (current)"]
    t["passes bar"] = [n != "base (current)"
                       and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       and r["pool median"] >= 3
                       for n, r in t.iterrows()]
    t.to_csv(OUT / "results.csv")
    cols_ = ["CAGR %", "Sharpe", "maxDD %", "Sharpe 16-19", "Sharpe 20-22", "big Sharpe", "pool median",
             "trades/yr", "win %", "entry x off 1y low", "entry % above 200d", "big winners (>=100%)",
             "CAGR 23-26", "Sharpe 23-26", "maxDD 23-26", "passes bar"]
    print("\n=== 2016-2022 (23-26 shown, already seen)\n" + t[cols_].to_string())
    win = t[t["passes bar"]]
    print("\nDECISION:", ", ".join(win.index) + " pass the bar" if len(win)
          else "no early-entry variant passes the bar - keep the current system")


if __name__ == "__main__":
    main()
