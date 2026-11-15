---
title: Can the backtest's orders be filled at circuit limits?
date: 2026-11-15
status: Tested, not adopted
tags: realism, circuit limits, execution, small caps, evidence
takeaway: 2016-22: 26.8% a year with every order filled, 26.7% if whole-day circuit locks block orders, 26.7% in the pessimistic case; 2023+: 34.6% a year with every order filled, 33.8% if whole-day circuit locks block orders, 34.2% in the pessimistic case. Circuit locks barely matter for this system - the backtest numbers stand.
source: canslim/experiments/circuit_locks.py, data/tune/circuit-locks/results.csv
---
**Question.** The backtest assumes every buy and sell fills at the next open. Small caps often lock at their upper circuit on breakouts and lower circuit on bad news. How much of the result depends on fills that could not happen?

**Method.** Same rules and dates. A day is 'locked' when high equals low (one price all day) with trading volume; up-locked days block buys, down-locked days block sells (retried at the next open). The pessimistic version also blocks opens at the day's extreme after a gap of 4.9% or more.

| period | variant | CAGR % | Sharpe | maxDD % | invested % | trades/yr | big Sharpe | Sharpe 16-19 | CAGR 16-19 | Sharpe 20-22 | CAGR 20-22 | passes bar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016-22 | live backtest (fills always) | 26.8 | 1.42 | -20.7 | 43.0 | 38.0 | 0.11 | 1.05 | 18.9 | 1.85 | 37.9 | False |
| 2023+ | live backtest (fills always) | 34.6 | 1.42 | -14.3 | 63.0 | 57.0 | 1.59 |  |  |  |  | False |
| 2016-22 | strict locks | 26.7 | 1.41 | -21.9 | 43.0 | 38.0 | 0.09 | 1.02 | 18.4 | 1.86 | 38.4 | False |
| 2023+ | strict locks | 33.8 | 1.39 | -14.3 | 63.0 | 57.0 | 1.59 |  |  |  |  | False |
| 2016-22 | pessimistic locks | 26.7 | 1.42 | -21.3 | 43.0 | 38.0 | 0.1 | 1.04 | 18.7 | 1.86 | 38.0 | False |
| 2023+ | pessimistic locks | 34.2 | 1.42 | -14.3 | 63.0 | 57.0 | 1.58 |  |  |  |  | False |

**Decision.** Circuit locks barely matter for this system - the backtest numbers stand
