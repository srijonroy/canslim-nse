---
title: The market-wide red flags don't help CAN SLIM; its filters already avoid those stocks
date: 2026-10-10
status: Rejected
tags: red flags, selling, system
takeaway: Blocking or selling CAN SLIM stocks with a recent red-flag event made returns worse in both periods (24.7% → 20.5%/yr in 2016–22, 37.7% → 30.8% in 2023–26). Rare flags (CFO resigns, QIP, tender buyback, pledge invoked) almost never hit CAN SLIM stocks; common ones (exchange price/volume queries, bulk-deal buying) fire on its breakouts.
source: canslim/flagtest.py, data/tune/flagtest/
---
**Question.** The event study found events that are bad news for the average NSE stock. Should CAN SLIM avoid stocks that just had one?

**Flags.** CFO resigns, exchange query on unusual price/volume, QIP, tender buyback, pledge invoked, bulk buying by an individual or company. A flag stays active for 90 days.

| Variant | 2016–22 | 2023–26 |
|---|---|---|
| Current system | 24.7%/yr, Sharpe 1.37, worst drop −17.9% | 37.7%/yr, Sharpe 1.60, worst drop −13.7% |
| A: no new buys while flagged | 20.5%/yr, Sharpe 1.15, −18.0% | 30.8%/yr, Sharpe 1.34, −22.1% |
| B: A + sell when flagged | 17.6%/yr, Sharpe 0.98, −16.4% | 32.6%/yr, Sharpe 1.45, −21.8% |

**Why.** 17.7% of passing stock-weeks carry a flag, almost all from two sources. Exchange price/volume queries hit 10.7% of passing stocks, and blocking them alone cut 2016–22 Sharpe to 1.23. Bulk-deal buying hit 3–5% and cut Sharpe to 1.28–1.34. Both fire because a CAN SLIM stock is breaking out on volume. The rare flags each touch under 1% of passing stocks, so blocking them changes nothing.

**Lesson.** An event's average effect across the whole market doesn't carry over to a filtered list. The bad outcomes come from speculative micro caps that CAN SLIM's earnings, ROE and trend rules already exclude.
