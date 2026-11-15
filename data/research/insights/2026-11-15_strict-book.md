---
title: Strict O'Neil vs the live system: what each departure costs
date: 2026-11-15
status: Tested, not adopted
tags: CAN SLIM, book, EPS, bases, breakouts, stop-loss, profit-taking
takeaway: The strict O'Neil version almost never buys on NSE: about 1 trade a year, 1% invested, 6.5% a year (2016-22) against the live system's 25.6%. Two book rules do it: annual EPS up 25%+ in each of the last 3 years (pool 4 -> 1 stock; alone 8.5% a year) and buying only on a base breakout on volume (alone 8.7%; a lenient reading 16.6% with half the drawdown but 9.4% in 2023+). The other departures cost little either way: EPS instead of profit 24.4%, 8% stop 24.9%, book sells (stop + 20% profit rule) 22.4%, no trend template 25.1%. None passes the bar; the live system's departures from the book are justified on NSE data.
source: canslim/experiments/strict_book.py, data/tune/strict-book/results.csv
---
**Question.** The live system departs from the book in several places (profit instead of EPS, softer A and sales rules, a trend template, no base breakouts, no stop-loss, no profit-taking). What does each departure cost or gain, and how does a strict book version do?

**Method.** Same data, dates and costs as every test. One variant per departure, each changed alone from the live system, then the strict book version with all of them, and the strict entry with the live exit. Book thresholds fixed before running (see canslim/experiments/strict_book.py).

**Decision bar (fixed before running).** Sharpe at least 0.03 higher than the current system in BOTH halves of 2016-22 (2016-19, 2020-22), worst drop no more than 3 points deeper, and the large-cap-only Sharpe not lower.

**Each change on its own, 2016-22** (vs live):

- 1 EPS instead of profit (C and A): 24.4% / Sharpe 1.32 / DD -19.1 (2023+ 32.5%)
- 2 book A: EPS +25% each of 3 yrs, ROE 17: 8.5% / Sharpe 0.39 / DD -9.3 (2023+ 9.4%)
- 3 book sales: +25% or 3-qtr acceleration: 15.8% / Sharpe 0.89 / DD -15.9 (2023+ 38.2%)
- 4 drop the trend template: 25.1% / Sharpe 1.22 / DD -21.6 (2023+ 38.1%)
- 5 buy only on base breakouts on volume: 8.7% / Sharpe 0.75 / DD -5.8 (2023+ 6.4%)
- 6 8% stop-loss: 24.9% / Sharpe 1.32 / DD -18.9 (2023+ 29.7%)
- 7 book sells: +20% profit, 8-week rule, no rank exit: 12.8% / Sharpe 0.43 / DD -46.7 (2023+ 23.5%)
- 6+7 book sells together (stop + profit rule), live entry: 22.4% / Sharpe 1.12 / DD -20.7 (2023+ 34.2%)
- 5b base breakouts, lenient reading: 16.6% / Sharpe 1.3 / DD -9.1 (2023+ 9.4%)
- STRICT BOOK (all of the above): 6.5% / Sharpe 0.33 / DD -3.0 (2023+ 6.0%)
- strict book entry, live exit: 7.1% / Sharpe 0.61 / DD -3.0 (2023+ 6.0%)
- BOOK, lenient breakouts: 7.7% / Sharpe 0.72 / DD -3.0 (2023+ 5.3%)

| period | variant | CAGR % | Sharpe | maxDD % | invested % | trades/yr | big Sharpe | Sharpe 16-19 | CAGR 16-19 | Sharpe 20-22 | CAGR 20-22 | passes bar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016-22 | live system | 25.6 | 1.34 | -21.1 | 44.0 | 39.0 | 0.03 | 1.01 | 18.4 | 1.72 | 35.7 | False |
| 2023+ | live system | 34.4 | 1.41 | -14.2 | 63.0 | 56.0 | 1.63 |  |  |  |  | False |
| 2016-22 | 1 EPS instead of profit (C and A) | 24.4 | 1.32 | -19.1 | 40.0 | 35.0 | -0.3 | 0.94 | 16.7 | 1.75 | 35.2 | False |
| 2023+ | 1 EPS instead of profit (C and A) | 32.5 | 1.34 | -15.2 | 62.0 | 58.0 | 1.7 |  |  |  |  | False |
| 2016-22 | 2 book A: EPS +25% each of 3 yrs, ROE 17 | 8.5 | 0.39 | -9.3 | 11.0 | 10.0 | -0.84 | 0.61 | 9.9 | 0.09 | 6.6 | False |
| 2023+ | 2 book A: EPS +25% each of 3 yrs, ROE 17 | 9.4 | 0.35 | -14.2 | 28.0 | 26.0 | 0.28 |  |  |  |  | False |
| 2016-22 | 3 book sales: +25% or 3-qtr acceleration | 15.8 | 0.89 | -15.9 | 27.0 | 25.0 | -0.19 | 1.02 | 14.2 | 0.84 | 17.9 | False |
| 2023+ | 3 book sales: +25% or 3-qtr acceleration | 38.2 | 1.84 | -13.1 | 51.0 | 43.0 | 2.01 |  |  |  |  | False |
| 2016-22 | 4 drop the trend template | 25.1 | 1.22 | -21.6 | 51.0 | 39.0 | 0.06 | 0.93 | 18.4 | 1.55 | 34.4 | False |
| 2023+ | 4 drop the trend template | 38.1 | 1.57 | -14.1 | 67.0 | 49.0 | 2.07 |  |  |  |  | False |
| 2016-22 | 5 buy only on base breakouts on volume | 8.7 | 0.75 | -5.8 | 2.0 | 1.0 | -0.56 | -0.95 | 4.8 | 1.53 | 14.0 | False |
| 2023+ | 5 buy only on base breakouts on volume | 6.4 | 0.18 | -2.7 | 2.0 | 2.0 | 0.13 |  |  |  |  | False |
| 2016-22 | 6 8% stop-loss | 24.9 | 1.32 | -18.9 | 43.0 | 40.0 | 0.06 | 1.0 | 17.9 | 1.69 | 34.6 | False |
| 2023+ | 6 8% stop-loss | 29.7 | 1.24 | -17.9 | 61.0 | 61.0 | 1.63 |  |  |  |  | False |
| 2016-22 | 7 book sells: +20% profit, 8-week rule, no rank exit | 12.8 | 0.43 | -46.7 | 57.0 | 7.0 | -0.29 | 0.35 | 11.4 | 0.52 | 14.6 | False |
| 2023+ | 7 book sells: +20% profit, 8-week rule, no rank exit | 23.5 | 0.96 | -25.9 | 64.0 | 11.0 | 1.39 |  |  |  |  | False |
| 2016-22 | 6+7 book sells together (stop + profit rule), live entry | 22.4 | 1.12 | -20.7 | 53.0 | 40.0 | -0.07 | 0.56 | 13.0 | 1.74 | 36.0 | False |
| 2023+ | 6+7 book sells together (stop + profit rule), live entry | 34.2 | 1.57 | -14.3 | 60.0 | 50.0 | 1.65 |  |  |  |  | False |
| 2016-22 | 5b base breakouts, lenient reading | 16.6 | 1.3 | -9.1 | 15.0 | 10.0 | 0.42 | 0.76 | 10.7 | 1.84 | 24.7 | False |
| 2023+ | 5b base breakouts, lenient reading | 9.4 | 0.42 | -8.9 | 12.0 | 13.0 | 0.74 |  |  |  |  | False |
| 2016-22 | STRICT BOOK (all of the above) | 6.5 | 0.33 | -3.0 | 1.0 | 1.0 |  | 0.63 | 6.6 | 0.21 | 6.5 | False |
| 2023+ | STRICT BOOK (all of the above) | 6.0 |  | 0.0 | 0.0 |  |  |  |  |  |  | False |
| 2016-22 | strict book entry, live exit | 7.1 | 0.61 | -3.0 | 1.0 | 0.0 |  | 0.5 | 6.5 | 0.75 | 7.7 | False |
| 2023+ | strict book entry, live exit | 6.0 |  | 0.0 | 0.0 |  |  |  |  |  |  | False |
| 2016-22 | BOOK, lenient breakouts | 7.7 | 0.72 | -3.0 | 1.0 | 1.0 |  | 0.93 | 7.7 | 0.57 | 7.6 | False |
| 2023+ | BOOK, lenient breakouts | 5.3 | -0.34 | -2.5 | 2.0 | 2.0 | -0.18 |  |  |  |  | False |

**Decision.** Keep the live system. No return to the book passes the bar. The book's two strictest rules (3 straight years of 25%+ EPS growth, base breakouts on volume) leave almost nothing to buy in NSE's liquid universe. Not tested yet (data being built): institutional quality (I), new products / orders / management (N catalyst); analyst estimates need a paid source.
