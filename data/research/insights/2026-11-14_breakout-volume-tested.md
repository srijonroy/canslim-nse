---
title: Breakout volume as a confirmer on top of the CAN SLIM rules
date: 2026-11-14
status: Tested, not adopted
tags: volume, breakout, techno-funda, entry, CAN SLIM
takeaway: Requiring a volume surge before buying a stock that already passes the rules made results worse in 2016–22 (return 15–21% a year vs 24.7%, Sharpe 1.04–1.26 vs 1.37). The win rate did not move (44–46%), so the surge did not pick better trades; it only meant fewer trades and more idle cash. Among the system's own 230 trades, those bought after a volume surge had a higher average gain but the same median, and the 2x and 3x results flipped between 2016–19 and 2020–22. Volume adds little once a stock is already near its high with top relative strength.
source: canslim/voltest.py, data/tune/voltest/ (results.csv, trade_split.csv)
---
**Why tested.** An investor's presentation picks stocks where fundamentals and a high-volume breakout agree ("techno-funda"). The system checks fundamentals, trend, nearness to the 52-week high and relative strength, but not volume.

**Method.** A volume day = close up at least 2% on volume at least k times the prior 50-day average. A passing stock may be bought only if it had one recently. 2016–22 only; bar fixed before running (Sharpe +0.03 in both halves, worst drop within 3 points, large-cap Sharpe not lower).

| Variant | Return / yr | Sharpe | Sharpe 16–19 | Sharpe 20–22 | Worst drop | Invested | Win rate |
|---|---|---|---|---|---|---|---|
| Current rules | 24.7% | 1.37 | 0.85 | 1.93 | −17.9% | 39% | 44% |
| 2x volume within 10 days | 20.4% | 1.21 | 0.58 | 1.84 | −15.5% | 30% | 45% |
| 3x volume within 20 days | 21.0% | 1.26 | 0.68 | 1.89 | −15.6% | 29% | 44% |
| 5x volume within 20 days | 15.5% | 1.04 | 1.05 | 1.12 | −12.2% | 18% | 46% |

**The current system's own trades, split by a volume day before the buy (2016–22, 230 trades)**

| Volume day | Trades with / without | Average gain with / without | Median with / without |
|---|---|---|---|
| 2x within 10 days | 99 / 131 | 7.0% / 6.3% | −0.9% / −1.7% |
| 3x within 20 days | 97 / 133 | 8.1% / 5.5% | −1.8% / −0.9% |
| 5x within 20 days | 41 / 189 | 10.0% / 5.9% | −1.0% / −0.9% |

By half: 2x was worse in 2016–19 (0.4% vs 7.8%) and better in 2020–22 (12.1% vs 4.9%); 3x was better in 2016–19 (8.4% vs 1.7%) and no better in 2020–22 (7.8% vs 8.3%); 5x was better in both (12.0% vs 3.6%, 8.9% vs 7.9%) on only 14 and 27 trades.

**Reading it.** The higher averages come from a few large winners, not from more winning trades. The 5x result is the only consistent one and rests on 41 trades, too few to act on.

**Related, already in the report.** The event study of 10 Oct found that strong results followed by a positive price reaction did well in both periods. That is the earnings monitor's "price confirming" list.
