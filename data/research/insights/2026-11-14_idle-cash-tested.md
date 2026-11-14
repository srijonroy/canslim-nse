---
title: Putting the system's idle cash into the index or the Graham list
date: 2026-11-14
status: Tested, not adopted
tags: cash drag, idle cash, Graham, Nifty 500, CAN SLIM
takeaway: The system sits about 60% in cash on average. Putting that cash into the Nifty 500 raised the 2016–22 return a little (28.3% vs 24.7% a year) but more than doubled the worst drop (−39.5% vs −17.9%). Putting it into the Graham list lowered the return (23.9%) and deepened the drop (−26.6%). Doing either only in market uptrends was no better. In 2023–26 the Graham version did beat the current system (41.0% vs 37.7%, similar drop), but it failed in 2016–22, so it is not consistent. The cash is idle mostly when the market is weak or few stocks qualify, which is when other shares also do badly.
source: canslim/idletest.py, data/tune/idletest/results.csv
---
**Why tested.** Earlier tests (pyramiding, position sizing) kept pointing at the same thing: return and risk follow how much of the money is invested, and the system is only about 39% invested on average in 2016–22.

**Method.** The CAN SLIM trades are unchanged. Each day the idle fraction earns a second holding's return instead of the 6% cash rate; moving money in or out of the second holding costs 0.3%. The Graham holding is the 20-stock Graham portfolio from the framework comparison. The Nifty 500 is the price index without dividends (about 1.2% a year understated). 2016–22 for the decision; 2023 onward as a check only. Bar fixed before running (Sharpe +0.03 in both halves, worst drop within 3 points, large-cap Sharpe not lower).

| Idle cash goes to | 2016–22 return / yr | Sharpe | Worst drop | Sharpe 16–19 | Sharpe 20–22 | 2023+ return / yr | 2023+ worst drop |
|---|---|---|---|---|---|---|---|
| Cash at 6% (current) | 24.7% | 1.37 | −17.9% | 0.85 | 1.93 | 37.7% | −13.7% |
| Nifty 500, always | 28.3% | 1.07 | −39.5% | 0.80 | 1.39 | 37.3% | −21.1% |
| Nifty 500, only in uptrends | 24.1% | 1.07 | −27.3% | 0.35 | 1.89 | 36.9% | −18.9% |
| Graham list, always | 23.9% | 1.17 | −26.6% | 0.60 | 1.77 | 41.0% | −15.5% |
| Graham list, only in uptrends | 22.8% | 1.17 | −21.1% | 0.45 | 1.93 | 37.4% | −15.8% |

**Reading it.**
- The cash is not idle at random. It is idle when the market model says no new buys, or when few stocks pass the rules. Those are the times the index and value stocks tend to fall, so filling the gap adds risk faster than return.
- The Nifty version's worst drop of −39.5% is March 2020: the system was mostly in cash then, the index was not.
- The "only in uptrends" versions do not help: in uptrends the system is already mostly invested, so little cash is left to place, and the switching costs eat the rest.
- The Graham list did better in 2023–26. One good period out of three is not enough to adopt.

**What follows.** The cash is part of how the system keeps its drops small. Four separate tests (pyramiding, position sizing, slot count, idle cash) now say the same thing: more return is available only by accepting a deeper worst drop.
