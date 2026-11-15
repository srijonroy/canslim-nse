"""How much of the headline result could be luck?

1) Block bootstrap: resample the system's daily returns in 3-month blocks (keeps streaks and crashes intact),
   2,000 times per period -> 5th / median / 95th percentile of return a year, Sharpe and worst drop.
2) Paired bootstrap vs the Nifty 500 and the Nifty200 Momentum 30 index: the same blocks for both curves ->
   range of the yearly lead and the share of resamples where the system is behind.
3) Random picks from the same pool: 200 runs where the stocks that pass the rules are chosen at random instead
   of by RS -> where the real system sits in that spread (does the ranking add anything?).
"""
import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim.exp import PERIODS, Experiment, Outcome, md_table

N_BOOT, BLOCK, N_RAND, SEED = 2000, 63, 200, 7


def boot_idx(n, rng):
    starts = rng.integers(0, n - BLOCK, size=n // BLOCK + 1)
    return np.concatenate([np.arange(s, s + BLOCK) for s in starts])[:n]


def curve_stats(r: np.ndarray) -> tuple:
    e = np.cumprod(1 + r)
    yrs = len(r) / 252
    cagr = e[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(252)
    dd = (e / np.maximum.accumulate(e) - 1).min()
    return cagr * 100, (cagr - 0.06) / vol if vol else np.nan, dd * 100


def run(ctx) -> Outcome:
    rng = np.random.default_rng(SEED)
    n500, mom = ctx.index("NIFTY 500"), ctx.index("NIFTY200 MOMENTUM 30")
    rows, rand_rows = [], []
    for pname, period in PERIODS.items():
        res = ctx.run(period=period)
        last = min(n500.index[-1], mom.index[-1])
        e = res.equity.loc[:last]
        r = e.pct_change().dropna()
        rb = {k: s.reindex(e.index, method="ffill").pct_change().reindex(r.index).fillna(0).values
              for k, s in (("Nifty 500", n500), ("Momentum 30", mom))}
        rv = r.values
        sims, ex = [], {k: [] for k in rb}
        for _ in range(N_BOOT):
            i = boot_idx(len(rv), rng)
            sims.append(curve_stats(rv[i]))
            for k, x in rb.items():
                ex[k].append(curve_stats(rv[i])[0] - curve_stats(x[i])[0])
        s = np.array(sims)
        real = curve_stats(rv)
        row = {"period": pname,
               "return/yr actual": round(real[0], 1),
               "return/yr 5%..95%": f"{np.percentile(s[:, 0], 5):.1f} .. {np.percentile(s[:, 0], 95):.1f}",
               "Sharpe actual": round(real[1], 2),
               "Sharpe 5%..95%": f"{np.percentile(s[:, 1], 5):.2f} .. {np.percentile(s[:, 1], 95):.2f}",
               "worst drop 5%..95%": f"{np.percentile(s[:, 2], 5):.1f} .. {np.percentile(s[:, 2], 95):.1f}"}
        for k, v in ex.items():
            v = np.array(v)
            row[f"lead over {k} 5%..95%"] = f"{np.percentile(v, 5):+.1f} .. {np.percentile(v, 95):+.1f}"
            row[f"% of resamples behind {k}"] = round((v <= 0).mean() * 100, 1)
        # random picks from the same pool
        pool = ctx.score
        rnd = []
        for j in range(N_RAND):
            sc = pd.DataFrame(rng.random(pool.shape), index=pool.index, columns=pool.columns).where(pool.notna())
            rnd.append(ctx.run(score=sc, period=period).stats["CAGR %"])
            if (j + 1) % 50 == 0:
                print(f"  {pname}: random-pick runs {j + 1}/{N_RAND}", flush=True)
        rnd = np.array(rnd)
        row["random picks return/yr 5%..95%"] = f"{np.percentile(rnd, 5):.1f} .. {np.percentile(rnd, 95):.1f}"
        row["system's percentile among random picks"] = round((rnd < res.stats["CAGR %"]).mean() * 100, 0)
        rows.append(row)
        print("  " + " | ".join(f"{k}: {v}" for k, v in row.items()), flush=True)
    t = pd.DataFrame(rows)
    T = t.set_index("period")
    a, b = T.loc["2016-22"], T.loc["2023+"]
    pct = "system's percentile among random picks"
    takeaway = (f"2016-22: {a['return/yr actual']}% a year, but the plausible range is {a['return/yr 5%..95%']}% "
                f"(Sharpe {a['Sharpe 5%..95%']}). 2023-26: {b['return/yr actual']}%, range {b['return/yr 5%..95%']}%. "
                f"The system was behind the Nifty 500 in {a['% of resamples behind Nifty 500']}% / "
                f"{b['% of resamples behind Nifty 500']}% of resamples and behind the Momentum 30 index in "
                f"{a['% of resamples behind Momentum 30']}% / {b['% of resamples behind Momentum 30']}%. "
                f"Picking at random from the same pool: {a['random picks return/yr 5%..95%']}% and "
                f"{b['random picks return/yr 5%..95%']}%; the RS ranking sits at the "
                f"{a[pct]:.0f}th and {b[pct]:.0f}th percentile.")
    lead = max(a["% of resamples behind Nifty 500"], b["% of resamples behind Nifty 500"])
    decision = (f"Lead over the Nifty 500 is unlikely to be luck (behind in at most {lead}% of resamples)"
                if lead < 5 else f"Lead over the Nifty 500 could be luck (behind in up to {lead}% of resamples)")
    body = md_table(t.T.reset_index().rename(columns={"index": "measure", 0: "2016-22", 1: "2023+"}))
    return Outcome(t, decision, takeaway, body, status="Checked")


EXPERIMENT = Experiment(
    slug="error-ranges", title="How much of the result could be luck?",
    question="With a pool of about four stocks on a typical day, the results rest on few trades. What range of "
             "results is plausible, and does the RS ranking beat random picks from the same pool?",
    tags="statistics, luck, bootstrap, random picks, evidence", bar=None, run=run,
    method=f"Block bootstrap ({N_BOOT} resamples of {BLOCK}-day blocks of daily returns; the same blocks for the "
           f"system and each index in the comparison). Random picks: {N_RAND} runs per period choosing among the "
           f"stocks that pass the rules at random instead of by RS, everything else unchanged. 'Range' = 5th to "
           f"95th percentile.")
