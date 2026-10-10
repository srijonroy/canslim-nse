---
title: Preferential issues: the move starts before the news; promoter money is what matters after
date: 2026-10-10
status: Research only
tags: corporate actions, small caps, promoters, timing
takeaway: Stocks beat same-size peers by a median 10.8% in the 3 months BEFORE a preferential issue is approved. After it, issues where promoters put in money beat peers (12m +4.6%, 12.9% doubled vs 8.1%); issues to outside investors only lagged (12m −8.6%).
source: canslim/preftest.py, data/research/pref/
---
**Question.** Stocks with a preferential allotment seemed to move a lot. Is that real, and can you still catch it after the news?

**Data.** Every preferential issue that got NSE in-principle approval from Apr 2023 to Sep 2026 (NSE's structured records start in Apr 2023). 474 issues are in our price data, 84% of them micro caps (market-cap rank 501+). Day 0 = the board resolution date; the "buy" is the close the day after, because the outcome is often filed after market hours. Every return is compared with the **median stock of the same size over the same dates**, so the 2023–24 small-cap boom doesn't flatter it.

| | Before (3m to the board meeting) | 6m after | 12m after | Doubled in 12m |
|---|---|---|---|---|
| All issues (474) | **+10.8%** | +4.1% | −0.1% | 11.8% (same-size stocks 8.1%) |
| Promoters put money in (290) | +12.1% | **+6.2%** (57% beat peers) | **+4.6%** | 12.9% |
| Outside investors only (184) | +9.6% | −1.4% | **−8.6%** (43% beat) | 10.1% |
| Promoters in + issue >15% of market cap (62) | +9.6% | **+13.7%** (67% beat) | +4.6% | 13.3% |

Medians, relative to same-size peers.

**What it means**
- Much of the move is already done when the news comes out. The stock that "moved a lot around its preferential issue" mostly moved before it.
- Promoter money is the signal: promoters subscribe when they expect higher prices. Money from outside investors only is not.
- It is a lottery-ticket effect. The average 12-month result is +28% vs peers, but the median is about zero: a few huge winners pull the average up.

**Update: 2016–22 now checked** (NSE announcements, 459 issues; see "What moves NSE stocks"). Across all preferential issues, the 12-month result was **−5.6% vs peers, with 44% beating them**. So the overall 2023–26 picture doesn't carry back. Older announcements rarely say who the allottees are, so the promoter-vs-outsider split, the part that looked useful, still can't be checked before 2023.

**Caveats.** Only 2023–26 for the promoter split, one market phase (boom, then the 2025 correction). Small samples once split. Not tested as a portfolio. BSE history for 2016–23 still has to be downloaded (BSE blocks fast downloads) to confirm it.
