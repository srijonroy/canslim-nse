---
title: Seven other stock-picking frameworks vs CAN SLIM on NSE
date: 2026-10-14
status: Research only
tags: frameworks, value, quality, growth, momentum, Graham, Lynch, Greenblatt, Coffee Can, QGLP, Minervini, Weinstein
takeaway: Over 2016–2026 none of seven famous frameworks came close to CAN SLIM (28.9%/yr, Sharpe 1.42, worst drop −18%). Best of the rest: Minervini's trend template 21.2%/yr but a −45% drop; Lynch 14.7% (−45%); Graham 12.7% with a −15% drop (steadiest, and the least like CAN SLIM). Coffee Can, Magic Formula, QGLP-style and Weinstein were at or below the Nifty 500 (11.8%/yr). Their daily lists are kept on the app page "Other frameworks" for comparison; nothing changes the CAN SLIM picks.
source: canslim/frameworks.py (rules, daily lists), canslim/fwtest.py (backtest), data/tune/frameworks/ (results.csv, equity.csv, summary.json); independent code review by a separate agent 2026-10-14
---
**Method.** Each framework's rules were written from its original source before testing (full text on the app page). Point-in-time data only, weekly, 0.3% cost per side, liquid universe (≥ Rs 3 Cr/day). Value and quality styles: 20 stocks, always invested, keep while ranked in the top 60. Minervini and Weinstein: 10 stocks, no new buys unless the market is in an uptrend (like CAN SLIM). Uninvested money earns 6% a year in every portfolio. No tuning.

| Framework | Return / yr | Sharpe | Worst drop | Invested | 2016–19 | 2020–22 | 2023–26 | Moves with CAN SLIM (1 = same) |
|---|---|---|---|---|---|---|---|---|
| **CAN SLIM (current)** | **28.9%** | **1.42** | **−17.9%** | 47% | 15.4% | 38.0% | 36.9% | 1.00 |
| Minervini trend template | 21.2% | 0.64 | −45.2% | 75% | 7.1% | 57.5% | 11.7% | 0.56 |
| Peter Lynch (GARP) | 14.7% | 0.44 | −44.8% | 85% | 6.4% | 13.6% | 24.9% | 0.51 |
| Benjamin Graham (defensive) | 12.7% | 0.85 | −14.6% | 25% | 4.8% | 14.3% | 20.1% | 0.39 |
| QGLP-style | 11.9% | 0.43 | −30.4% | 60% | 3.1% | 17.8% | 16.7% | 0.56 |
| Nifty 500 (buy and hold) | 11.8% | 0.36 | −38.3% | 100% | 10.2% | 16.3% | 9.9% | — |
| Magic Formula | 10.7% | 0.24 | −56.3% | 97% | 3.3% | 17.7% | 12.6% | 0.47 |
| Weinstein stage analysis | 9.7% | 0.17 | −47.4% | 66% | −0.2% | 2.6% | 27.6% | 0.45 |
| Coffee Can | 7.5% | 0.25 | −12.5% | 21% | 3.9% | 9.1% | 10.1% | 0.36 |

**Reading it.**
- CAN SLIM's edge comes from combining strong earnings with strong price action and a market filter; frameworks with only one of those (pure value, pure trend) did much worse here.
- Minervini's published trend template without his earnings and base rules is mostly momentum: one great period (2020–22), deep drops.
- Graham and Coffee Can rarely find enough stocks (median 5 and 4 a week), so they sat in cash most of the time; Graham's low drop comes partly from that.
- Graham is the least correlated with CAN SLIM and has a CAN SLIM-like worst drop, so it is the obvious candidate to test for CAN SLIM's idle cash (CAN SLIM is invested only 47% of the time). Not tested yet.

**Checks done.**
- Look-ahead check: on 2021-02-01, scores computed with price data cut at that date equal scores computed with all data, for all seven (0 differences).
- Independent review: a separate agent read the code against the plain-English rules. It found no look-ahead and no unit errors, and one edge-case bug (yearly growth across gaps in quarterly data), which was fixed before these numbers.
- CAN SLIM's result here (28.9%/yr, 2016–26) uses the same simulator as earlier tests (24.7%/yr for 2016–22).

**Caveats.**
- Market cap on old dates uses today's share count × the adjusted price.
- ROCE, ROE, balance sheet and dividend history start in FY2015, so in early years the "10-year" checks on those items use the years available (at least 3).
- Coffee Can allows one year below 10% sales growth (the original rule is 10 of 10; on NSE the COVID year leaves 1–2 stocks).
- Financials are excluded from Coffee Can, Magic Formula, QGLP, Lynch and Graham (their debt and capital aren't comparable).
- Prices cover stocks listed today (survivorship), which flatters all frameworks equally.
