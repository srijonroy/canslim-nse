---
title: Promoter ownership doesn't improve CAN SLIM; its stocks are already promoter-heavy
date: 2026-10-10
status: Rejected
tags: promoters, book rules, shareholding
takeaway: Requiring promoter holding ≥ 50%, ≥ 35%, or not falling (book rule 18, management ownership) failed on 2016–22. ≥ 50% cut the worst drop from −17.9% to −11.8% but also the return (24.7% → 20.5%) and left a list of about 2 stocks. The median CAN SLIM stock already has 56% promoter holding.
source: canslim/promotertest.py, canslim/shp.py (promoter_pct), data/tune/promotertest/
---
**Data.** BSE shareholding patterns for every stock that ever passed CAN SLIM (241 stocks), quarterly from Dec 2015. Promoter % = 100 − public %. Each quarter is used only from the date it was filed. Data covers 92% of passing stock-weeks.

| Extra rule | 2016–22 | 2023–26 | Stocks passing (median) |
|---|---|---|---|
| None (current) | 24.7%/yr, Sharpe 1.37, worst drop −17.9% | 37.7%/yr, Sharpe 1.60, −13.7% | 4 / 9 |
| Promoter ≥ 50% | 20.5%, 1.29, **−11.8%** | 32.2%, 1.43, −12.4% | 2 / 7 |
| Promoter ≥ 35% | 23.7%, 1.34, −17.0% | 37.8%, 1.68, −12.8% | 3 / 8 |
| Promoter not down > 1 point in a year | 21.5%, 1.23, −17.2% | 35.2%, 1.58, −15.7% | 3 / 7 |

**Lesson.** In India, promoters typically own a large stake, so "management owns stock" is already true for most CAN SLIM names. Raising the bar mostly shrinks an already small list. The lower drawdown at ≥ 50% is worth knowing for anyone who wants a calmer portfolio, but it costs about 4 points of return a year.
