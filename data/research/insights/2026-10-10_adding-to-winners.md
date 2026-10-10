---
title: Adding to winners (pyramiding) lowers returns on NSE
date: 2026-10-10
status: Rejected
tags: position sizing, book rules, winners
takeaway: Buying half a position and adding only once it is up (the book's rule 12) cut returns from 24.7% to 19–21%/yr in 2016–22 and from 37.7% to 31–34% in 2023–26, with a lower Sharpe. It only softened drawdowns (−10 to −11% vs −13.7% in 2023–26). The system already sits mostly in cash, and pyramiding leaves even more uninvested.
source: canslim/pyramidtest.py, canslim/portfolio.py (Config.pyramid), data/tune/pyramidtest/
---
**Test.** Same CAN SLIM entries and exits. Only how a position is built changes.

| Variant | 2016–22 | 2023–26 | Trades fully built |
|---|---|---|---|
| Full slot at once (current) | 24.7%/yr, Sharpe 1.37, worst drop −17.9% | 37.7%/yr, Sharpe 1.60, −13.7% | 100% |
| Book: 50%, +30% at +2.5%, +20% at +5% | 21.1%, 1.21, −17.5% | 33.5%, 1.56, −11.4% | 46–50% |
| 50%, +50% at +5% | 20.6%, 1.19, −17.8% | 32.5%, 1.52, −11.1% | 50–52% |
| 50%, +50% at +10% | 19.3%, 1.15, −16.2% | 31.2%, 1.53, −10.0% | 37–40% |

**Why it fails here**
- **The system is already under-invested.** On average only 39% of the money was in stocks in 2016–22 (61% in 2023–26), because the passing list is often about 4 stocks for 10 slots. Pyramiding drops that to 31–34%.
- **Adds come late and at higher prices,** and the holding is often sold within weeks when it drops out of the ranking, so the extra money rarely catches the big part of a move.

**What it points to.** The bigger lever is how much money is invested at all (the cash drag), not how each position is built. An earlier test of 5 stocks instead of 10 made 28%/yr but with a −35% worst drop.
