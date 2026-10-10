---
title: Rising institutional ownership doesn't add anything on NSE
date: 2026-10-02
status: Rejected
tags: institutions, shareholding, book rules
takeaway: O'Neil's "institutional sponsorship" rule, tested on BSE shareholding filings since Dec 2015, didn't improve the system. More mutual-fund schemes buying cut the drawdown sharply but left a list of about 2 stocks and failed on 2023–26.
source: canslim/shp.py, canslim/insttest.py
---
**Data.** BSE quarterly shareholding filings from Dec 2015, used only from the date each filing was made public.

| Filter added to the system (2016–22) | Sharpe | Note |
|---|---|---|
| Current system | 1.37 | |
| Number of institutions rising | 1.34 | |
| Institutional % rising | 1.22 | |
| Number of institutions not falling | 1.36 | worst drop −13.5% |
| Number of MF schemes rising | 1.44 | worst drop −8.3%, but 17.5%/yr and only ~2 stocks pass; 2023–26 worse (1.37 vs 1.60) |

**Lesson.** By the time a stock passes CAN SLIM's earnings and price rules, institutions are usually already there. The filter mostly shrinks the list.
