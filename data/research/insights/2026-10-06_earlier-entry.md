---
title: Buying earlier costs more in drawdowns than it gains
date: 2026-10-06
status: Rejected
tags: entry timing, drawdown
takeaway: Buying earlier in a stock's run (looser trend rule, earnings-only signals) caught more 2x trades but raised the worst drop to −23% to −43%. Re-ranking the passing list barely changes timing, because the list is only about 4 stocks.
source: canslim/earlytest.py, data/tune/earlytest/
---
**Question.** CAN SLIM buys stocks already up a lot from their lows (median 2.45x off the 1-year low). Can we get in earlier?

| Variant (2016–22) | Result |
|---|---|
| E1 rank by least stretched, E2 fresh qualifiers only | Entry timing barely changes (still 2.45x off the low). The passing list is about 4 stocks, so the rules set the timing, not the ranking |
| E3 price above a rising 200-day + RS 70 | Earlier (2.15x off the low), but Sharpe 0.99 vs 1.37 and worst drop −22.8% |
| E4 earnings-monitor signal (margin jump / two strong quarters) | 10 trades of +100% vs 4, but worst drop −43% |

**Lesson.** Earliness costs drawdown. The early lists stay in the report as a research radar, not as buy signals.
