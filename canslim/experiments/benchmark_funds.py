"""Does the system beat simply buying a momentum index fund?

Benchmarks are NSE price indices (no dividends, ~1%/yr understated); a fund also charges ~0.3-0.5%/yr. The two
roughly cancel, so the indices are used as they are. The system's idle cash earns 6%/yr as in every backtest.
All curves are compared on the same days (the index files end earlier than the price data).
"""
import pandas as pd

from canslim import portfolio as pf
from canslim.exp import PERIODS, Experiment, Outcome, md_table

FUNDS = {"Nifty 500": "NIFTY 500", "Nifty200 Momentum 30": "NIFTY200 MOMENTUM 30",
         "Nifty500 Momentum 50": "NIFTY500 MOMENTUM 50", "Midcap150 Momentum 50": "NIFTY MIDCAP150 MOMENTUM 50"}


def run(ctx) -> Outcome:
    idx = {k: ctx.index(v) for k, v in FUNDS.items()}
    last = min(s.index[-1] for s in idx.values())
    rows, curves = [], {}
    for pname, (a, b) in {**PERIODS, "2016-now": (PERIODS["2016-22"][0], None)}.items():
        res = ctx.run(period=(a, b))
        sysq = res.equity.loc[:last]
        days = sysq.index
        cur = {"CAN SLIM system": sysq}
        for k, s in idx.items():
            cur[k] = s.reindex(days, method="ffill").dropna()
        sys_r = sysq.pct_change()
        for k, e in cur.items():
            st = pf.stats(e)
            rows.append({"period": pname, "holding": k, "CAGR %": st["CAGR %"], "Sharpe": st["Sharpe"],
                         "maxDD %": st["maxDD %"], "corr with system": round(e.pct_change().corr(sys_r), 2)})
        if pname == "2016-now":
            curves = cur
    t = pd.DataFrame(rows)
    T = t.set_index(["period", "holding"])
    mom = [k for k in FUNDS if "Momentum" in k]
    beats = {p: all(T.loc[(p, "CAN SLIM system"), "CAGR %"] > T.loc[(p, m), "CAGR %"] and
                    T.loc[(p, "CAN SLIM system"), "maxDD %"] > T.loc[(p, m), "maxDD %"] for m in mom)
             for p in PERIODS}
    best = {p: T.loc[p].loc[mom, "CAGR %"].idxmax() for p in PERIODS}
    s16, s23 = T.loc[("2016-22", "CAN SLIM system")], T.loc[("2023+", "CAN SLIM system")]
    b16, b23 = T.loc[("2016-22", best["2016-22"])], T.loc[("2023+", best["2023+"])]
    if all(beats.values()):
        decision = "The system beats every momentum index on both return and worst drop, in both periods - keep it"
    elif any(beats.values()):
        decision = ("The system beats every momentum index in " + " and ".join(p for p, v in beats.items() if v)
                    + " only - mixed evidence")
    else:
        decision = "A momentum index fund matched or beat the system in both periods - the system's value is in doubt"
    yr = pd.DataFrame({k: pf.yearly(v) for k, v in curves.items()})
    takeaway = (f"In 2016-22 the system made {s16['CAGR %']}% a year with a worst drop of {s16['maxDD %']}%; "
                f"the best momentum index ({best['2016-22']}) made {b16['CAGR %']}% with {b16['maxDD %']}%. "
                f"In 2023-26: system {s23['CAGR %']}% / {s23['maxDD %']}%, best index ({best['2023+']}) "
                f"{b23['CAGR %']}% / {b23['maxDD %']}%. "
                f"Daily correlation with Nifty200 Momentum 30: {T.loc[('2016-now', 'Nifty200 Momentum 30'), 'corr with system']}. "
                + decision + ".")
    body = (md_table(t) + "\n\n**Year by year (% return).**\n\n" + md_table(yr.reset_index(names="year"))
            + f"\n\nIndex data ends {last.date()}; all curves stop there.")
    return Outcome(t, decision, takeaway, body,
                   status="Checked - system ahead" if all(beats.values()) else "Checked - see decision")


EXPERIMENT = Experiment(
    slug="benchmark-funds", title="The system vs a momentum index fund",
    question="Does the system do better than just buying a momentum index fund, which needs no work?",
    tags="benchmark, momentum, index fund, evidence", bar=None, run=run,
    method="Same days for every curve. NSE price indices (no dividends, about 1% a year understated, roughly "
           "offset by a fund's 0.3-0.5% fee). The system is the live rules (data/tune/final.json) with 6% on idle "
           "cash. 'Beats' = higher return AND a shallower worst drop than every momentum index.")
