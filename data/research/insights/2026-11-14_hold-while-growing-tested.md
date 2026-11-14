---
title: Let winners run while profits keep growing, cut losers early: tested
date: 2026-11-14
status: Tested, not adopted
tags: selling, hold winners, stop loss, growth, CAN SLIM
takeaway: Holding a winner (up 20% or more) until its quarterly profit growth fades made results much worse in 2016–22: 11–17% a year with drops of 45–55%, against 24.7% and −17.9% for the current rule. Price tops before reported growth does, so the rule sits through the fall. Adding a 200-day-average exit rescued most of it (22.3%, −24.7%) but still trailed the current rule, and did worse in 2023–26 too. An 8% stop on losers changed almost nothing, because the current rule already exits losers at an average of −6.4% against an average win of +22.9%.
source: canslim/growthhold.py, data/tune/growthhold/ (results.csv, trades.csv); earlier price-based versions: canslim/holdtest.py
---
**Why tested.** An investor's presentation holds growth stocks through their whole high-growth phase and sells when the growth rate slows. The system's median holding is 23 days. Earlier tests of holding longer used price exits and failed; an exit on the growth rate itself had not been tried.

**Method.** Entry unchanged. Once a holding is up 20% it is no longer sold for dropping out of the ranking or failing a rule, only on the exit shown. Growth = latest quarterly net profit, year on year, as known on the day. 2016–22 for the decision; 2023–26 as a check only. Bar fixed before running (Sharpe +0.03 in both halves, worst drop within 3 points, large-cap Sharpe not lower).

| Variant | Return / yr | Sharpe | Worst drop | Invested | Avg win / avg loss | Held over 1 year | 2023–26 return / worst drop |
|---|---|---|---|---|---|---|---|
| Current rule | 24.7% | 1.37 | −17.9% | 39% | +22.9% / −6.4% | 0 | 37.7% / −13.7% |
| A: hold till profit growth below 0 | 10.9% | 0.23 | −54.6% | 70% | +24.0% / −9.8% | 11 | 26.5% / −29.0% |
| B: hold till growth below 15% | 14.7% | 0.41 | −48.7% | 68% | +23.8% / −8.1% | 9 | 30.2% / −28.0% |
| C: hold till growth below 25% and falling | 16.5% | 0.51 | −44.7% | 63% | +25.8% / −8.4% | 6 | 42.2% / −20.8% |
| D: B, or close below the 200-day average | 22.3% | 0.89 | −24.7% | 56% | +37.4% / −6.3% | 4 | 23.6% / −27.1% |
| E: B plus 8% stop on losers | 15.1% | 0.43 | −46.3% | 67% | +23.4% / −7.8% | 9 | 28.1% / −28.8% |
| F: D plus 8% stop on losers | 22.4% | 0.89 | −23.8% | 55% | +36.8% / −6.2% | 3 | 21.4% / −27.7% |

**Reading it.**
- Reported growth lags price. A stock up 20% that then falls 40% often still shows growing quarterly profits, so a growth-only exit holds it all the way down (variants A, B, C, E).
- With a price exit added (D, F) the average winning trade rises from +23% to +37%, but the portfolio still earns less: gains are given back before the exit, and held positions block slots that the current rule would refill with the next strongest stock.
- The losers are already cut early. The current rule's average loss is −6.4%; an 8% stop adds nothing.
- Variant C beat the current rule on return in 2023–26 (42.2% vs 37.7%) but with a deeper drop, and it was far worse in 2016–22. Not consistent.

**Count so far.** Sixteen ways of holding winners longer have now been tested (ten price-based in holdtest.py, six here). None beat the current exit.

**What a rule cannot copy.** The presentation's long holds are a few hand-picked companies, chosen by judgment about the business. These tests can only say that holding every winner mechanically does not work.
