---
title: 10-baggers fall 25–35% several times on the way; no rule held them without also holding losers
date: 2026-10-02
status: Rejected
tags: selling, holding, multibaggers
takeaway: Letting winners run (after +20% or +50%, sell only below the 150/200-day line or 25–30% off the peak) made the average winner +45–49% instead of +23%, but every version had a worse Sharpe (0.66–1.02 vs 1.26) and deeper drawdowns. The system's problem with big winners is churn, not missing them.
source: canslim/holdtest.py, canslim/reentry.py, data/tune/holdtest/, data/tune/reentry/
---
**What the system does.** Median holding 23 days; nothing was held a year in 2016–22. After a sale, the median stock was down 5% 6–24 months later, but 11% doubled within 24 months.

**Hold-longer rules tested (2016–22).**

| Rule | Result |
|---|---|
| After +20%: sell only below the 200-day / 150-day line, or 25% / 30% off the peak | All worse: Sharpe 0.66–1.00 vs 1.26, worst drop −26% to −30% vs −21% |
| After +50%: sell only below the 200-day | Worse |
| Same rules, only for stocks bought a second time | Best was Sharpe 1.02 vs 1.26 |

**Re-entry audit.** 13 stocks sold in 2016–22 later went up 3x or more. The system **bought 11 of them back**, usually within weeks and near the exit price, but captured a median 2% of the run. GRAVITA went up 13x; it was bought 6 times and the system captured 14% of the move.

**Lesson.** The big winners fall 25–35% several times along the way, and on price data alone those drops look like a breakdown. A mechanical rule can't tell them apart from real failures. That's the gap the Journal is meant to measure: whether your judgment, using what the data can't see, does better.
