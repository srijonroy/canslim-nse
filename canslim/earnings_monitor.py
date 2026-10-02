"""Daily earnings monitor: companies that just reported a strong quarter.

Wider than the CAN SLIM top 10: any NSE stock with Screener earnings history,
price >= Rs 10 and >= Rs 0.5 Cr median daily value, including new listings.

Earnings signals used are the two that held up in BOTH study periods
(canslim/winners.py, 2016-21 and 2023-25):
  * margin up: operating margin >= 6 points above the same quarter last year
  * two strong quarters: net profit up >= 50% YoY in each of the last two quarters
Price confirmation (also consistent in both periods): above the 50-day average
and within 15% of the high (52-week, or since listing for new listings).

Research only. Not investment advice.
"""
import json

import numpy as np
import pandas as pd

from canslim import data

FRESH_DAYS = 75          # covers the latest results round; result age did not matter in the study
NEW_DAYS = 14
MIN_PRICE, MIN_VALUE_CR, THIN_CR = 10, 0.5, 5


def _yoy(cur, prev):
    if prev is None or np.isnan(prev):
        return np.nan
    if prev > 0:
        return (cur / prev - 1) * 100
    return 100.0 if cur > 0 else np.nan          # loss -> profit: counted as +100%, labelled turnaround


def _rs_ibd(c: pd.DataFrame) -> pd.Series:
    """IBD-style weighted 12-month return on the last day (NaN with < 1 year of data)."""
    def ret(a, b):
        return c.iloc[-1 - a] / c.iloc[-1 - b] - 1 if len(c) > b else pd.Series(np.nan, index=c.columns)
    return 0.4 * ret(0, 63) + 0.2 * ret(63, 126) + 0.2 * ret(126, 189) + 0.2 * ret(189, 252)


def price_view(P: dict) -> pd.DataFrame:
    c, h, v = P["close"], P["high"], P["volume"]
    last = c.ffill().iloc[-1]
    n = c.notna().sum()
    value = (c * v).iloc[-50:].median(skipna=True) / 1e7
    ma50 = c.iloc[-50:].mean(skipna=True)
    ma150, ma200 = c.iloc[-150:].mean(), c.iloc[-200:].mean()
    ma200_prev = c.iloc[-221:-21].mean()
    full = c.iloc[-221:].notna().sum() >= 200
    trend = full & (last > ma50) & (ma50 > ma150) & (ma150 > ma200) & (ma200 > ma200_prev)
    hi = h.iloc[-252:].max(skipna=True)
    r6 = last / c.iloc[-127] - 1 if len(c) > 127 else np.nan
    rs = _rs_ibd(c)
    out = pd.DataFrame({"close": last, "days": n, "value_cr": value, "above50": last > ma50, "trend": trend,
                        "from_high": (last / hi - 1) * 100, "ret6": r6, "rs_raw": rs})
    ok = (out.close >= MIN_PRICE) & (out.value_cr >= MIN_VALUE_CR)
    out["rs"] = out.rs_raw.where(ok).rank(pct=True) * 99
    return out[ok]


def with_new_listings(P: dict, min_days: int = 10) -> dict:
    """data.panels() drops stocks with < 60 days of data; add them back so fresh NSE listings are seen."""
    have = set(P["close"].columns)
    extra = {k: {} for k in P}
    for f in data.PRICES.glob("NSE_*-EQ.parquet"):
        name = data.name_of(f)
        if name in have or f.stat().st_size == 0:
            continue
        df = pd.read_parquet(f)
        if len(df) < min_days:
            continue
        df = data.adjust(df[~df.index.duplicated()])
        for k in P:
            extra[k][name] = df[k]
    if not extra["close"]:
        return P
    idx = P["close"].index
    return {k: pd.concat([P[k], pd.DataFrame(v).reindex(idx)], axis=1) for k, v in extra.items()}


def scan(d: pd.Timestamp, P: dict, fund: dict, fresh_days: int | None = FRESH_DAYS) -> pd.DataFrame:
    pv = price_view(with_new_listings(P))
    rows = []
    for sym, f in fund.items():
        if sym not in pv.index:
            continue
        q = f["q"][f["q"].known <= d]
        if len(q) < 6:
            continue
        last = q.iloc[-1]
        age = (d - pd.Timestamp(last.known)).days
        if fresh_days is not None and age > fresh_days:
            continue
        np_now, np_prev = _yoy(q.np.iloc[-1], q.np.iloc[-5]), _yoy(q.np.iloc[-2], q.np.iloc[-6])
        sales = (q.sales.iloc[-1] / q.sales.iloc[-5] - 1) * 100 if q.sales.iloc[-5] > 0 else np.nan
        raw = json.loads((data.FUND / f"{sym}.json").read_text()).get("history") or {}
        opm = data._dated(raw.get("OPM"))
        opm_now = opm.get(q.index[-1], np.nan)
        opm_ago = opm.get(q.index[-5], np.nan)
        margin_up = opm_now - opm_ago >= 6
        two_strong = min(np_now, np_prev) >= 50 if not (np.isnan(np_now) or np.isnan(np_prev)) else False
        if not (margin_up or two_strong):
            continue
        p = pv.loc[sym]
        price_ok = bool(p.above50) and p.from_high >= -15
        notes = []
        if q.np.iloc[-5] <= 0 < q.np.iloc[-1]:
            notes.append("turnaround (loss a year ago)")
        if p.value_cr < THIN_CR:
            notes.append(f"thin trading (Rs {p.value_cr:.1f} Cr/day)")
        if p.days < 252:
            notes.append(f"new on NSE ({int(p.days)} days of data)")
        rows.append({"sym": sym, "result_date": pd.Timestamp(last.known), "quarter": q.index[-1],
                     "sales_yoy": sales, "np_yoy": np_now, "np_yoy_prev": np_prev,
                     "opm_now": opm_now, "opm_ago": opm_ago, "margin_up": margin_up, "two_strong": two_strong,
                     "n_signals": int(margin_up) + int(two_strong), "price_ok": price_ok, "trend": bool(p.trend),
                     "ret6": p.ret6, "from_high": p.from_high, "above50": bool(p.above50), "rs": p.rs,
                     "close": p.close, "value_cr": p.value_cr, "industry": f.get("industry"), "notes": "; ".join(notes)})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["price_ok", "n_signals", "rs"], ascending=False).set_index("sym")


# ------------------------------------------------------------------ emerging / turnaround list
# Tested in canslim/emerging.py on 2016-22 (10 names, no new buys in a correction, 0.3% cost/side):
#   21.9%/yr, worst drop -38.6%  vs  CAN SLIM 23.8%/yr, -21.0%;  equal-weight market 13.1%/yr.
# Passed the pre-set bar for a SEPARATE list (narrowly in 2016-19), not for replacing CAN SLIM.
EMERGING_MIN_VALUE_CR = 5


def emerging(d: pd.Timestamp, P: dict, fund: dict, n: int = 10) -> pd.DataFrame:
    """Earnings acceleration + price leadership, with no ROE / 3-year-growth rule (catches turnarounds)."""
    m = scan(d, P, fund, fresh_days=None)
    if m.empty:
        return m
    ok = m[m.trend & (m.rs >= 80) & (m.from_high >= -15) & (m.close >= 20) & (m.value_cr >= EMERGING_MIN_VALUE_CR)]
    ok = ok.sort_values("rs", ascending=False)
    keep, per = [], {}
    for s, r in ok.iterrows():                    # max 3 per industry, as in the backtest
        g = r.industry
        if g and per.get(g, 0) >= 3:
            continue
        per[g] = per.get(g, 0) + 1
        keep.append(s)
        if len(keep) == n:
            break
    return ok.loc[keep]
