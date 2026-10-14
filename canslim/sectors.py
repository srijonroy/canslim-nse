"""Sector radar: which industry groups are strong now, for how long, and which just dropped out.

Group = Screener basic industry with >= 5 liquid stocks; strength = average RS percentile of its stocks,
ranked against the other groups every week (every 5th trading day).

Tested 2026-10-14 (canslim/sectortest.py, canslim/warntest.py, 2016-26):
  - the top 20% of groups beat the bottom 20% by ~4% over the next 3 months in every period;
  - a group stays in the top 20% for a median of 2 months (~15% last 6 months or more);
  - groups that drop out of the top 20% lag the market by 1-5% over the next 3-12 months.
  "Group dropped out" as a sell/avoid rule passed the 2016-22 bar but was worse in 2023-26, so it is an
  AMBER warning on holdings only (holdings.py), not a rule.
"""
import pandas as pd

MINM, TOP, LOOKBACK, WEEKS = 5, 0.8, 13, 60


def weekly_strength(rs_ibd: pd.DataFrame, U: pd.DataFrame, industry: dict):
    """weeks x groups strength percentile (0-1) and member counts, latest WEEKS weeks."""
    d = rs_ibd.index[::-5][:WEEKS][::-1]
    u = U.loc[d].fillna(False).astype(bool)
    rs = rs_ibd.loc[d].where(u).rank(axis=1, pct=True)
    ind = pd.Series(industry).reindex(rs.columns).dropna()
    rs, u = rs[ind.index], u[ind.index]
    g = rs.T.groupby(ind).mean().T
    n = rs.notna().T.groupby(ind).sum().T                 # members with an RS value
    return g.where(n >= MINM).rank(axis=1, pct=True), n


def radar(rs_ibd: pd.DataFrame, U: pd.DataFrame, industry: dict) -> pd.DataFrame:
    gp, n = weekly_strength(rs_ibd, U, industry)
    now = gp.iloc[-1].dropna()
    rows = []
    for g, p in now.items():
        top = (gp[g] >= TOP).tolist()
        streak = 0
        for v in reversed(top):
            if not v:
                break
            streak += 1
        status, since = "", None
        if p >= TOP:
            status = "New leader" if streak <= 2 else "Leading"
        else:
            past = top[-(LOOKBACK + 1):-1]
            if any(past):
                since = len(past) - max(i for i, v in enumerate(past) if v)
                status = "Dropped out"
            elif p <= 0.2:
                status = "Weak"
        rows.append({"group": g, "stocks": int(n[g].iloc[-1]), "strength": round(100 * p),
                     "weeks_top": streak, "weeks_since_drop": since, "status": status,
                     "weeks_top_last_year": int(sum(top[-52:]))})
    return pd.DataFrame(rows).sort_values("strength", ascending=False).reset_index(drop=True)


def group_warnings(rad: pd.DataFrame) -> dict:
    """group -> warning text, for groups that dropped out of the top 20% in the last 13 weeks."""
    d = rad[rad.status == "Dropped out"]
    return {r.group: f"group {r.group} dropped out of the top 20% {int(r.weeks_since_drop)} wk ago"
            for r in d.itertuples()}
