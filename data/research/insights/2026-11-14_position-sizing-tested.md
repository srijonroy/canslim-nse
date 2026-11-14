---
title: Position sizing and number of stocks: equal weight in 10 slots stays
date: 2026-11-14
status: Tested, not adopted
tags: position sizing, weighting, concentration, CAN SLIM, cash drag
takeaway: Putting more money in the top-ranked stocks raised return (31.0% vs 24.7% a year, 2016–22) but only because the portfolio was more invested (46% vs 39%), and the worst drop grew from −17.9% to −24.5%. Weighting calmer stocks more did nothing useful. Five slots: more return, far deeper drop (−31.7%). Fifteen or twenty slots: lower return, because only about 4 stocks pass the rules on a typical day and the extra slots sit in cash. Nothing passed the bar. How much of the money is invested drives both return and risk; which stock gets more does not.
source: canslim/weighttest.py, data/tune/weighttest/results.csv
---
**Method.** Same entry and exit rules as the live system; only position size or the number of slots changes. 2016–22 only (2023–26 already seen). Bar fixed before running: Sharpe at least 0.03 better in both 2016–19 and 2020–22, worst drop no more than 3 points deeper, large-cap Sharpe not lower.

| Variant | Return / yr | Sharpe | Sharpe 16–19 | Sharpe 20–22 | Worst drop | Invested |
|---|---|---|---|---|---|---|
| 10 equal slots (current) | 24.7% | 1.37 | 0.85 | 1.93 | −17.9% | 39% |
| Rank-weighted (ranks 1–3 get 1.5 slots, 4–7 one, 8+ half) | 31.0% | 1.47 | 0.82 | 2.23 | −24.5% | 46% |
| Volatility-weighted (calmer stocks get more) | 23.7% | 1.31 | 0.64 | 2.01 | −19.9% | 39% |
| 5 equal slots | 30.7% | 1.18 | 0.70 | 1.74 | −31.7% | 57% |
| 15 equal slots | 19.9% | 1.38 | 0.86 | 1.93 | −11.9% | 28% |
| 20 equal slots | 16.4% | 1.31 | 0.88 | 1.75 | −10.5% | 22% |

**Reading it.** The variants line up almost exactly by how much money is invested: more invested, more return and a deeper worst drop. Rank-weighting gains nothing in 2016–19 and all of its edge is in 2020–22. More than 10 slots cannot help while only about 4 stocks qualify on a typical day.

**Not testable:** weighting by the research-brief conviction score. Briefs only exist from October 2026, so there is no history to test on.

**What follows.** The open lever is the idle cash (61% on average in 2016–22), not the split between stocks.
