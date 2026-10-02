"""Point-in-time backtest of the book's screen on NSE.

At each rebalance date we only use what was knowable then:
  * prices up to that date (Fyers, data/prices)
  * quarterly results only after they were published: quarter end + 45 days
    (March quarter + 60 days, SEBI deadlines), annual figures FY end + 60 days
  * RS rating computed cross-sectionally on that date

Screen variants are compared on forward 1/3/6-month returns against the
equal-weight liquid universe and the Nifty 500 index.

Known biases (stated in the output): survivorship (universe is today's listed
stocks), restated financials on Screener, short history (~13 quarters).

usage: python -m canslim.backtest [--start 2024-12-01] [--step M]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim.fundamentals import FUND

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "prices"
OUT = ROOT / "data" / "backtest"

MIN_PRICE = 20
MIN_TURNOVER = 5e7          # Rs 5 Cr average daily value
LAG_Q, LAG_Q4, LAG_FY = 45, 60, 60


# ---------------------------------------------------------------- prices
def load_panels():
    closes, vols, highs = {}, {}, {}
    for f in PRICES.glob("NSE_*-EQ.parquet"):
        df = pd.read_parquet(f)
        if len(df) < 60:
            continue
        name = f.stem[4:-3]          # NSE_ABC-EQ -> ABC  (& stored as 'and')
        closes[name], vols[name], highs[name] = df["close"], df["volume"], df["high"]
    c = pd.DataFrame(closes).sort_index()
    return c, pd.DataFrame(vols).reindex(c.index), pd.DataFrame(highs).reindex(c.index)


def rs_score(c: pd.DataFrame) -> pd.DataFrame:
    """IBD-style: 40% weight on last 3 months, 20% on each earlier quarter of the year."""
    r = lambda n: c / c.shift(n) - 1
    q1, q2, q3, q4 = r(63), c.shift(63) / c.shift(126) - 1, c.shift(126) / c.shift(189) - 1, c.shift(189) / c.shift(252) - 1
    return 0.4 * q1 + 0.2 * q2.fillna(0) + 0.2 * q3.fillna(0) + 0.2 * q4.fillna(0)


# ---------------------------------------------------------- fundamentals
def _period_end(label: str):
    try:
        return pd.Timestamp(label) + pd.offsets.MonthEnd(0)
    except Exception:
        return None


def _series(row: dict) -> pd.Series:
    s = {}
    for k, v in (row or {}).items():
        d = _period_end(k)
        if d is not None and v is not None:
            s[d] = v
    return pd.Series(s, dtype=float).sort_index()


def load_fundamentals() -> dict:
    out = {}
    for f in FUND.glob("*.json"):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text())
        q, a, b = d["quarters"], d["annual"], d["balance"]
        sales_key = "Sales" if "Sales" in q else ("Revenue" if "Revenue" in q else None)
        eq = _series(b.get("Equity Capital")).add(_series(b.get("Reserves")), fill_value=0)
        sh = d.get("shareholding", {})
        inst = _series(sh.get("FIIs")).add(_series(sh.get("DIIs")), fill_value=0)
        out[f.stem] = {
            "q_np": _series(q.get("Net Profit")), "q_eps": _series(q.get("EPS in Rs")),
            "q_sales": _series(q.get(sales_key)) if sales_key else pd.Series(dtype=float),
            "a_np": _series(a.get("Net Profit")), "a_eps": _series(a.get("EPS in Rs")),
            "equity": eq, "inst": inst,
            "industry": (d.get("industry") or [None])[-1],
        }
    return out


def _avail_q(s: pd.Series, t: pd.Timestamp) -> pd.Series:
    lag = pd.to_timedelta([LAG_Q4 if d.month == 3 else LAG_Q for d in s.index], unit="D")
    return s[(s.index + lag) <= t]


def _growth(cur, prev):
    if cur is None or prev is None or pd.isna(cur) or pd.isna(prev) or prev <= 0:
        return np.nan
    return (cur / prev - 1) * 100


def fund_metrics(f: dict, t: pd.Timestamp) -> dict:
    np_q, sales_q = _avail_q(f["q_np"], t), _avail_q(f["q_sales"], t)
    m = {"c_np": np.nan, "c_np_prev": np.nan, "c_sales": np.nan, "a_cagr3": np.nan,
         "a_up": False, "roe": np.nan, "inst_up": np.nan, "np_pos": False}
    if len(np_q):
        last = np_q.index[-1]
        get = lambda s, d: s.get(d, np.nan)
        y1 = last - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
        m["c_np"] = _growth(np_q.iloc[-1], get(np_q, y1))
        m["np_pos"] = np_q.iloc[-1] > 0
        if len(np_q) >= 2:
            p, py = np_q.index[-2], np_q.index[-2] - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
            m["c_np_prev"] = _growth(np_q.iloc[-2], get(np_q, py))
        if len(sales_q) and sales_q.index[-1] == last:
            m["c_sales"] = _growth(sales_q.iloc[-1], get(sales_q, y1))
    a = f["a_np"][(f["a_np"].index + pd.Timedelta(days=LAG_FY)) <= t]
    if len(a) >= 4:
        cur, base = a.iloc[-1], a.iloc[-4]
        if base > 0 and cur > 0:
            m["a_cagr3"] = ((cur / base) ** (1 / 3) - 1) * 100
        m["a_up"] = bool(a.iloc[-1] > a.iloc[-2])
        eq = f["equity"].get(a.index[-1], np.nan)
        if eq and eq > 0:
            m["roe"] = a.iloc[-1] / eq * 100
    inst = f["inst"][(f["inst"].index + pd.Timedelta(days=21)) <= t]
    if len(inst) >= 2:
        m["inst_up"] = inst.iloc[-1] - inst.iloc[-2]
    return m


# --------------------------------------------------------------- screens
SCREENS = {
    "C+A (fundamentals only)": lambda r: r.C and r.A,
    "N+L (price only)": lambda r: r.N and r.L and r.trend,
    "CAN SLIM (C+A+N+L)": lambda r: r.C and r.A and r.N and r.L and r.trend,
    "CAN SLIM + I (inst. rising)": lambda r: r.C and r.A and r.N and r.L and r.trend and r.I,
    "Top 10 composite": lambda r: bool(r.top10),
}
MARKET_GATED = ["CAN SLIM (C+A+N+L)", "Top 10 composite"]   # also run with the M filter


def market_states(c: pd.DataFrame, v: pd.DataFrame) -> pd.Series:
    """Book's market model on Nifty 500 price + synthetic volume (sum of traded value)."""
    from canslim.market import market_state_series
    idx = pd.read_parquet(PRICES / "NSE_NIFTY500-INDEX.parquet")
    idx = idx.assign(volume=(c * v).sum(axis=1).reindex(idx.index))
    idx = idx[idx.volume > 0]
    return market_state_series(idx)["state"]


def snapshot(t, c, v, h, rs, funds) -> pd.DataFrame:
    i = c.index.get_loc(t)
    win = c.iloc[max(0, i - 251): i + 1]
    close = c.iloc[i]
    ma50, ma200 = win.iloc[-50:].mean(), win.mean() if len(win) >= 200 else np.nan
    ma200_prev = c.iloc[max(0, i - 271): i - 20 + 1].mean()
    hi = h.iloc[max(0, i - 251): i + 1].max()
    turnover = (c.iloc[max(0, i - 49): i + 1] * v.iloc[max(0, i - 49): i + 1]).mean()
    liquid = (close >= MIN_PRICE) & (turnover >= MIN_TURNOVER) & win.notna().sum().ge(200)
    rs_pct = rs.iloc[i][liquid].rank(pct=True) * 99
    df = pd.DataFrame({"close": close, "rs": rs_pct, "off_high": (close / hi - 1) * 100,
                       "trend": (close > ma50) & (ma50 > ma200) & (ma200 > ma200_prev)})
    df = df.loc[liquid[liquid].index]
    rows = []
    for s in df.index:
        f = funds.get(s)
        rows.append(fund_metrics(f, t) if f else {})
    df = df.join(pd.DataFrame(rows, index=df.index))
    df["industry"] = [funds[s]["industry"] if s in funds else None for s in df.index]
    df["C"] = (df.c_np >= 25) & df.np_pos & (df.c_np_prev >= 20) & (df.c_sales >= 20)
    df["A"] = (df.a_cagr3 >= 20) & df.a_up & (df.roe >= 17)
    df["N"] = df.off_high >= -15
    df["L"] = df.rs >= 80
    df["I"] = df.inst_up > 0
    # composite for the daily top-10: RS, quarterly + annual earnings growth, ROE, nearness to high
    elig = df.N & df.trend & df.np_pos & (df.c_np > 0) & (df.a_cagr3 > 0)
    score = (df.rs.rank(pct=True) * 2 + df.c_np.rank(pct=True) * 2 + df.a_cagr3.rank(pct=True)
             + df.roe.rank(pct=True) + df.c_sales.rank(pct=True) + df.off_high.rank(pct=True))
    df["composite"] = score.where(elig)
    df["top10"] = df.composite.rank(ascending=False) <= 10
    return df


def run(start: str, step: str, horizons=(21, 63, 126)):
    c, v, h = load_panels()
    funds = load_fundamentals()
    rs = rs_score(c)
    idx = pd.read_parquet(PRICES / "NSE_NIFTY500-INDEX.parquet")["close"].reindex(c.index).ffill()
    dates = pd.Series(c.index, index=c.index)[start:].resample(step).first().dropna()
    mstate = market_states(c, v).reindex(c.index).ffill()
    recs, picks = [], []
    for t in dates:
        i = c.index.get_loc(t)
        snap = snapshot(t, c, v, h, rs, funds)
        fwd = {n: (c.iloc[i + n] / c.iloc[i] - 1) * 100 if i + n < len(c) else None for n in horizons}
        bench = {n: (idx.iloc[i + n] / idx.iloc[i] - 1) * 100 if i + n < len(c) else np.nan for n in horizons}
        universe = snap.index
        base = {"date": t.date(), "screen": "Universe (liquid, EW)", "n": len(universe)}
        for n in horizons:
            base[f"r{n}"] = fwd[n][universe].mean() if fwd[n] is not None else np.nan
            base[f"nifty500_{n}"] = bench[n]
        recs.append(base)
        for name, fn in SCREENS.items():
            sel = [s for s, r in snap.iterrows() if fn(r)]
            rec = {"date": t.date(), "screen": name, "n": len(sel)}
            for n in horizons:
                if fwd[n] is not None and sel:
                    r = fwd[n][sel].dropna()
                    rec[f"r{n}"] = r.mean()
                    rec[f"hit{n}"] = (r > bench[n]).mean() * 100
                    rec[f"med{n}"] = r.median()
                else:
                    rec[f"r{n}"] = np.nan
                rec[f"nifty500_{n}"] = bench[n]
            recs.append(rec)
            if name in MARKET_GATED:
                ok = mstate.get(t) in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE")
                g = dict(rec, screen=name + " + M (cash in correction)", n=rec["n"] if ok else 0)
                if not ok:
                    for n in horizons:
                        g[f"r{n}"] = 0.0 if fwd[n] is not None else np.nan
                        g.pop(f"hit{n}", None)
                recs.append(g)
            if name in ("CAN SLIM (C+A+N+L)", "Top 10 composite"):
                for s in sel:
                    picks.append({"date": t.date(), "screen": name, "market": mstate.get(t), "symbol": s, **snap.loc[s, ["rs", "off_high", "c_np", "c_sales",
                                  "a_cagr3", "roe", "industry"]].to_dict(),
                                  **{f"fwd{n}": (fwd[n][s] if fwd[n] is not None else np.nan) for n in horizons}})
        print(t.date(), mstate.get(t), {r["screen"][:14]: r["n"] for r in recs if r["date"] == t.date()}, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    res = pd.DataFrame(recs)
    res.to_csv(OUT / "periods.csv", index=False)
    pd.DataFrame(picks).to_csv(OUT / "canslim_picks.csv", index=False)
    return res


def summarize(res: pd.DataFrame, horizons=(21, 63, 126)) -> pd.DataFrame:
    rows = []
    for name, g in res.groupby("screen", sort=False):
        row = {"screen": name, "avg picks": round(g.n.mean(), 1)}
        for n in horizons:
            ok = g[f"r{n}"].notna()
            row[f"{n}d avg %"] = round(g.loc[ok, f"r{n}"].mean(), 2)
            row[f"{n}d vs N500"] = round((g.loc[ok, f"r{n}"] - g.loc[ok, f"nifty500_{n}"]).mean(), 2)
            if f"hit{n}" in g:
                row[f"{n}d beat%"] = round(g.loc[ok, f"hit{n}"].mean(), 1)
            row[f"{n}d periods"] = int(ok.sum())
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-12-01")
    ap.add_argument("--step", default="MS")
    a = ap.parse_args()
    res = run(a.start, a.step)
    pd.set_option("display.width", 250)
    s = summarize(res)
    s.to_csv(OUT / "summary.csv", index=False)
    print(s.to_string(index=False))
