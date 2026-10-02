"""
NSE Momentum + Volume Scanner v2
=================================
An upgrade on the plain "above 20/200 EMA + volume" scanner. Adds the filters
that separate genuine strength from noise / manipulated moves:

  1. Above BOTH 20 EMA and 200 EMA, with 20 EMA > 200 EMA (trend alignment)
  2. Recent strength: positive return over the last N days
  3. Relative strength vs. Nifty 50 (outperforming the index, not drifting with it)
  4. Elevated volume vs. its own recent average (relative volume)
  5. Minimum daily turnover in Rs crore -> excludes illiquid stocks that are
     cheap to move with small size (the exact "easy to fake" problem we
     discussed -- thin liquidity is where operator/pump activity concentrates)
  6. Minimum price floor -> avoids penny-stock circuit-pump territory
  7. Single-day-dominance check -> excludes stocks where most of the "return"
     came from one gap/circuit day rather than sustained buying
  8. Proximity to 52-week high -> less overhead supply, cleaner breakouts
  9. Optional market-regime gate (--require-market-uptrend) -> refuses to
     surface anything if the Nifty 50 itself is below its 200 EMA

Stocks that pass every gate are ranked by a composite percentile score
across return, relative volume, relative strength, and proximity to the
52-week high -- so you get an ordered watchlist, not a wall of names.

INSTALL
-------
    pip install yfinance pandas numpy requests

USAGE
-----
    python nse_scanner_v2.py --universe nifty500 --lookback 5 --min-return 3 \\
        --vol-mult 1.5 --min-turnover-cr 5 --min-price 20

    # Stricter: liquid, near highs, market itself must be healthy
    python nse_scanner_v2.py --universe nifty200 --min-turnover-cr 15 \\
        --max-pct-from-52w-high 10 --require-market-uptrend

NOTE: Research/screening tool, not investment advice. Every filter here is
backward-looking -- it describes what already happened, not what happens next.
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
BENCHMARK_TICKER = "^NSEI"  # Nifty 50 index


# --------------------------------------------------------------------------
# 1. Universe
# --------------------------------------------------------------------------
def get_nse_universe(universe: str) -> list:
    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    if universe == "all":
        url, symbol_col = NSE_ALL_EQUITY_URL, "SYMBOL"
    elif universe in NSE_INDEX_URLS:
        url, symbol_col = NSE_INDEX_URLS[universe], "Symbol"
    else:
        raise ValueError(f"Unknown universe '{universe}'")

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    if symbol_col not in df.columns:
        candidates = [c for c in df.columns if "symbol" in c.lower()]
        if not candidates:
            raise RuntimeError(f"Could not find a symbol column in {url}")
        symbol_col = candidates[0]

    return df[symbol_col].dropna().astype(str).str.strip().unique().tolist()


def load_symbols_from_file(path: str) -> list:
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        col = next((c for c in df.columns if c.lower() == "symbol"), df.columns[0])
        return df[col].dropna().astype(str).str.strip().tolist()
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


# --------------------------------------------------------------------------
# 2. Data download
# --------------------------------------------------------------------------
def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance sometimes returns MultiIndex columns like ('Close', '^NSEI')
    even for a single ticker, depending on version. Flatten to plain
    'Close', 'High', etc. so column selection returns a Series, not a
    single-column DataFrame."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def download_batches(symbols: list, batch_size: int = 150, period: str = "1y") -> dict:
    tickers = [f"{s}.NS" for s in symbols]
    data = {}

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        print(f"  Downloading {i + 1}-{i + len(batch)} of {len(tickers)}...", file=sys.stderr)
        try:
            raw = yf.download(
                tickers=batch, period=period, interval="1d",
                group_by="ticker", threads=True, progress=False, auto_adjust=True,
            )
        except Exception as e:
            print(f"  Batch download failed ({e}), skipping batch.", file=sys.stderr)
            continue

        for t in batch:
            symbol = t[:-3]
            try:
                df = raw if len(batch) == 1 else raw[t]
                df = _flatten_columns(df)
                df = df.dropna(how="all")
                if not df.empty:
                    data[symbol] = df
            except (KeyError, Exception):
                continue
        time.sleep(1)

    return data


def download_benchmark(period: str = "1y") -> pd.DataFrame:
    df = yf.download(BENCHMARK_TICKER, period=period, interval="1d", progress=False, auto_adjust=True)
    df = _flatten_columns(df)
    return df.dropna(how="all")


# --------------------------------------------------------------------------
# 3. Scoring
# --------------------------------------------------------------------------
def score_stock(
    df: pd.DataFrame,
    bench_return_pct: float,
    ema_short: int = 20,
    ema_long: int = 200,
    lookback: int = 5,
    min_return_pct: float = 2.0,
    vol_mult: float = 1.5,
    vol_baseline_days: int = 20,
    min_turnover_cr: float = 5.0,
    min_price: float = 20.0,
    max_pct_from_52w_high: float = 15.0,
    max_single_day_pct: float = 15.0,
) -> dict:
    needed = ema_long + lookback + vol_baseline_days + 5
    if len(df) < needed:
        return None

    close, volume, high = df["Close"], df["Volume"], df["High"]

    ema_s = close.ewm(span=ema_short, adjust=False).mean()
    ema_l = close.ewm(span=ema_long, adjust=False).mean()
    last_close, last_ema_s, last_ema_l = close.iloc[-1], ema_s.iloc[-1], ema_l.iloc[-1]

    above_short_ema = last_close > last_ema_s
    above_long_ema = last_close > last_ema_l
    ema_stack_bullish = last_ema_s > last_ema_l

    ret_pct = (last_close / close.iloc[-1 - lookback] - 1) * 100
    rs_vs_nifty = ret_pct - bench_return_pct

    recent_vol_avg = volume.iloc[-lookback:].mean()
    baseline_vol_avg = volume.iloc[-lookback - vol_baseline_days : -lookback].mean()
    rel_volume = recent_vol_avg / baseline_vol_avg if baseline_vol_avg > 0 else np.nan

    avg_turnover_cr = (close.iloc[-vol_baseline_days:] * volume.iloc[-vol_baseline_days:]).mean() / 1e7

    lookback_window = min(252, len(high))
    high_52w = high.iloc[-lookback_window:].max()
    pct_from_52w_high = (last_close / high_52w - 1) * 100  # <= 0, closer to 0 = nearer the high

    daily_pct = close.iloc[-lookback - 1 :].pct_change().dropna() * 100
    max_single_day = daily_pct.abs().max() if not daily_pct.empty else 0.0
    pump_risk = max_single_day > max_single_day_pct

    passes = (
        above_short_ema
        and above_long_ema
        and ema_stack_bullish
        and ret_pct >= min_return_pct
        and rel_volume >= vol_mult
        and avg_turnover_cr >= min_turnover_cr
        and last_close >= min_price
        and abs(pct_from_52w_high) <= max_pct_from_52w_high
        and not pump_risk
    )

    return {
        "close": round(last_close, 2),
        "last_bar_date": df.index[-1].strftime("%Y-%m-%d"),
        "ema20": round(last_ema_s, 2),
        "ema200": round(last_ema_l, 2),
        f"return_{lookback}d_pct": round(ret_pct, 2),
        "rs_vs_nifty_pct": round(rs_vs_nifty, 2),
        "rel_volume": round(rel_volume, 2) if not np.isnan(rel_volume) else None,
        "avg_turnover_cr": round(avg_turnover_cr, 1),
        "pct_from_52w_high": round(pct_from_52w_high, 1),
        "max_single_day_pct": round(max_single_day, 1),
        "pump_risk_flag": pump_risk,
        "passes_all_filters": passes,
    }


def add_composite_score(hits: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Rank passers by average percentile across the 4 strength metrics."""
    ret_col = f"return_{lookback}d_pct"
    ranks = pd.DataFrame(index=hits.index)
    ranks["r1"] = hits[ret_col].rank(pct=True)
    ranks["r2"] = hits["rel_volume"].rank(pct=True)
    ranks["r3"] = hits["rs_vs_nifty_pct"].rank(pct=True)
    ranks["r4"] = (-hits["pct_from_52w_high"]).rank(pct=True)  # closer to high = better
    hits = hits.copy()
    hits["composite_score"] = ranks.mean(axis=1).round(3)
    return hits.sort_values("composite_score", ascending=False)


# --------------------------------------------------------------------------
# 4. Main
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="NSE EMA + RS + liquidity-aware scanner")
    parser.add_argument("--universe", choices=["nifty50", "nifty100", "nifty200", "nifty500", "all"], default="nifty500")
    parser.add_argument("--symbols-file", help="Custom symbol list, overrides --universe")
    parser.add_argument("--ema-short", type=int, default=20)
    parser.add_argument("--ema-long", type=int, default=200)
    parser.add_argument("--lookback", type=int, default=5)
    parser.add_argument("--min-return", type=float, default=2.0)
    parser.add_argument("--vol-mult", type=float, default=1.5)
    parser.add_argument("--min-turnover-cr", type=float, default=5.0, help="Min avg daily turnover, Rs crore")
    parser.add_argument("--min-price", type=float, default=20.0)
    parser.add_argument("--max-pct-from-52w-high", type=float, default=15.0)
    parser.add_argument("--max-single-day-pct", type=float, default=15.0, help="Exclude if any single day exceeds this move -- likely a circuit/pump day")
    parser.add_argument("--require-market-uptrend", action="store_true", help="Refuse results if Nifty 50 is below its own 200 EMA")
    parser.add_argument("--top-n", type=int, default=30)
    args = parser.parse_args()

    print("Fetching Nifty 50 benchmark...", file=sys.stderr)
    bench = download_benchmark()
    if bench.empty or len(bench) < args.ema_long + args.lookback:
        print("Could not get enough benchmark data -- aborting.", file=sys.stderr)
        return
    bench_close = bench["Close"]
    last_data_date = bench.index[-1].strftime("%Y-%m-%d %H:%M")
    print(f"Latest data bar is dated: {last_data_date} (IST-dated trading session, from Yahoo Finance)",
          file=sys.stderr)
    print("  -> If this isn't today's date, or you're running during market hours, treat the "
          "last bar as provisional/stale, not a live tick.", file=sys.stderr)
    bench_ret_pct = (bench_close.iloc[-1] / bench_close.iloc[-1 - args.lookback] - 1) * 100
    bench_ema_long = bench_close.ewm(span=args.ema_long, adjust=False).mean().iloc[-1]
    market_uptrend = bench_close.iloc[-1] > bench_ema_long
    print(f"Nifty 50: {bench_close.iloc[-1]:.0f}, {args.ema_long}EMA: {bench_ema_long:.0f}, "
          f"{'ABOVE' if market_uptrend else 'BELOW'} -> market regime {'bullish' if market_uptrend else 'not bullish'}",
          file=sys.stderr)

    if args.require_market_uptrend and not market_uptrend:
        print("\n--require-market-uptrend set and Nifty 50 is below its own "
              f"{args.ema_long}-EMA. Skipping scan -- broad market isn't in an uptrend.")
        return

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
            df, bench_return_pct=bench_ret_pct,
            ema_short=args.ema_short, ema_long=args.ema_long, lookback=args.lookback,
            min_return_pct=args.min_return, vol_mult=args.vol_mult,
            min_turnover_cr=args.min_turnover_cr, min_price=args.min_price,
            max_pct_from_52w_high=args.max_pct_from_52w_high,
            max_single_day_pct=args.max_single_day_pct,
        )
        if result is not None:
            result["symbol"] = symbol
            rows.append(result)

    if not rows:
        print("No results -- check internet access to Yahoo Finance / NSE, or loosen the filters.")
        return

    results = pd.DataFrame(rows).set_index("symbol")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"nse_scan_v2_results_{ts}.csv"
    results.to_csv(out_path)
    print(f"\nFull results ({len(results)} stocks) saved to {out_path}\n")

    hits = results[results["passes_all_filters"]]
    if hits.empty:
        print("None passed every filter -- try loosening --min-return, --vol-mult, or --min-turnover-cr.")
        return

    hits = add_composite_score(hits, args.lookback)
    ret_col = f"return_{args.lookback}d_pct"
    cols = ["close", ret_col, "rs_vs_nifty_pct", "rel_volume", "avg_turnover_cr", "pct_from_52w_high", "composite_score"]
    print(f"=== {len(hits)} stocks passed all filters, ranked by composite score ===\n")
    print(hits[cols].head(args.top_n).to_string())


if __name__ == "__main__":
    main()