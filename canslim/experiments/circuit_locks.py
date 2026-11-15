"""Realism check: can the backtest's buys and sells actually be filled when a stock is stuck at its circuit limit?

The simulator fills every order at the next open. A small cap frozen at its upper circuit all day (high == low,
up on the day) has only buyers, so a buy cannot be filled; frozen at the lower circuit, a sell cannot.
  strict       block buys on whole-day upper locks, sells on whole-day lower locks (sell retried next day)
  pessimistic  also block when the stock opens at the day's high after a >= 4.9% gap up (likely opened at the
               circuit) / at the day's low after a >= 4.9% gap down
This is a realism check, not an idea to adopt for profit: if it costs much, backtests should include it.
"""
import pandas as pd

from canslim.exp import Experiment, Variant


def masks(ctx, pessimistic=False):
    P = ctx.lab.P
    o, h, l, c, v = P["open"], P["high"], P["low"], P["close"], P["volume"]
    gap = o / c.shift() - 1
    frozen = (h == l) & (v > 0)
    up, dn = frozen & (gap > 0), frozen & (gap < 0)
    if pessimistic:
        up |= (o >= h) & (gap >= 0.049)
        dn |= (o <= l) & (gap <= -0.049)
    return {"no_buy": up, "no_sell": dn}


def explain(t, passed):
    T = t.set_index(["period", "variant"])
    lines = []
    for p in ("2016-22", "2023+"):
        b, s, x = (T.loc[(p, n)] for n in ("live backtest (fills always)", "strict locks", "pessimistic locks"))
        lines.append(f"{p}: {b['CAGR %']}% a year with every order filled, {s['CAGR %']}% if whole-day circuit "
                     f"locks block orders, {x['CAGR %']}% in the pessimistic case")
    cost = T.loc[("2016-22", "live backtest (fills always)"), "CAGR %"] - T.loc[("2016-22", "pessimistic locks"), "CAGR %"]
    verdict = ("Circuit locks barely matter for this system - the backtest numbers stand."
               if cost < 1 else "Circuit locks cost real return - backtests overstate the system.")
    return "; ".join(lines) + ". " + verdict, ""


EXPERIMENT = Experiment(
    slug="circuit-locks", title="Can the backtest's orders be filled at circuit limits?",
    question="The backtest assumes every buy and sell fills at the next open. Small caps often lock at their "
             "upper circuit on breakouts and lower circuit on bad news. How much of the result depends on fills "
             "that could not happen?",
    tags="realism, circuit limits, execution, small caps, evidence", bar=None, explain=explain,
    method="Same rules and dates. A day is 'locked' when high equals low (one price all day) with trading "
           "volume; up-locked days block buys, down-locked days block sells (retried at the next open). The "
           "pessimistic version also blocks opens at the day's extreme after a gap of 4.9% or more.",
    variants=[Variant("live backtest (fills always)"),
              Variant("strict locks", sim=lambda ctx: masks(ctx)),
              Variant("pessimistic locks", sim=lambda ctx: masks(ctx, True))])
