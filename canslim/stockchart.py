"""Price with 20- and 200-day exponential averages, for the app's chart panel and the daily report's chart drawer.

Prices are the Fyers daily closes in data/prices (from 2014), adjusted for splits / bonuses the same way as the
research panels (data.adjust). Both averages are computed on the full history, so the 200-day line is settled
even at the start of a 5-year window.
"""
import json
import re
from functools import lru_cache

import numpy as np
import pandas as pd

from canslim import data, patterns
from canslim.data import FUND, PRICES, ROOT, _dated, adjust


@lru_cache(maxsize=4)
def index_close(name: str) -> pd.Series:
    s = data.index_close(name)
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated()].sort_index()

# Capitalised words in our own text that are not tickers here, even when a listed company has that symbol.
NOT_TICKERS = {"BSE", "NSE", "ROE", "ROCE", "EPS", "PEG", "CAGR", "GARP", "QGLP", "FPI", "FII", "DII", "IPO",
               "ETF", "PAT", "EBIT", "EBITDA", "YOY", "QOQ", "USD", "INR", "PDF", "PPT", "AGM", "SEBI", "RBI",
               "CEO", "CFO", "MD", "NPA", "RPT", "OFS", "QIP", "FY", "TTM", "SEPA", "IBD", "ATH", "EMA", "SMA",
               "NIFTY", "SLIM", "CAN", "OK", "NEW", "RED", "AMBER", "GREEN", "GREY", "HOLD", "SELL", "BUY", "NOTE"}


def _file(sym: str):
    return PRICES / f"NSE_{sym.replace('&', 'and')}-EQ.parquet"


def ohlcv(sym: str) -> pd.DataFrame:
    """Split/bonus-adjusted daily OHLCV for the whole stored history; empty if there is no price file."""
    f = _file(sym)
    if not f.exists():
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.read_parquet(f)
    df.index = pd.to_datetime(df.index)
    return adjust(df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]).dropna(
        subset=["close"])


def series(sym: str) -> pd.DataFrame:
    """Daily close, ema20, ema200 for the whole stored history; empty if there is no price file."""
    c = ohlcv(sym)["close"]
    return pd.DataFrame({"close": c, "ema20": c.ewm(span=20, adjust=False).mean(),
                         "ema200": c.ewm(span=200, adjust=False).mean()})


# ------------------------------------------------------------------ chart layers (app panel)
BACKTEST_TRADES = ROOT / "data" / "tune" / "sizetest" / "trades.csv"   # every trade of the current rules, 2016-26


def _on_bar(idx: pd.DatetimeIndex, when) -> str | None:
    """Date string of the first trading day on/after `when` (markers must sit on a bar)."""
    i = idx.searchsorted(pd.Timestamp(when))
    return f"{idx[i]:%Y-%m-%d}" if i < len(idx) else None


def results(sym: str) -> pd.DataFrame:
    """Quarterly results: quarter end, day the numbers became known, net profit growth vs a year ago (%).
    Same method as data.fundamentals (profit = sales x NPM; known = first TTM-EPS stamp after the quarter)."""
    f = FUND / f"{sym.replace('&', 'and')}.json"
    if not f.exists():
        return pd.DataFrame(columns=["known", "np_yoy"])
    h = (json.loads(f.read_text()).get("history") or {})
    sales, npm, eps = _dated(h.get("Quarter Sales")), _dated(h.get("NPM")), _dated(h.get("EPS"))
    q = pd.DataFrame({"sales": sales, "npm": npm}).dropna()
    if q.empty:
        return pd.DataFrame(columns=["known", "np_yoy"])
    q["np"] = q.sales * q.npm / 100
    known = []
    for qe in q.index:
        later = eps.index[(eps.index > qe) & (eps.index <= qe + pd.Timedelta(days=120))]
        known.append(later[0] if len(later) else qe + pd.Timedelta(days=60 if qe.month == 3 else 45))
    q["known"] = known
    prev = q.np.reindex(q.index - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)).values
    with np.errstate(divide="ignore", invalid="ignore"):
        q["np_yoy"] = np.where(prev > 0, (q.np.values / prev - 1) * 100, np.nan)
    q["turned"] = (prev <= 0) & (q.np.values > 0)
    return q


def layers(sym: str, picks: pd.DataFrame | None = None, paper: pd.DataFrame | None = None,
           holdings: pd.DataFrame | None = None) -> dict:
    """Everything the app's chart draws for one stock (full history; the page picks the visible window).

    picks: CAN SLIM list rows (date, symbol) for all scan dates; paper: paper_trades rows; holdings: holdings rows.
    Returns t/c/e20/e200 (price), v/v50/heavy (volume), rs (price / Nifty 500, rebased), markers (signals,
    results, RS-leads), lines (pivot, buy zone, your buy prices) and base (text)."""
    df = ohlcv(sym)
    if df.empty:
        return {}
    c, v, idx = df.close, df.volume, df.index
    v50 = v.rolling(50, min_periods=30).mean()
    nifty = index_close("NIFTY500").reindex(idx).ffill()
    rs = (c / nifty)
    rs = rs / rs.dropna().iloc[0] * 100
    out = {"t": [f"{d:%Y-%m-%d}" for d in idx], "c": c.round(2).tolist(),
           "e20": c.ewm(span=20, adjust=False).mean().round(2).tolist(),
           "e200": c.ewm(span=200, adjust=False).mean().round(2).tolist(),
           "v": v.fillna(0).astype(int).tolist(), "v50": v50.round(0).fillna(0).astype(int).tolist(),
           "up": (c >= c.shift()).astype(int).tolist(),
           "heavy": (v >= 1.4 * v50.shift()).astype(int).tolist(),        # book: breakout volume >= 40% above average
           "rs": rs.round(2).where(rs.notna(), None).tolist()}
    sig, res, rsm, lines = [], [], [], []

    def mark(lst, when, buy, text):
        t = _on_bar(idx, when)
        if t:
            lst.append({"time": t, "position": "belowBar" if buy else "aboveBar",
                        "shape": "arrowUp" if buy else "arrowDown", "buy": bool(buy), "text": text})

    if BACKTEST_TRADES.exists():                                   # backtest of the current rules
        bt = pd.read_csv(BACKTEST_TRADES)
        for r in bt[bt.sym == sym].drop_duplicates(["entry_date", "exit_date"]).itertuples():
            mark(sig, r.entry_date, True, "BT")
            if pd.notna(r.exit_date):
                mark(sig, r.exit_date, False, f"BT {r.ret:+.0%}")
    if picks is not None and len(picks):                          # live CAN SLIM list, joined / left
        days = sorted(picks.date.unique())
        on = set(picks[picks.symbol == sym].date)
        for prev, d in zip([None] + days[:-1], days):
            if d in on and prev not in on:
                mark(sig, d, True, "List")
            elif d not in on and prev in on:
                mark(sig, d, False, "Off list")
    if paper is not None and len(paper):
        for r in paper[paper.symbol == sym].itertuples():
            mark(sig, r.entry_date, True, "Paper")
            if r.status == "closed" and pd.notna(r.exit_date):
                mark(sig, r.exit_date, False, f"Paper {r.ret:+.0%}")
    if holdings is not None and len(holdings):
        for r in holdings[holdings.symbol == sym].itertuples():
            mark(sig, r.buy_date, True, "You")
            if pd.notna(r.sell_date):
                mark(sig, r.sell_date, False, f"You {r.sell_price / r.buy_price - 1:+.0%}")
            else:
                lines.append({"price": float(r.buy_price), "title": f"Your buy {r.buy_price:,.2f}", "kind": "you"})

    for r in results(sym).itertuples():                            # result days
        if r.known < idx[0]:
            continue
        txt = "E turned profit" if r.turned else (f"E {r.np_yoy:+.0f}%" if pd.notna(r.np_yoy) else "E")
        t = _on_bar(idx, r.known)
        if t:
            res.append({"time": t, "position": "aboveBar", "shape": "circle", "text": txt,
                        "good": bool(r.turned or (pd.notna(r.np_yoy) and r.np_yoy >= 25))})

    # RS line at a new 52-week high while the price is still 5%+ below its own (O'Neil: RS leads price)
    lead = (rs >= rs.rolling(252, min_periods=200).max()) & (c < 0.95 * c.rolling(252, min_periods=200).max())
    last = -99
    for i in np.flatnonzero(lead.fillna(False).values):
        if i - last > 20:
            rsm.append({"time": f"{idx[i]:%Y-%m-%d}", "position": "belowBar", "shape": "circle", "text": "RS leads"})
        last = i

    try:                                                           # current base and pivot
        b = patterns.detect(df, index_close("NIFTY500"))
    except Exception:
        b = None
    base = b.summary() if b is not None else ""
    if b is not None and b.kind != "none" and pd.notna(b.pivot):
        lines += [{"price": float(b.pivot), "title": f"Pivot {b.pivot:,.2f}", "kind": "pivot"},
                  {"price": float(b.pivot * (1 + patterns.BUY_ZONE)), "title": "Buy zone top (+5%)", "kind": "zone"}]
    out.update(signals=sorted(sig, key=lambda m: m["time"]), results=res, rsmarks=rsm, lines=lines, base=base)
    return out


def universe() -> set:
    """Every symbol with a price file."""
    return {f.stem[4:-3].replace("and", "&") for f in PRICES.glob("NSE_*-EQ.parquet")}   # symbols are upper case


def mentioned(text: str, known: set) -> list:
    """Tickers that appear in a piece of text, in order of first mention."""
    out = []
    for w in re.findall(r"(?<![A-Za-z0-9&])[A-Z][A-Z0-9&-]{2,19}(?![A-Za-z0-9&])", text or ""):
        if w in known and w not in NOT_TICKERS and w not in out:
            out.append(w)
    return out
