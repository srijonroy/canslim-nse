"""Price with 20- and 200-day exponential averages, for the app's chart panel and the daily report's chart drawer.

Prices are the Fyers daily closes in data/prices (from 2014), adjusted for splits / bonuses the same way as the
research panels (data.adjust). Both averages are computed on the full history, so the 200-day line is settled
even at the start of a 5-year window.
"""
import re

import pandas as pd

from canslim.data import PRICES, adjust

# Capitalised words in our own text that are not tickers here, even when a listed company has that symbol.
NOT_TICKERS = {"BSE", "NSE", "ROE", "ROCE", "EPS", "PEG", "CAGR", "GARP", "QGLP", "FPI", "FII", "DII", "IPO",
               "ETF", "PAT", "EBIT", "EBITDA", "YOY", "QOQ", "USD", "INR", "PDF", "PPT", "AGM", "SEBI", "RBI",
               "CEO", "CFO", "MD", "NPA", "RPT", "OFS", "QIP", "FY", "TTM", "SEPA", "IBD", "ATH", "EMA", "SMA",
               "NIFTY", "SLIM", "CAN", "OK", "NEW", "RED", "AMBER", "GREEN", "GREY", "HOLD", "SELL", "BUY", "NOTE"}


def _file(sym: str):
    return PRICES / f"NSE_{sym.replace('&', 'and')}-EQ.parquet"


def series(sym: str) -> pd.DataFrame:
    """Daily close, ema20, ema200 for the whole stored history; empty if there is no price file."""
    f = _file(sym)
    if not f.exists():
        return pd.DataFrame(columns=["close", "ema20", "ema200"])
    df = pd.read_parquet(f)
    df.index = pd.to_datetime(df.index)
    df = adjust(df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]])
    c = df["close"].dropna()
    return pd.DataFrame({"close": c, "ema20": c.ewm(span=20, adjust=False).mean(),
                         "ema200": c.ewm(span=200, adjust=False).mean()})


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
