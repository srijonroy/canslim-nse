---
title: How much of the result could be luck?
date: 2026-11-15
status: Checked
tags: statistics, luck, bootstrap, random picks, evidence
takeaway: 2016-22: 25.6% a year, but the plausible range is 12.6 .. 45.1% (Sharpe 0.47 .. 2.51). 2023-26: 33.5%, range 14.0 .. 62.1%. The system was behind the Nifty 500 in 5.7% / 3.2% of resamples and behind the Momentum 30 index in 17.4% / 7.8%. Picking at random from the same pool: 25.3 .. 27.6% and 28.7 .. 36.6%; the RS ranking sits at the 8th and 74th percentile.
source: canslim/experiments/error_ranges.py, data/tune/error-ranges/results.csv
---
**Question.** With a pool of about four stocks on a typical day, the results rest on few trades. What range of results is plausible, and does the RS ranking beat random picks from the same pool?

**Method.** Block bootstrap (2000 resamples of 63-day blocks of daily returns; the same blocks for the system and each index in the comparison). Random picks: 200 runs per period choosing among the stocks that pass the rules at random instead of by RS, everything else unchanged. 'Range' = 5th to 95th percentile.

| measure | 2016-22 | 2023+ |
|---|---|---|
| period | 2016-22 | 2023+ |
| return/yr actual | 25.6 | 33.5 |
| return/yr 5%..95% | 12.6 .. 45.1 | 14.0 .. 62.1 |
| Sharpe actual | 1.35 | 1.36 |
| Sharpe 5%..95% | 0.47 .. 2.51 | 0.41 .. 2.70 |
| worst drop 5%..95% | -31.2 .. -13.2 | -23.3 .. -12.5 |
| lead over Nifty 500 5%..95% | -0.7 .. +27.7 | +2.3 .. +46.1 |
| % of resamples behind Nifty 500 | 5.7 | 3.2 |
| lead over Momentum 30 5%..95% | -5.7 .. +22.4 | -3.4 .. +44.8 |
| % of resamples behind Momentum 30 | 17.4 | 7.8 |
| random picks return/yr 5%..95% | 25.3 .. 27.6 | 28.7 .. 36.6 |
| system's percentile among random picks | 8.0 | 74.0 |

**Decision.** Lead over the Nifty 500 could be luck (behind in up to 5.7% of resamples)
