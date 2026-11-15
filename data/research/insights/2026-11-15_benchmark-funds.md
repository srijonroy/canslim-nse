---
title: The system vs a momentum index fund
date: 2026-11-15
status: Checked - system ahead
tags: benchmark, momentum, index fund, evidence
takeaway: In 2016-22 the system made 25.6% a year with a worst drop of -21.1%; the best momentum index (Midcap150 Momentum 50) made 19.8% with -39.6%. In 2023-26: system 33.5% / -14.2%, best index (Midcap150 Momentum 50) 18.2% / -26.7%. Daily correlation with Nifty200 Momentum 30: 0.45. The system beats every momentum index on both return and worst drop, in both periods - keep it.
source: canslim/experiments/benchmark_funds.py, data/tune/benchmark-funds/results.csv
---
**Question.** Does the system do better than just buying a momentum index fund, which needs no work?

**Method.** Same days for every curve. NSE price indices (no dividends, about 1% a year understated, roughly offset by a fund's 0.3-0.5% fee). The system is the live rules (data/tune/final.json) with 6% on idle cash. 'Beats' = higher return AND a shallower worst drop than every momentum index.

| period | holding | CAGR % | Sharpe | maxDD % | corr with system |
|---|---|---|---|---|---|
| 2016-22 | CAN SLIM system | 25.6 | 1.35 | -21.1 | 1.0 |
| 2016-22 | Nifty 500 | 12.8 | 0.39 | -38.3 | 0.37 |
| 2016-22 | Nifty200 Momentum 30 | 17.4 | 0.58 | -34.2 | 0.38 |
| 2016-22 | Nifty500 Momentum 50 | 17.5 | 0.56 | -39.4 | 0.45 |
| 2016-22 | Midcap150 Momentum 50 | 19.8 | 0.73 | -39.6 | 0.45 |
| 2023+ | CAN SLIM system | 33.5 | 1.36 | -14.2 | 1.0 |
| 2023+ | Nifty 500 | 9.7 | 0.28 | -18.8 | 0.52 |
| 2023+ | Nifty200 Momentum 30 | 11.6 | 0.3 | -31.8 | 0.55 |
| 2023+ | Nifty500 Momentum 50 | 15.4 | 0.46 | -31.8 | 0.61 |
| 2023+ | Midcap150 Momentum 50 | 18.2 | 0.43 | -26.7 | 0.4 |
| 2016-now | CAN SLIM system | 28.1 | 1.32 | -21.1 | 1.0 |
| 2016-now | Nifty 500 | 11.8 | 0.36 | -38.3 | 0.41 |
| 2016-now | Nifty200 Momentum 30 | 15.4 | 0.49 | -34.2 | 0.45 |
| 2016-now | Nifty500 Momentum 50 | 16.8 | 0.53 | -39.4 | 0.51 |
| 2016-now | Midcap150 Momentum 50 | 19.3 | 0.59 | -39.6 | 0.42 |

**Year by year (% return).**

| year | CAN SLIM system | Nifty 500 | Nifty200 Momentum 30 | Nifty500 Momentum 50 | Midcap150 Momentum 50 |
|---|---|---|---|---|---|
| 2016 | 9.1 | 3.4 | 7.7 | -2.8 | 4.5 |
| 2017 | 79.5 | 35.9 | 54.5 | 67.2 | 72.9 |
| 2018 | -9.1 | -3.4 | -2.4 | -11.5 | -17.5 |
| 2019 | 8.5 | 7.7 | 9.7 | 7.8 | 4.9 |
| 2020 | 45.0 | 16.7 | 18.8 | 19.9 | 25.8 |
| 2021 | 81.7 | 30.2 | 52.1 | 77.8 | 77.1 |
| 2022 | -5.6 | 3.0 | -6.4 | -8.3 | -0.4 |
| 2023 | 60.2 | 25.8 | 40.7 | 46.7 | 51.5 |
| 2024 | 42.0 | 15.2 | 20.0 | 26.3 | 31.6 |
| 2025 | -2.1 | 6.7 | -5.1 | -7.9 | -3.9 |
| 2026 | 28.4 | -8.4 | -6.2 | -0.2 | -2.6 |

Index data ends 2026-10-01; all curves stop there.

**Decision.** The system beats every momentum index on both return and worst drop, in both periods - keep it
