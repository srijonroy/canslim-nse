"""Test: an 'emerging / turnaround' list next to CAN SLIM.

Rules (fixed before running):
  earnings: profit +50% YoY in each of the last 2 quarters OR operating margin +6 pts YoY
  price:    RS >= 80, uptrend (price > 50 > 150 > 200-day, 200-day rising), within 15% of the 52-week high, price >= 20
  NO ROE / 3-year growth rule (these blocked Laurus 2019-21 and Wockhardt 2024-25). Ranked by RS.
  Versions: liquidity >= Rs 5 Cr/day at 0.3% cost per side, and >= Rs 1 Cr/day at 0.6% per side.
  Portfolio exactly as the tuned system: 10 names, keep while rank <= 30, no new buys in a correction.

Decision bar (fixed before running), judged on 2016-2022 only:
  * add as a SEPARATE list in the report if it beats the equal-weight liquid universe in both halves
  * replace / merge into CAN SLIM only if Sharpe beats tuned CAN SLIM by >= 0.03 in both halves
2023-26 is shown but is NOT independent: the two earnings signals were chosen after seeing it.

usage: python -m canslim.emerging
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune
from canslim.data import CACHE
from canslim.system import benchmarks

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "emerging"
HALVES = {"2016-19": ("2016-01-01", "2019-12-31"), "2020-22": ("2020-01-01", "2022-12-31")}
LATER = ("2023-01-01", None)
CASES = ["LAURUSLABS", "WOCKPHARMA", "AVANTIFEED"]


def panels(lab):
    ds = pd.read_pickle(CACHE / "winners_ds.pkl")
    idx, cols = lab.S["trend"].index, lab.P["close"].columns
    get = lambda k: ds[k].unstack("sym").reindex(index=idx, columns=cols)
    return {k: get(k) for k in ("rs", "trend", "prox_high", "opm_chg", "np_min2", "value_cr")}


def emerging_score(X, P, floor_cr):
    px = P["close"].reindex(X["rs"].index)
    earn = (X["opm_chg"] >= 6) | (X["np_min2"] >= 50)
    ok = earn & (X["rs"] >= 80) & (X["trend"] == 1) & (X["prox_high"] >= 0.85) & (px >= 20) & (X["value_cr"] >= floor_cr)
    return X["rs"].where(ok)


def half_stats(eq):
    out = {}
    for h, (a, b) in HALVES.items():
        st = pf.stats(eq.loc[a:b])
        out[f"CAGR {h}"], out[f"Sharpe {h}"], out[f"maxDD {h}"] = st["CAGR %"], st["Sharpe"], st["maxDD %"]
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    final = json.loads((OUT.parent / "final.json").read_text())
    rules, cfg = final["rules"], pf.Config(**final["cfg"])
    print("loading data ...", flush=True)
    lab = tune.Lab()
    X = panels(lab)
    systems = {
        "CAN SLIM tuned (current)": (tune.book_score(lab.S, lab.U, lab.has_f, rules), cfg),
        "Emerging, >= Rs 5 Cr/day": (emerging_score(X, lab.P, 5), cfg),
        "Emerging, >= Rs 1 Cr/day": (emerging_score(X, lab.P, 1), pf.Config(**{**cfg.__dict__, "cost": 0.006})),
    }
    cs = systems["CAN SLIM tuned (current)"][0]
    em5 = systems["Emerging, >= Rs 5 Cr/day"][0]
    systems["CAN SLIM + Emerging (5 Cr), by RS"] = (cs.combine_first(em5), cfg)

    rows, curves, trades = [], {}, {}
    for name, (sc, c) in systems.items():
        pool = float(sc.loc["2016":"2022"].notna().sum(axis=1).median())
        tune_res = lab.run(sc, c, period=("2016-01-01", "2022-12-31"))
        later = lab.run(sc, c, period=LATER)
        curves[name], trades[name] = tune_res.equity, tune_res.trades
        rows.append({"system": name, "pool median": pool, **tune_res.stats, **half_stats(tune_res.equity),
                     "CAGR 2023-26*": later.stats["CAGR %"], "maxDD 2023-26*": later.stats["maxDD %"]})
        print(f"  {name:<36} 2016-22 CAGR {tune_res.stats['CAGR %']:>5}  Sharpe {tune_res.stats['Sharpe']:>5}  "
              f"maxDD {tune_res.stats['maxDD %']:>6}  pool {pool:.0f}", flush=True)
    rng = np.random.default_rng(3)
    sc1, c1 = systems["Emerging, >= Rs 1 Cr/day"]
    rnd = [lab.run(pd.DataFrame(rng.random(sc1.shape), index=sc1.index, columns=sc1.columns).where(sc1.notna()),
                   c1, period=("2016-01-01", "2022-12-31")) for _ in range(10)]
    rr = pd.DataFrame([{**r.stats, **half_stats(r.equity)} for r in rnd]).median().round(2)
    rows.append({"system": "random picks from Emerging 1 Cr pool (median of 10)", **rr.to_dict()})
    for k, v in benchmarks(lab.P, lab.U, "2016-01-01", "2022-12-31").items():
        rows.append({"system": k, **pf.stats(v), **half_stats(v)})
        curves[k] = v
    t = pd.DataFrame(rows).set_index("system")
    t.to_csv(OUT / "results.csv")
    pd.DataFrame(curves).to_parquet(OUT / "curves.parquet")
    cols = ["pool median", "CAGR %", "Sharpe", "maxDD %", "CAGR 2016-19", "Sharpe 2016-19", "maxDD 2016-19",
            "CAGR 2020-22", "Sharpe 2020-22", "maxDD 2020-22", "trades/yr", "win %", "invested %",
            "CAGR 2023-26*", "maxDD 2023-26*"]
    print("\n=== 2016-2022 (decision period)   * 2023-26 not independent")
    print(t[[c for c in cols if c in t.columns]].to_string())

    ew = t.loc["Equal-weight liquid universe"]
    base = t.loc["CAN SLIM tuned (current)"]
    print("\n=== Decisions (bar fixed before running)")
    for name in ["Emerging, >= Rs 5 Cr/day", "Emerging, >= Rs 1 Cr/day", "CAN SLIM + Emerging (5 Cr), by RS"]:
        r = t.loc[name]
        sep = all(r[f"CAGR {h}"] > ew[f"CAGR {h}"] for h in HALVES)
        rep = all(r[f"Sharpe {h}"] >= base[f"Sharpe {h}"] + 0.03 for h in HALVES)
        print(f"  {name:<36} separate list: {'YES' if sep else 'no'} | beats CAN SLIM in both halves: {'YES' if rep else 'no'}")

    print("\n=== Did the lists hold the case stocks? (2016-22 trades)")
    for name, tr in trades.items():
        if tr.empty:
            continue
        x = tr[tr.sym.isin(CASES)]
        for r in x.itertuples():
            print(f"  {name:<36} {r.sym:<11} {r.entry_date:%d %b %Y} @ {r.entry:8.1f} -> {r.exit_date:%d %b %Y} "
                  f"@ {r.exit:8.1f}  {r.ret * 100:+6.1f}%  ({r.why})")
    for name, tr in trades.items():
        if not tr.empty:
            tr.to_csv(OUT / f"trades_{name.split(',')[0].split(' (')[0].replace(' ', '_').replace('+', 'plus')}.csv", index=False)


if __name__ == "__main__":
    main()
