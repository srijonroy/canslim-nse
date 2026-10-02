"""Robustness checks for the chosen system (book_rules, M=no_new, no hard stop).

A real edge should survive: different position counts, holding buffers, double
costs, monthly instead of weekly rebalancing, large/liquid names only, and it
should clearly beat RANDOM picks drawn from the same book-gated pool (which
tells us whether the ranking adds value beyond the filters).

usage: python -m canslim.robust
"""
import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim.research import build
from canslim.system import OUT, benchmarks, market_state, score_book_rules

START = "2016-01-01"


def main():
    pd.set_option("display.width", 250)
    B = build()
    S, U, has_f, P = B["S"], B["U"], B["has_f"], B["P"]
    industry = {k: f["industry"] for k, f in B["fund"].items()}
    ms = market_state(P).reindex(P["close"].index).ffill()
    base = score_book_rules(S, U, has_f)
    passing = base.notna().sum(axis=1)
    print(f"stocks passing the book rules per week: median {passing.median():.0f}, "
          f"10th pct {passing.quantile(.1):.0f}, 90th pct {passing.quantile(.9):.0f}")
    run = lambda sc, **kw: pf.simulate(sc.loc[START:], P["open"], P["close"],
                                       pf.Config(**{"market": "no_new", "stop": None, **kw}), ms, industry,
                                       start=START)
    rows, curves = [], {}

    def add(name, res):
        rows.append({"variant": name, **res.stats})
        curves[name] = res.equity
        print(name, res.stats, flush=True)

    add("BASE: n=10 keep=30 weekly cost 0.3%", run(base))
    for n in (5, 20):
        add(f"n={n}", run(base, n=n, keep_rank=n * 3))
    for k in (10, 60):
        add(f"keep_rank={k}", run(base, keep_rank=k))
    add("cost 0.6%/side", run(base, cost=0.006))
    monthly = base[base.index.to_series().dt.month.diff().ne(0).values]
    add("monthly rebalance", run(monthly))
    big = base.where(S["turnover"] >= 25e7)
    add("large/liquid only (>= Rs 25 Cr/day)", run(big))
    add("no industry cap", run(base, max_per_group=0))
    add("with 8% stop", run(base, stop=0.08))
    # random picks from the same gated pool: 20 seeds
    rnd = []
    rng = np.random.default_rng(7)
    for seed in range(20):
        r = pd.DataFrame(rng.random(base.shape), index=base.index, columns=base.columns).where(base.notna())
        rnd.append(run(r).stats)
    rs = pd.DataFrame(rnd)
    rows.append({"variant": "RANDOM picks from same pool (median of 20)", **rs.median().round(2).to_dict()})
    print("random: CAGR range", rs["CAGR %"].min(), "-", rs["CAGR %"].max())
    for k, v in benchmarks(P, U, START, S["rs_ibd"].index[-1]).items():
        rows.append({"variant": k, **pf.stats(v)})
    t = pd.DataFrame(rows).set_index("variant")
    t.to_csv(OUT / "robustness.csv")
    print("\n=== Robustness (2016 -> now)")
    print(t.to_string())
    print(f"\nrandom CAGR range over 20 seeds: {rs['CAGR %'].min()} .. {rs['CAGR %'].max()}")


if __name__ == "__main__":
    main()
