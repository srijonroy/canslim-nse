---
title: The 100 biggest companies are slow movers; mid and small caps are not
date: 2026-10-10
status: Not adopted
tags: size, holding time, large caps
takeaway: After joining the CAN SLIM list, top-100 stocks took a median 224 trading days to gain 20% (2016–22) vs 65–78 for everything smaller. Skipping them improved 2016–22 but not 2023–26, and the result depends on the exact cutoff, so the rule is unchanged.
source: canslim/sizetest.py, data/tune/sizetest/
---
**Question.** Do stocks with a huge market cap take too long to move?

**Data.** Every stock that joined the CAN SLIM passing list (after 4+ weeks off it) and every trade the current system made, grouped by market-cap rank on the signal date: Large = top 100, Mid = 101–250, Small = 251–500, Micro = 501+.

| Market-cap rank | Median trading days to +20% (2016–22 / 2023–26) | Hit +20% within 3 months (2016–22) | Fell 20% before rising 20% (2016–22) |
|---|---|---|---|
| Top 100 | **224 / 113** | **14%** | 54% |
| 101–250 | 78 / 60 | 45% | 33% |
| 251–500 | 65 / 55 | 49% | 43% |
| 501+ | 76 / 45 | 47% | 41% |

**Portfolio test**, buying no new top-100 stocks:

| | 2016–22 | 2023–26 |
|---|---|---|
| Current system | 24.7%/yr, Sharpe 1.37, worst drop −17.9% | 37.7%/yr, Sharpe 1.60, worst drop −13.7% |
| No top-100 buys | 26.8%/yr, Sharpe 1.58, worst drop −14.4% | 36.0%/yr, Sharpe 1.63, worst drop −14.7% |

**Why it isn't used.** Skipping only the top 50 changes nothing, skipping the top 250 is worse, and 2023–26 doesn't confirm it. The system already sells a slow stock within about 2–3 weeks when it drops out of the top 30, so a slow large cap costs little. The idea also came from looking at the same data.

**Practical lesson.** A top-100 name on the list will probably be slow. Mid caps (101–250) were the best group in both periods.
