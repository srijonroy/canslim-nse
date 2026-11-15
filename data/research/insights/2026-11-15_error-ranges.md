---
title: How much of the result could be luck?
date: 2026-11-15
status: Checked
tags: statistics, luck, bootstrap, random picks, evidence
takeaway: 2016-22: 26.8% a year, but the plausible range is 13.5 .. 46.7% (Sharpe 0.54 .. 2.61). 2023-26: 33.7%, range 14.7 .. 61.7%. The system was behind the Nifty 500 in 4.5% / 2.9% of resamples and behind the Momentum 30 index in 13.7% / 7.4%. Picking at random from the same pool: 26.3 .. 28.7% and 29.6 .. 38.2%; the RS ranking sits at the 12th and 64th percentile.
source: canslim/experiments/error_ranges.py, data/tune/error-ranges/results.csv
---
**Question.** With a pool of about four stocks on a typical day, the results rest on few trades. What range of results is plausible, and does the RS ranking beat random picks from the same pool?

**Method.** Block bootstrap (2000 resamples of 63-day blocks of daily returns; the same blocks for the system and each index in the comparison). Random picks: 200 runs per period choosing among the stocks that pass the rules at random instead of by RS, everything else unchanged. 'Range' = 5th to 95th percentile.

| measure | 2016-22 | 2023+ |
|---|---|---|
| period | 2016-22 | 2023+ |
| return/yr actual | 26.8 | 33.7 |
| return/yr 5%..95% | 13.5 .. 46.7 | 14.7 .. 61.7 |
| Sharpe actual | 1.42 | 1.37 |
| Sharpe 5%..95% | 0.54 .. 2.61 | 0.43 .. 2.72 |
| worst drop 5%..95% | -30.6 .. -13.0 | -22.8 .. -12.2 |
| lead over Nifty 500 5%..95% | +0.7 .. +29.2 | +2.6 .. +45.9 |
| % of resamples behind Nifty 500 | 4.5 | 2.9 |
| lead over Momentum 30 5%..95% | -4.5 .. +23.9 | -3.1 .. +44.3 |
| % of resamples behind Momentum 30 | 13.7 | 7.4 |
| random picks return/yr 5%..95% | 26.3 .. 28.7 | 29.6 .. 38.2 |
| system's percentile among random picks | 12.0 | 64.0 |

**Decision.** Lead over the Nifty 500 is unlikely to be luck (behind in at most 4.5% of resamples)
