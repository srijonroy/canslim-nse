---
title: Can the backtest's orders be filled at circuit limits?
date: 2026-11-15
status: Tested, not adopted
tags: realism, circuit limits, execution, small caps, evidence
takeaway: 2016-22: 25.6% a year with every order filled, 25.6% if whole-day circuit locks block orders, 25.6% in the pessimistic case; 2023+: 34.4% a year with every order filled, 33.6% if whole-day circuit locks block orders, 33.8% in the pessimistic case. Circuit locks barely matter for this system - the backtest numbers stand.
source: canslim/experiments/circuit_locks.py, data/tune/circuit-locks/results.csv
---
**Question.** The backtest assumes every buy and sell fills at the next open. Small caps often lock at their upper circuit on breakouts and lower circuit on bad news. How much of the result depends on fills that could not happen?

**Method.** Same rules and dates. A day is 'locked' when high equals low (one price all day) with trading volume; up-locked days block buys, down-locked days block sells (retried at the next open). The pessimistic version also blocks opens at the day's extreme after a gap of 4.9% or more.

| period | variant | CAGR % | Sharpe | maxDD % | invested % | trades/yr | big Sharpe | Sharpe 16-19 | CAGR 16-19 | Sharpe 20-22 | CAGR 20-22 | passes bar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016-22 | live backtest (fills always) | 25.6 | 1.35 | -21.1 | 44.0 | 39.0 | 0.03 | 1.01 | 18.4 | 1.73 | 35.8 | False |
| 2023+ | live backtest (fills always) | 34.4 | 1.41 | -14.2 | 63.0 | 56.0 | 1.6 |  |  |  |  | False |
| 2016-22 | strict locks | 25.6 | 1.34 | -22.1 | 44.0 | 39.0 | 0.01 | 0.98 | 18.0 | 1.75 | 36.2 | False |
| 2023+ | strict locks | 33.6 | 1.38 | -14.2 | 63.0 | 56.0 | 1.6 |  |  |  |  | False |
| 2016-22 | pessimistic locks | 25.6 | 1.34 | -21.6 | 44.0 | 39.0 | 0.02 | 1.0 | 18.2 | 1.74 | 35.9 | False |
| 2023+ | pessimistic locks | 33.8 | 1.39 | -14.2 | 63.0 | 56.0 | 1.6 |  |  |  |  | False |

**Decision.** Circuit locks barely matter for this system - the backtest numbers stand
