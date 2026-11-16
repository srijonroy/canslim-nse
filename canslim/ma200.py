"""200-day touch list: liquid stocks whose price just came to the 200-day moving average (SMA or EMA).

Separate filter requested by the user (2026-11-16). Information only: it is NOT part of the CAN SLIM rules
and has NOT been backtested.

Rules (fixed defaults, change the constants below):
  * universe   = the scan's liquid universe (price >= MIN_PRICE, median traded value >= Rs 3 Cr/day, 200+ days of data)
  * touch      = on one of the last TOUCH_DAYS sessions the day's range reached the line:
                 low <= line x (1 + BAND) and high >= line x (1 - BAND)
  * line       = 200-day simple average of the close (SMA) and/or 200-day exponential average (EMA)
  * approach   = how price got there, judged on the sessions LOOK_FROM..LOOK_TO days before today:
                 "Pullback from above" if the close stayed > 3% above the SMA the whole time,
                 "Rising from below"   if it stayed > 3% below, otherwise "Around the line"
  * 200 rising = SMA today higher than 20 sessions ago
Sorted: pullbacks first, then 200-day rising, then RS.
"""
import json

import numpy as np
import pandas as pd

N, BAND, TOUCH_DAYS = 200, 0.01, 3
LOOK_FROM, LOOK_TO, AWAY = 30, 5, 0.03
LIST_NAME = "ma200"
APPROACH_ORDER = {"Pullback from above": 0, "Around the line": 1, "Rising from below": 2}


def lines(c: pd.DataFrame):
    sma = c.rolling(N, min_periods=N).mean()
    ema = c.ewm(span=N, adjust=False, min_periods=N).mean()
    return sma, ema


def touch_list(P: dict, U: pd.DataFrame, rs_ibd: pd.DataFrame, industry: dict | None = None,
               failed: pd.Series | None = None, d=None) -> pd.DataFrame:
    """One row per stock that touched the 200-day SMA/EMA in the last TOUCH_DAYS sessions up to date d."""
    c, h, lo = P["close"], P["high"], P["low"]
    if d is not None:
        c, h, lo = c.loc[:d], h.loc[:d], lo.loc[:d]
    d = c.index[-1]
    uni = U.loc[d].reindex(c.columns).fillna(False).astype(bool)
    cols = uni.index[uni]
    c, h, lo = c[cols], h[cols], lo[cols]
    sma, ema = lines(c)
    t = slice(-TOUCH_DAYS, None)

    def touched(m):
        hit = (lo.iloc[t] <= m.iloc[t] * (1 + BAND)) & (h.iloc[t] >= m.iloc[t] * (1 - BAND))
        last = hit[::-1].values.argmax(axis=0)            # sessions ago of the most recent touch
        return hit.any(), pd.Series(np.where(hit.any(), last, -1), index=cols)

    ts, ago_s = touched(sma)
    te, ago_e = touched(ema)
    hit = ts | te
    if not hit.any():
        return pd.DataFrame()
    s = hit.index[hit]
    rel = (c / sma).iloc[-LOOK_FROM:-LOOK_TO][s]
    approach = np.where(rel.min() > 1 + AWAY, "Pullback from above",
                        np.where(rel.max() < 1 - AWAY, "Rising from below", "Around the line"))
    rs = rs_ibd.loc[d].where(uni).rank(pct=True) * 99
    hi = h.rolling(252, min_periods=200).max().iloc[-1]
    out = pd.DataFrame({
        "symbol": s,
        "line": ["SMA + EMA" if ts[x] and te[x] else ("SMA" if ts[x] else "EMA") for x in s],
        "days ago": [int(min(v for v in (ago_s[x], ago_e[x]) if v >= 0)) for x in s],
        "approach": approach,
        "close": c.iloc[-1][s].round(2).values,
        "SMA200": sma.iloc[-1][s].round(2).values,
        "EMA200": ema.iloc[-1][s].round(2).values,
        "vs SMA %": ((c.iloc[-1][s] / sma.iloc[-1][s] - 1) * 100).round(1).values,
        "200 rising": (sma.iloc[-1][s] > sma.iloc[-21][s]).values,
        "RS": rs[s].round(0).values,
        "% of 52w high": (c.iloc[-1][s] / hi[s] * 100).round(0).values,
    })
    if industry:
        out["industry"] = out.symbol.map(industry)
    if failed is not None:
        out["CAN SLIM rules failed"] = out.symbol.map(lambda x: len(failed[x]) if x in failed.index else None)
    out["_o"] = out.approach.map(APPROACH_ORDER)
    out = out.sort_values(["_o", "200 rising", "RS"], ascending=[True, False, False]).drop(columns="_o")
    out.insert(0, "rank", range(1, len(out) + 1))
    return out.reset_index(drop=True)


def store(c, d, df: pd.DataFrame):
    """Save to the picks table as list 'ma200'; extra columns go into note as JSON."""
    from canslim import db
    if df is None or not len(df):
        db.store_list(c, d, LIST_NAME, None)
        return
    extra = df.drop(columns=["rank", "symbol", "close"])
    note = [json.dumps({k: (None if pd.isna(v) else (bool(v) if isinstance(v, (bool, np.bool_)) else
                                                     (float(v) if isinstance(v, (int, float, np.number)) else v)))
                        for k, v in r.items()}) for _, r in extra.iterrows()]
    db.store_list(c, d, LIST_NAME, df[["rank", "symbol", "close"]].assign(rs=df["RS"], note=note))
