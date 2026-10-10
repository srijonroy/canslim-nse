---
title: Improving profit margins is the one extra book rule that helped
date: 2026-10-02
status: Adopted
tags: book rules, margins, fundamentals
takeaway: Requiring net profit margin to be higher than a year ago raised the Sharpe from 1.26 to 1.37 and cut the worst drop from −21% to −17.9%; it also held on 2023–26. Every other untested rule from the book's list failed.
source: canslim/booktest.py, data/tune/booktest/
---
**Test.** Each rule from the book's rule list (pp. 424–426) not yet in the system was added on top, one at a time, on 2016–22.

**Passed and adopted.** Net margin up vs a year ago: Sharpe 1.37 vs 1.26 (better in both halves), worst drop −17.9% vs −21%; 2023–26 check 1.60 vs 1.57.

**Failed.**
- Profit growth ≥25% in each of the last 2 quarters
- Stock in a top industry group (the list collapses to 1 stock)
- RS 85 instead of 80
- Accelerating sales
- Accumulation (up-volume vs down-volume)
- Holding 5 stocks instead of 10: 28%/yr but a −35% worst drop
- All of them combined

**Couldn't be tested** (no point-in-time data before 2023): management ownership, buybacks / new management, analyst estimates, cash flow vs EPS, and adding to winners.
