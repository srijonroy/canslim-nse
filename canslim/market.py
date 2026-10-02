"""Market-direction model (book Chapter 9): distribution days, rally attempts,
follow-through days -> market state.

States: CONFIRMED_UPTREND, UPTREND_UNDER_PRESSURE, RALLY_ATTEMPT, CORRECTION.
Rules from the book:
  * Distribution day: index falls >= 0.2% on volume higher than the prior day.
    Counted over a rolling 25 sessions (~5 weeks); they expire, and drop off if
    the index later rallies 5%+ above the distribution day's close.
  * 4-5 distribution days in 4-5 weeks => market topping.
  * Rally attempt starts on the first up close after a decline (day 1).
    Follow-through: on day 4-7 an index gains >= 1.5% on volume above the prior
    day. (Book moved from 1% to 1.5-2% as institutions learned the rule.)
"""
from dataclasses import dataclass

import pandas as pd

DIST_MIN_DROP = -0.2      # percent
DIST_WINDOW = 25          # sessions
DIST_EXPIRE_GAIN = 5.0    # percent rally above the distribution close removes it
FTD_MIN_GAIN = 1.2        # percent; Nifty 500 is less volatile than the Nasdaq the book used
UPTREND_MAX_DD = 8.0      # percent off the high made since the follow-through
FTD_DAYS = (4, 20)        # book: usually day 4-7; later ones still count
POWER_NEAR_HIGH = 0.95    # IBD power-trend style: index this close to its 52-wk high
TOP_DIST_COUNT = 5
PRESSURE_DIST_COUNT = 4


def distribution_days(df: pd.DataFrame) -> pd.Series:
    """Boolean series: True on distribution days (before expiry logic)."""
    chg = df["close"].pct_change() * 100
    return (chg <= DIST_MIN_DROP) & (df["volume"] > df["volume"].shift(1))


def active_distribution(df: pd.DataFrame) -> pd.Series:
    """Count of unexpired distribution days in the trailing window, per date."""
    dist = distribution_days(df)
    close = df["close"].values
    idx = list(range(len(df)))
    out = []
    for i in idx:
        lo = max(0, i - DIST_WINDOW + 1)
        n = 0
        for j in range(lo, i + 1):
            if dist.iloc[j] and close[i] < close[j] * (1 + DIST_EXPIRE_GAIN / 100):
                n += 1
        out.append(n)
    return pd.Series(out, index=df.index, name="dist_count")


def market_state_series(df: pd.DataFrame) -> pd.DataFrame:
    """Walk forward through the index history and label each session's state."""
    df = df.copy()
    dist_cnt = active_distribution(df)
    chg = df["close"].pct_change() * 100
    ma50 = df["close"].rolling(50).mean()
    ma200 = df["close"].rolling(200).mean()
    hi252 = df["close"].rolling(252, min_periods=200).max()
    low50 = df["close"].rolling(50, min_periods=20).min()
    # strong, orderly uptrend with no correction to rally from: the FTD rule never fires here
    power = (df["close"] > ma50) & (ma50 > ma200) & (ma50 > ma50.shift(10))         & (df["close"] >= hi252 * POWER_NEAR_HIGH)

    state, rally_day, low_close = "CORRECTION", 0, None
    rally_low, peak_up = None, None     # correction low before the FTD; high since the FTD
    dist = distribution_days(df).values
    closes = df["close"].values
    ftd_i = -1                          # distribution count resets at a follow-through day
    states, rally_days, counts = [], [], []
    for i in range(len(df)):
        c, ch = df["close"].iloc[i], chg.iloc[i]
        lo = max(0, i - DIST_WINDOW + 1, ftd_i + 1)
        cnt = sum(1 for j in range(lo, i + 1)
                  if dist[j] and closes[i] < closes[j] * (1 + DIST_EXPIRE_GAIN / 100))

        if state in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE"):
            peak_up = max(peak_up, c)
            broke = (c < rally_low                                     # undercut the rally low
                     or cnt >= TOP_DIST_COUNT + 1                      # distribution pile-up
                     or (not pd.isna(ma50.iloc[i]) and c < ma50.iloc[i] and cnt >= PRESSURE_DIST_COUNT)
                     or (c / peak_up - 1) * 100 <= -UPTREND_MAX_DD)
            if broke:
                state, rally_day, low_close = "CORRECTION", 0, c
            else:
                state = "UPTREND_UNDER_PRESSURE" if cnt >= PRESSURE_DIST_COUNT else "CONFIRMED_UPTREND"
        elif power.iloc[i]:
            state, rally_day, rally_low, peak_up, ftd_i = "CONFIRMED_UPTREND", 0, low50.iloc[i], c, i
        else:  # CORRECTION or RALLY_ATTEMPT
            if state == "CORRECTION":
                low_close = c if low_close is None else min(low_close, c)
                if ch > 0 and i > 0 and df["close"].iloc[i - 1] <= low_close * 1.03:
                    state, rally_day = "RALLY_ATTEMPT", 1
            else:  # RALLY_ATTEMPT
                if c < low_close:                      # undercut the low -> rally failed
                    state, rally_day, low_close = "CORRECTION", 0, c
                else:
                    rally_day += 1
                    ftd = (FTD_DAYS[0] <= rally_day <= FTD_DAYS[1] and ch >= FTD_MIN_GAIN
                           and df["volume"].iloc[i] > df["volume"].iloc[i - 1])
                    if ftd:
                        state, rally_day, rally_low, peak_up = "CONFIRMED_UPTREND", 0, low_close, c
                        ftd_i = i
        states.append(state)
        counts.append(cnt)
        rally_days.append(rally_day)

    out = pd.DataFrame({"close": df["close"], "chg_pct": chg.round(2),
                        "dist_count": dist_cnt, "dist_since_ftd": counts, "state": states, "rally_day": rally_days,
                        "above_50dma": df["close"] > ma50, "above_200dma": df["close"] > ma200})
    return out


@dataclass
class MarketStatus:
    state: str
    dist_count: int
    rally_day: int
    detail: str
    buy_ok: bool


def market_status(index_df: pd.DataFrame) -> MarketStatus:
    """Latest market state, using the strictest read across the supplied index."""
    s = market_state_series(index_df).iloc[-1]
    ok = s["state"] in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE")
    detail = {
        "CONFIRMED_UPTREND": "Confirmed uptrend -- breakouts from sound bases are in play.",
        "UPTREND_UNDER_PRESSURE": f"Uptrend under pressure: {s['dist_count']} distribution days. Be selective; book says raise cash if it hits 5-6.",
        "RALLY_ATTEMPT": f"Rally attempt, day {s['rally_day']}. Not confirmed -- wait for a follow-through day (day 4-7).",
        "CORRECTION": "Market in correction. Book: do NOT buy breakouts; most will fail.",
    }[s["state"]]
    return MarketStatus(s["state"], int(s["dist_count"]), int(s["rally_day"]), detail, ok)


if __name__ == "__main__":
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "data" / "prices"
    for name in ["NSE_NIFTY50-INDEX", "NSE_NIFTY500-INDEX"]:
        df = pd.read_parquet(root / f"{name}.parquet")
        ser = market_state_series(df)
        st = market_status(df)
        print(f"\n== {name}: {st.state} | dist days {st.dist_count} | {st.detail}")
        chg = ser["state"] != ser["state"].shift()
        print(ser.loc[chg, ["close", "state", "dist_count"]].tail(10).to_string())
