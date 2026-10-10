---
title: An 8% stop-loss and going to cash both hurt on NSE
date: 2026-09-30
status: Rejected
tags: selling, stop-loss, market timing
takeaway: The book's 8% stop-loss and "sell everything in a correction" both lowered returns on NSE in 2016–26. What works is the softer rule: keep holdings, but buy nothing new until the market is back in an uptrend.
source: canslim/system.py, canslim/tune.py
---
**Tested on 2016–26 against the same CAN SLIM list:**

| Rule | Result |
|---|---|
| 8% stop-loss (book) | Hurt (likely reason, not measured: NSE stocks often dip 8% and recover) |
| Go to cash in a correction | Hurt (likely reason, not measured: it misses the sharp rebounds) |
| No new buys in a correction (kept) | Best balance of return and drawdown |
| Machine-learned blend of factors (walk-forward) | Worst of all |

**Lesson.** On NSE, selling is better driven by the stock dropping out of the CAN SLIM rules or ranking than by a fixed percentage loss.
