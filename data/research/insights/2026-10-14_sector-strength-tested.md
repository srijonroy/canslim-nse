---
title: Strong sectors on NSE: what identifies them and how long they last
date: 2026-10-14
status: Research only
tags: sectors, industry groups, momentum, persistence, CAN SLIM
takeaway: Plain group strength (average RS of a group's stocks) is the best simple way to tell which sectors are strong: the top fifth of groups beat the bottom fifth by about 4% over the next 3 months in 2016–19, 2020–22 and 2023–26. Fancier measures (rising fast, earnings breadth, big caps leading small caps) add nothing. Strength is short-lived: a group stays in the top 20% for a median 2 months, and only ~15% last 6 months. Joining the top 20% doesn't reliably pay afterwards, but dropping out is a consistent warning (−1% to −5% vs the market over the next 3–12 months). Adding sector strength to CAN SLIM's ranking barely changes results, because the pool is only ~4 stocks.
source: canslim/sectortest.py, data/tune/sectortest/ (ic.csv, rising_groups.csv, spells_*.csv, decay_*.csv, portfolio.csv); literature: 2026-10-14_picking-sectors-research.md
---
**Method.** Groups = Screener basic industries with at least 5 stocks in the liquid universe on the date (about 23 groups on a typical date). Group return = equal-weight average of its stocks minus the universe average. Sampled every 4 weeks, June 2015 – Sept 2026. Decisions on 2016–22; 2023–26 shown as a check.

### Which measures identify strong sectors (top 20% of groups minus bottom 20%, next 3 months)

| Measure | 2016–19 | 2020–22 | 2023–26 | Verdict |
|---|---|---|---|---|
| Group strength (average RS percentile) | +4.2% | +3.5% | +4.7% | Works in every period |
| Group near its 52-week high | +3.7% | +3.9% | +2.0% | Good, weaker lately |
| Share of members within 10% of their high | +4.8% | +2.7% | +3.6% | About as good as group strength |
| Share of members above 200-day average | +4.5% | +4.2% | +1.3% | Fades lately |
| 12→1 month return | +3.3% | +3.0% | +5.1% | Similar, slightly weaker |
| 12→7 month return | −0.7% | +1.7% | +4.9% | Fails in 2016–19 |
| Rising fast (strength change over 3 months) | +1.2% | +1.7% | +0.5% | Weak |
| Earnings breadth (profit +25% and margin up) | −0.5% | +1.8% | +2.8% | Fails in the decision period |
| 3-year return (reversal) | −1.0% | +2.2% | +4.4% | No reversal; recent winners kept winning |
| Big caps lead small caps | −1.0% | −2.4% | −2.0% | Doesn't work here |
| Combined score | +2.5% | +2.9% | +4.2% | No better than group strength |

Over 6 months the group-strength gap is +6.5 / +5.6 / +8.9%.

### How long a sector stays strong (top 20% by group strength)

| Stretches starting in | Count | Median length | Lasted 3m+ | 6m+ | 12m+ |
|---|---|---|---|---|---|
| 2016–19 | 33 | 2 months | 48% | 18% | 6% |
| 2020–22 | 63 | 2 months | 35% | 14% | 6% |
| 2023–26 | 134 (12 still running) | 2 months | 43% | 14% | 4% |

### What happens next (median excess return of the group)

| Event | Period | 3 months | 6 months | 12 months |
|---|---|---|---|---|
| Entered the top 20% | 2016–19 | +4.1% | +0.8% | +2.8% |
| | 2020–22 | 0.0% | +3.6% | −3.2% |
| | 2023–26 | −0.8% | −2.1% | −3.1% |
| Dropped out of the top 20% | 2016–19 | −2.0% | −4.7% | −3.9% |
| | 2020–22 | −2.4% | −1.7% | −4.1% |
| | 2023–26 | −1.1% | −2.6% | −3.0% |

Groups that jumped from the bottom half into the top 20% within 3 months (12 / 8 / 52 cases) did no better than groups that were already strong: catching the turn doesn't pay.

### Combined with CAN SLIM (2016–22, decision bar as in booktest.py)

| Variant | CAGR | Sharpe | 2016–19 | 2020–22 | Max drop | 2023–26 Sharpe (check) |
|---|---|---|---|---|---|---|
| Current system | 24.7% | 1.37 | 0.85 | 1.93 | −17.9% | 1.60 |
| Rank by RS + 0.5 × group strength | 25.5% | 1.41 | 0.86 | 2.02 | −17.9% | 1.65 |
| Rank by RS + 0.5 × combined score | 25.1% | 1.38 | 0.86 | 1.95 | −17.9% | 1.92 |
| Rank by RS + 1.0 × combined score | 25.0% | 1.37 | 0.86 | 1.95 | −17.9% | 1.86 |
| Separate "sector leaders" list | 13.6% | 0.47 | −0.15 | 0.92 | −34.3% | 0.96 |

None passes (2016–19 improves by only +0.01, the bar is +0.03 in both halves). The tilt can't do much because only ~4 stocks pass CAN SLIM's rules on a typical week. Buying the strongest stocks in the strongest groups without CAN SLIM's earnings rules is much worse.

**Checks.** An independent code review (separate agent) found that strong stretches still running at the end of the data had been dropped; they are now counted (table above), which did not change the medians. The "12→7 month" signal actually measures 12→6 months.

**Follow-ups done the same day.** Broader industries (58, `--level3`): group strength still works (+4.5 / +3.1 / +3.2% per 3m), strong groups last a median 1.5–3 months, but the "dropped out" warning only shows in 2020–22. As a rule inside CAN SLIM (`warntest.py`): "group dropped out of the top 20% in the last 13 weeks" → no buy / sell passed the 2016–22 bar (Sharpe 1.44 vs 1.37, worst drop −16.2% vs −17.9%) but was worse in 2023–26 (1.51 vs 1.60), so it is shown as an amber warning on holdings, not a rule. The sector radar is now in the daily report and on the app page "Sectors".

**Caveats.** Only ~23 groups qualify per date, so the per-measure statistics are weak (t around 1–2); the direction is what's consistent. Industry labels are today's (not point-in-time), and the price data covers currently listed stocks only.
