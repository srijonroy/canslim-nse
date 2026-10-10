---
title: What came before NSE stocks doubled
date: 2026-10-01
status: Adopted
tags: multibaggers, momentum, margins, size
takeaway: Price strength was the most reliable sign: stocks up >100% in 6 months doubled again 33%/28% of the time vs a 15%/14% base rate. Margin expansion and two strong profit quarters also helped in both periods; sales growth only helped in 2023–25. Small, volatile stocks double more often but also crash more often.
source: canslim/winners.py, data/research/winners/, data/reports/winners_study.html
---
**Question.** What did stocks look like just before they doubled within 12 months?

**Data.** Every liquid NSE stock (≥ ₹0.5 Cr/day traded), monthly. Signals found on 2016–21, checked on 2023–25. Base rate: 15% / 14% doubled (inflated, because only currently listed stocks are in the data).

| Signal | Doubled within 12m (2016–21 / 2023–25) |
|---|---|
| Base rate | 15% / 14% |
| Up >100% in the last 6 months | **33% / 28%** |
| Top relative strength | 21% / 21% |
| Passes CAN SLIM | 21% / 21% |
| Operating margin up >6 points | 18% / 20% |
| Profit up >50% in 2 straight quarters | 17% / 20% |
| Smallest 20% by traded value | 21% / 18% (but fell 30%+ 36% / 32% of the time) |
| Largest 20% | 7% / 10% (fell 30%+ 29% / 17%) |

**Lessons**
- Strength begets strength: a stock already up a lot is more likely, not less, to double again. The related run-up test agrees: trades bought after a >100% 6-month run did better (+8.4% vs +5.8%).
- A machine-learning model on all signals scored 49.5% in sample but 21.6% out of sample, no better than plain CAN SLIM. It mostly learned "small and volatile".
