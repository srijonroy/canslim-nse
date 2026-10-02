"""
NSE Momentum + Volume Scanner
=============================
Scans NSE-listed stocks and flags the ones that are currently:
  1. Above BOTH the 20-day EMA and 200-day EMA (short + long term uptrend)
  2. Showing recent strength (positive return over the last N trading days)
  3. Trading on above-average ("good") volume vs. their own recent history

Data source : Yahoo Finance, via the `yfinance` library (NSE tickers use a
              ".NS" suffix, e.g. RELIANCE.NS, TCS.NS)
Universe    : Pulled live from NSE's own index/equity archives, or you can
              point it at your own CSV of symbols with --symbols-file.

INSTALL
-------
    pip install yfinance pandas numpy requests

USAGE
-----
    # Nifty 500 stocks, up on 5-day return, volume 1.5x its recent average
    python nse_scanner.py --universe nifty500 --lookback 5 --min-return 3 --vol-mult 1.5

    # Full NSE equity list (~2000 symbols, slower)
    python nse_scanner.py --universe all --lookback 5 --min-return 2 --vol-mult 1.3

    # Your own list of symbols (no .NS suffix, one per line, or a column named "Symbol")
    python nse_scanner.py --symbols-file my_symbols.csv --lookback 5

Output: prints the top matches and writes a full results CSV
        (nse_scan_results_<timestamp>.csv) with every stock that was checked,
        sorted by strength.

NOTE: This is a research/screening tool, not investment advice. EMA position,
short-term return, and relative volume are backward-looking descriptive
filters -- they tell you what already happened, not what happens next.
"""

import argparse
import io
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf

NSE_HEADERS = {
    # NSE's archive server blocks requests without a browser-like User-Agent
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,*/*",
}

NSE_INDEX_URLS = {
    "nifty50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "nifty100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    "nifty500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
}
NSE_ALL_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"


# --------------------------------------------------------------------------
# 1. Build the universe of symbols to scan
# --------------------------------------------------------------------------
def get_nse_universe(universe: str) -> list:
    """Fetch a list of NSE trading symbols (WITHOUT the .NS suffix)."""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    if universe == "all":
        url = NSE_ALL_EQUITY_URL
        symbol_col = "SYMBOL"
    elif universe in NSE_INDEX_URLS:
        url = NSE_INDEX_URLS[universe]
        symbol_col = "Symbol"
    else:
        raise ValueError(f"Unknown universe '{universe}'")

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    if symbol_col not in df.columns:
        # NSE occasionally tweaks header casing -- fall back to a fuzzy match
        candidates = [c for c in df.columns if "symbol" in c.lower()]
        if not candidates:
            raise RuntimeError(f"Could not find a symbol column in {url}")
        symbol_col = candidates[0]

    symbols = df[symbol_col].dropna().astype(str).str.strip().unique().tolist()
    return symbols


def load_symbols_from_file(path: str) -> list:
    """Load symbols from a user-supplied file: one per line, or a CSV with a
    'Symbol' / 'SYMBOL' column."""
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        col = next((c for c in df.columns if c.lower() == "symbol"), df.columns[0])
        return df[col].dropna().astype(str).str.strip().tolist()
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


# --------------------------------------------------------------------------
# 2. Download OHLCV data in batches
# --------------------------------------------------------------------------
def download_batches(symbols: list, batch_size: int = 150, period: str = "1y") -> dict:
    """Download daily OHLCV for many symbols via yfinance, batched to avoid
    throttling. Returns {symbol: DataFrame}."""
    tickers = [f"{s}.NS" for s in symbols]
    data = {}

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        print(f"  Downloading {i + 1}-{i + len(batch)} of {len(tickers)}...", file=sys.stderr)
        try:
            raw = yf.download(
                tickers=batch,
                period=period,
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            print(f"  Batch download failed ({e}), skipping batch.", file=sys.stderr)
            continue

        for t in batch:
            symbol = t[:-3]  # strip ".NS"
            try:
                if len(batch) == 1:
                    df = raw
                else:
                    df = raw[t]
                df = df.dropna(how="all")
                if not df.empty:
                    data[symbol] = df
            except (KeyError, Exception):
                continue

        time.sleep(1)  # be polite between batches

    return data


# --------------------------------------------------------------------------
# 3. Scoring logic
# --------------------------------------------------------------------------
def score_stock(
    df: pd.DataFrame,
    ema_short: int = 20,
    ema_long: int = 200,
    lookback: int = 5,
    min_return_pct: float = 2.0,
    vol_mult: float = 1.5,
    vol_baseline_days: int = 20,
) -> dict:
    """Evaluate one stock's DataFrame against the three criteria.
    Returns a dict of metrics, or None if there isn't enough history."""
    needed = ema_long + lookback + 5
    if len(df) < needed:
        return None

    close = df["Close"]
    volume = df["Volume"]

    ema_s = close.ewm(span=ema_short, adjust=False).mean()
    ema_l = close.ewm(span=ema_long, adjust=False).mean()

    last_close = close.iloc[-1]
    last_ema_s = ema_s.iloc[-1]
    last_ema_l = ema_l.iloc[-1]

    above_short_ema = last_close > last_ema_s
    above_long_ema = last_close > last_ema_l
    ema_stack_bullish = last_ema_s > last_ema_l  # 20 EMA above 200 EMA

    # Recent strength: % return over the lookback window
    ret_pct = (last_close / close.iloc[-1 - lookback] - 1) * 100

    # Relative volume: recent average volume vs. the volume baseline
    # that precedes it (so a spike doesn't inflate its own baseline)
    recent_vol_avg = volume.iloc[-lookback:].mean()
    baseline_vol_avg = volume.iloc[-lookback - vol_baseline_days : -lookback].mean()
    rel_volume = recent_vol_avg / baseline_vol_avg if baseline_vol_avg > 0 else np.nan

    passes = (
        above_short_ema
        and above_long_ema
        and ret_pct >= min_return_pct
        and rel_volume >= vol_mult
    )

    return {
        "close": round(last_close, 2),
        "ema20": round(last_ema_s, 2),
        "ema200": round(last_ema_l, 2),
        "above_ema20": above_short_ema,
        "above_ema200": above_long_ema,
        "ema_stack_bullish": ema_stack_bullish,
        f"return_{lookback}d_pct": round(ret_pct, 2),
        "rel_volume": round(rel_volume, 2) if not np.isnan(rel_volume) else None,
        "passes_all_filters": passes,
    }


# --------------------------------------------------------------------------
# 4. Main
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="NSE EMA + momentum + volume scanner")
    parser.add_argument(
        "--universe",
        choices=["nifty50", "nifty100", "nifty200", "nifty500", "all"],
        default="nifty500",
        help="Which NSE list to scan (default: nifty500)",
    )
    parser.add_argument("--symbols-file", help="Path to a custom symbol list, overrides --universe")
    parser.add_argument("--ema-short", type=int, default=20)
    parser.add_argument("--ema-long", type=int, default=200)
    parser.add_argument("--lookback", type=int, default=5, help="Days used to measure recent strength")
    parser.add_argument("--min-return", type=float, default=2.0, help="Min %% return over lookback window")
    parser.add_argument("--vol-mult", type=float, default=1.5, help="Min relative volume vs recent baseline")
    parser.add_argument("--top-n", type=int, default=30, help="How many results to print")
    args = parser.parse_args()

    if args.symbols_file:
        symbols = load_symbols_from_file(args.symbols_file)
    else:
        print(f"Fetching {args.universe} symbol list from NSE...", file=sys.stderr)
        symbols = get_nse_universe(args.universe)
    print(f"Universe size: {len(symbols)} symbols", file=sys.stderr)

    price_data = download_batches(symbols)
    print(f"Downloaded data for {len(price_data)} / {len(symbols)} symbols", file=sys.stderr)

    rows = []
    for symbol, df in price_data.items():
        result = score_stock(
            df,
            ema_short=args.ema_short,
            ema_long=args.ema_long,
            lookback=args.lookback,
            min_return_pct=args.min_return,
            vol_mult=args.vol_mult,
        )
        if result is not None:
            result["symbol"] = symbol
            rows.append(result)

    if not rows:
        print("No results -- check your internet access to Yahoo Finance / NSE, or loosen the filters.")
        return

    results = pd.DataFrame(rows).set_index("symbol")
    ret_col = f"return_{args.lookback}d_pct"
    results = results.sort_values(ret_col, ascending=False)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"nse_scan_results_{ts}.csv"
    results.to_csv(out_path)
    print(f"\nFull results ({len(results)} stocks) saved to {out_path}\n")

    hits = results[results["passes_all_filters"]].sort_values(ret_col, ascending=False)
    print(f"=== {len(hits)} stocks passed ALL filters "
          f"(above {args.ema_short}/{args.ema_long} EMA, "
          f"{args.lookback}d return >= {args.min_return}%, "
          f"rel. volume >= {args.vol_mult}x) ===\n")
    if hits.empty:
        print("None passed every filter -- try loosening --min-return or --vol-mult.")
    else:
        cols_to_show = ["close", "ema20", "ema200", ret_col, "rel_volume"]
        print(hits[cols_to_show].head(args.top_n).to_string())


if __name__ == "__main__":
    main()