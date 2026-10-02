"""Factor research: which of the book's ideas actually predict NSE returns?

For every factor, on weekly dates within the liquid universe:
  * Spearman IC vs forward return (entry next day's open -> exit h days later)
  * quintile returns in excess of the universe average (Q5 - Q1 spread)
reported per regime so a factor must work in more than one market to count.
Plus a "model book" study: what did the biggest winners look like before they ran?

usage: python -m canslim.research
"""
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import data, factors

OUT = Path(__file__).resolve().parent.parent / "data" / "research"
PERIODS = {"2015-19": ("2015-01-01", "2019-12-31"), "2020-22": ("2020-01-01", "2022-12-31"),
           "2023-26": ("2023-01-01", "2026-12-31")}
FUND_COLS = ["np_yoy", "sales_yoy", "accel", "sue", "streak", "ttm_cagr3", "npm_chg", "np_pos",
             "roe", "inst_chg", "last_ann"]
# direction: +1 higher is better (per book/theory), -1 lower is better
SIGN = {"rs_ibd": 1, "mom_12_1": 1, "mom_6_1": 1, "ram": 1, "prox_high": 1, "new_high": 1, "trend": 1,
        "ud_vol": 1, "vol_surge": 1, "vol60": -1, "max_ret21": -1, "ext50": -1, "tight": 1,
        "turnover": 1, "np_yoy": 1, "sales_yoy": 1, "accel": 1, "sue": 1, "streak": 1, "ttm_cagr3": 1,
        "npm_chg": 1, "roe": 1, "inst_chg": 1, "group_rs": 1, "days_since_ann": -1}


def build(step: int = 5):
    """Everything sampled on rebalance dates: factor panels, universe, forward returns."""
    P = data.panels()
    F = factors.price_factors(P)
    U = factors.universe_mask(P, F)
    c = P["close"]
    dates = c.index[260::step]
    S = {k: v.reindex(dates) for k, v in F.items()}
    U = U.reindex(dates)
    fund = data.fundamentals()
    ev = factors.fundamental_events(fund)
    FP = factors.fundamental_panel(ev, dates, FUND_COLS)
    FP = {k: v.reindex(columns=c.columns) for k, v in FP.items()}
    day_no = pd.Series(dates.values.astype("datetime64[D]").astype("int64"), index=dates)
    FP["days_since_ann"] = FP.pop("last_ann").rsub(day_no, axis=0).where(lambda x: x >= 0)
    S.update(FP)
    rs_rank = S["rs_ibd"].where(U).rank(axis=1, pct=True)
    S["group_rs"] = factors.group_rs(rs_rank, {k: f["industry"] for k, f in fund.items()})
    has_f = S["np_yoy"].notna()
    o = P["open"]
    pos = {d: i for i, d in enumerate(c.index)}
    fwd = {}
    for h in (21, 63, 126):
        rows = []
        for d in dates:
            i = pos[d]
            if i + 1 + h < len(o):
                rows.append(o.iloc[i + 1 + h] / o.iloc[i + 1] - 1)
            else:
                rows.append(pd.Series(np.nan, index=c.columns))
        fwd[h] = pd.DataFrame(rows, index=dates).clip(-0.95, 5)
    return dict(P=P, S=S, U=U, has_f=has_f, fwd=fwd, fund=fund, events=ev, dates=dates)


def factor_stats(S, U, has_f, fwd, h=63, periods=PERIODS):
    rows = []
    fwd_h = fwd[h]
    for name, panel in S.items():
        sign = SIGN.get(name, 1)
        base_mask = U & has_f if name in FUND_COLS + ["days_since_ann"] else U & has_f
        x = (panel * sign).where(base_mask)
        y = fwd_h.where(base_mask)
        ics, spreads, q5ex, dts = [], [], [], []
        for d in x.index:
            xs, ys = x.loc[d], y.loc[d]
            ok = xs.notna() & ys.notna()
            if ok.sum() < 50:
                continue
            xr, yr = xs[ok].rank(), ys[ok].rank()
            ics.append(np.corrcoef(xr, yr)[0, 1])
            q = pd.qcut(xs[ok].rank(method="first"), 5, labels=False)
            m = ys[ok].groupby(q).mean()
            spreads.append(m.iloc[-1] - m.iloc[0])
            q5ex.append(m.iloc[-1] - ys[ok].mean())
            dts.append(d)
        s = pd.DataFrame({"ic": ics, "spread": spreads, "q5ex": q5ex}, index=dts)
        row = {"factor": name}
        for p, (a, b) in periods.items():
            sp = s[a:b]
            if len(sp) < 10:
                continue
            # overlapping h-day windows sampled weekly: effective n ~ len/(h/5)
            n_eff = max(len(sp) / (h / 5), 1)
            row[f"IC {p}"] = round(sp.ic.mean(), 3)
            row[f"t {p}"] = round(sp.ic.mean() / (sp.ic.std() / np.sqrt(n_eff)), 1)
            row[f"Q5-Q1 {p}"] = round(sp.spread.mean() * 100, 1)
        row["IC all"] = round(s.ic.mean(), 3)
        row["Q5 excess all"] = round(s.q5ex.mean() * 100, 2)
        rows.append(row)
    return pd.DataFrame(rows).set_index("factor")


def winners_study(S, U, has_f, fwd, h=126, top=0.02):
    """Model-book study: percentile of each factor at the start of the biggest h-day moves."""
    rows = []
    for d in S["rs_ibd"].index:
        m = U.loc[d] & has_f.loc[d]
        y = fwd[h].loc[d][m].dropna()
        if len(y) < 100:
            continue
        cut = y.quantile(1 - top)
        win = y[y >= cut].index
        for name, panel in S.items():
            x = (panel.loc[d] * SIGN.get(name, 1))[m]
            pr = x.rank(pct=True)
            rows.append({"date": d, "factor": name, "winner_pct": pr.reindex(win).median(),
                         "share_top30": (pr.reindex(win) >= 0.7).mean()})
    w = pd.DataFrame(rows)
    return w.groupby("factor")[["winner_pct", "share_top30"]].mean().round(2) \
        .sort_values("winner_pct", ascending=False)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    B = build()
    print("universe size (median):", int(B["U"].sum(axis=1).median()),
          "| with fundamentals:", int((B["U"] & B["has_f"]).sum(axis=1).median()))
    for h in (21, 63):
        st = factor_stats(B["S"], B["U"], B["has_f"], B["fwd"], h)
        st.to_csv(OUT / f"factor_stats_{h}d.csv")
        print(f"\n=== factor stats, forward {h} trading days (sign-adjusted: positive = book direction works)")
        print(st.sort_values("IC all", ascending=False).to_string())
    w = winners_study(B["S"], B["U"], B["has_f"], B["fwd"])
    w.to_csv(OUT / "winners_study.csv")
    print("\n=== Model book: median percentile of top-2% 6-month winners at the start (0.5 = average)")
    print(w.to_string())
