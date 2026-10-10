---
title: CAN SLIM works on NSE, and the edge is in the filters
date: 2026-09-30
status: Adopted
tags: system, market timing, drawdown, momentum
takeaway: The book's hard rules plus "no new buys unless the market is in an uptrend" made about 21%/yr from 2016–26 with a −30% worst drop, vs 12% and −38% for the Nifty 500. Random picks from the passing list did as well as the top-ranked ones, so the edge comes from the filters.
source: canslim/system.py, canslim/tune.py, data/tune/
---
**Walk-forward test, 2016–26.** The book's CAN SLIM rules, ranked by relative strength, 10 stocks, with no new buys in a market correction.

| | Return/yr | Worst drop |
|---|---|---|
| CAN SLIM (book rules + market filter) | ~21% | −30% |
| Nifty 500 | ~12% | −38% |
| Pure momentum (roughly what momentum funds do) | 22–25% | **−54% to −56%** |

**Findings**
- **The filters are the edge.** Random picks from the passing list did as well as the top-ranked ones.
- **Quality halves the drawdown.** Pure momentum earned about the same, with twice the worst drop.
- **ROE ≥ 20% (was 15%).** This was the only tuning change that held: tuned on 2016–22, then run once on 2023–26 at 38.5%/yr with a −16% worst drop, vs 24.9% / −30% for the plain book.
- Later additions: net margin improving (see its own finding), and a liquidity floor lowered to ₹3 Cr/day to include more small caps (not backtested).
