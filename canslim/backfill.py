"""Rebuild the scans for days the scheduled run missed, so the paper portfolio has no gaps.

For each missed trading day it recomputes the snapshot, market state and CAN SLIM list using only prices up to
that day and fundamentals already announced by that day (the same code path as canslim.daily), stores them in
data/canslim.db and data/history/picks.csv, then rebuilds the paper portfolio.
Not rebuilt: the HTML report, earnings/emerging lists and other-framework lists for those days.
Caveat: fundamentals are today's files filtered by announcement date; later restatements are not undone.

usage: python -m canslim.backfill 2026-10-24 2026-11-12
"""
import sys

import pandas as pd

from canslim import daily, data, db, factors, paper, sectors
from canslim.system import market_state


def main(a: str, b: str):
    P = data.panels(refresh=True)
    F = factors.price_factors(P)
    U = factors.universe_mask(P, F)
    fund = data.fundamentals()
    ev = factors.fundamental_events(fund)
    ms_all = market_state(P)
    ind = {k: f["industry"] for k, f in fund.items()}
    sec = pd.Series({k: f["sector"] for k, f in fund.items()})
    c = db.connect()
    have = {r[0] for r in c.execute("SELECT DISTINCT date FROM snapshot")}
    days = [d for d in P["close"].loc[a:b].index if f"{d:%Y-%m-%d}" not in have]
    hist_f = daily.HISTORY / "picks.csv"
    hist = pd.read_csv(hist_f, parse_dates=["date"])
    for d in days:
        FP = factors.fundamental_panel(ev, pd.DatetimeIndex([d]), daily.FUND_COLS)
        row = pd.DataFrame({k: v.loc[d] for k, v in F.items()})
        for k, v in FP.items():
            row[k] = v.iloc[-1].reindex(row.index)
        row["universe"] = U.loc[d].reindex(row.index).fillna(False)
        row["has_f"] = row.np_yoy.notna()
        elig = row.universe & row.has_f
        row["rs"] = row.rs_ibd.where(elig).rank(pct=True) * 99
        row["industry"] = pd.Series(ind).reindex(row.index)
        row["sector"] = sec.reindex(row.index)
        g = row[elig].groupby("industry").rs.agg(["mean", "count"])
        g = g[g["count"] >= 3]
        row["group_rank"] = row.industry.map(g["mean"].rank(ascending=False).astype(int))
        row["groups_total"] = len(g)
        rad = sectors.radar(F["rs_ibd"].loc[:d], U.loc[:d], ind)
        row["group_warn"] = row.industry.map(sectors.group_warnings(rad))
        snap = row[elig].copy()
        snap["failed"] = [daily.evaluate(r) for _, r in snap.iterrows()]
        snap["n_fail"] = snap.failed.map(len)
        picks, per = [], {}
        for s, r in snap[snap.n_fail == 0].sort_values("rs", ascending=False).iterrows():
            if r.industry and per.get(r.industry, 0) >= 3:
                continue
            per[r.industry] = per.get(r.industry, 0) + 1
            picks.append(s)
            if len(picks) == 10:
                break
        state = ms_all.loc[:d].iloc[-1]
        closes = P["close"].loc[:d].ffill().iloc[-1]
        new = pd.DataFrame([{"date": d, "rank": i + 1, "symbol": s, "close": closes[s],
                             "rs": round(snap.at[s, "rs"], 1), "market": state} for i, s in enumerate(picks)])
        db.store_market(c, d, state)
        db.store_snapshot(c, d, snap, closes)
        db.store_list(c, d, "canslim", new.drop(columns="date").assign(industry=[snap.at[s, "industry"] for s in picks])
                      if len(new) else new)
        db.store_radar(c, d, rad)
        c.commit()
        hist = pd.concat([hist[hist.date != d], new])
        print(f"{d:%Y-%m-%d} {state:<18} {len(snap)} stocks, picks: {', '.join(picks) or 'none'}", flush=True)
    hist.sort_values(["date", "rank"]).to_csv(hist_f, index=False)
    print("paper portfolio:", paper.run(c))
    c.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
