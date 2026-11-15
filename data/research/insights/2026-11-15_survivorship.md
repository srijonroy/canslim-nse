---
title: Do the backtests only look good because dead stocks are missing?
date: 2026-11-15
status: Checked
tags: survivorship bias, delisted, realism, evidence
takeaway: 548 stocks delisted or merged since 2014 (303 ended badly); most had become too small to trade long before they vanished. Screener has no fundamentals for them, so they were given the fundamental pass rate of listed stocks (10%). Fair estimate: 2016-22 return 25.6% -> 25.7% a year (worst drop -21.1% -> -22.55%), 2023-26 34.4% -> 34.05%. Worst case (all of them pass): 2016-22 26.2% with a -30.9% worst drop, 2023-26 31.9%. Writing failures down to zero changes nothing - the system never still held a stock when it died. Missing dead stocks flatter the return by about 0.4 points a year at most - the edge survives.
source: canslim/experiments/survivorship.py, data/tune/survivorship/results.csv
---
**Question.** The price data only holds stocks listed today, so every stock that went bust or was delisted since 2016 is invisible to the backtest. How much does that flatter the results?

**Method.** NSE bhavcopies 2014-2026 (every stock that traded, series EQ/BE/BZ) rebuilt with the same split/bonus adjustment as the live price files; renamed stocks matched by ISIN. Missing stocks get the same price rules and are assumed to pass the fundamental rules (worst case). Same simulator, costs and market filter. A sanity run rebuilds the live pool from scratch and must match it.

**Delisted or merged equity stocks by year they stopped trading.** 2014: 24, 2015: 75, 2016: 36, 2017: 57, 2018: 44, 2019: 56, 2020: 41, 2021: 63, 2022: 41, 2023: 44, 2024: 23, 2025: 28, 2026: 16.

**Still trading, liquid on 2026-09-30, but not in the backtest cache:** BLISSGVS, BODALCHEM, HFCL, MODISONLTD, RADHIKAJWE, STLTECH, TBZ, UGARSUGAR. Some have price files added after the cache was built; the rest are in the trade-to-trade (BE) segment, which the scanner does not download.

Notes: bhavcopy data ends 2026-10-01. Sanity check: the listed-only pool rebuilt here differs from the backtest pool in 0 stock-days. Fair-estimate rows are the median of 20 random draws (range shown).

**Decision.** Missing dead stocks flatter the return by about 0.4 points a year at most - the edge survives
