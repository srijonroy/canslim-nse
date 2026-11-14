---
title: Can a strong AI model pick buy points from a chart alone? Blind test on 2024
date: 2026-11-14
status: Tested, not adopted (narrow miss; second year needed)
tags: AI, chart reading, blind test, entry, CAN SLIM
takeaway: Claude Fable 5.2 read 287 anonymised charts from 2024 (no names, no dates, rescaled prices). On 204 random stocks its BUY calls beat its AVOID calls by 4.4 points of 3-month return over the index (7.3% vs 2.9%), with WAIT in between. That missed the bar set beforehand by a hair (2.8 points in the first half-year against 3 required; 4.7 in the second), and with only 45 BUY calls the gap is within what chance produces. Its confidence score told nothing. On the system's own 83 buys, the ones it called BUY did better over a fixed 3 months (12.3% vs 3.4% over the index) but not under the system's actual exits (3.9% vs 6.3% per trade). Promising direction, not proof.
source: canslim/blindtest.py, data/tune/blindtest/ (key.csv, answers_fable.jsonl, scored_fable.csv)
---
**Why tested.** The question was whether a capable model can find good buy points from the chart, where coded chart rules (pivots, volume surges) added nothing. An earlier blind test on US500 intraday setups with a weaker model failed.

**Method.** For each chart the model saw one year of daily candles up to the decision date, the 50- and 200-day averages, volume and a relative-strength line, with the name and dates removed and prices rescaled to start at 100. It answered BUY, WAIT or AVOID with a confidence of 1–5. It ran in a bare folder holding only the images. Outcomes were kept in a separate key: return over the next 63 trading days from the next open, minus the Nifty 500's, and whether +20% came before −8% within 126 days.

Samples: 204 random stock-dates (17 liquid stocks on the first scan date of each month of 2024) and all 83 buys the current system made in 2024 (50 different stocks).

Bar, fixed before running: (1) on the random charts BUY beats AVOID by at least 3 points of average excess return in both half-years; (2) on the system's buys, BUY does no worse than the rest.

### Random charts

| Model's call | Charts | Avg 3-month return over index | Median | Beat the index | +20% before −8% |
|---|---|---|---|---|---|
| BUY | 45 | 7.3% | 3.7% | 58% | 38% |
| WAIT | 77 | 5.4% | −1.7% | 45% | 30% |
| AVOID | 82 | 2.9% | 1.3% | 55% | 30% |

| Half-year | BUY | WAIT | AVOID | BUY minus AVOID |
|---|---|---|---|---|
| Jan–Jun 2024 | 9.3% (27) | 7.6% (36) | 6.5% (39) | 2.8 points |
| Jul–Dec 2024 | 4.4% (18) | 3.5% (41) | −0.3% (43) | 4.7 points |

- BUY minus AVOID over the year: 4.4 points, t-statistic 1.0. A gap this size appears by chance about one time in three with samples this small.
- Confidence did not help: BUY calls at confidence 3 averaged 8.3%, at confidence 4 only 5.0%.
- The simple rule (uptrend, within 15% of the high, relative strength in the top 20%) showed no edge on these charts: 4.6% for the 28 that passed against 4.8% for the rest.

### The system's own buys in 2024

| Model's call | Buys | Avg 3-month return over index | System's actual result per trade (avg / median) |
|---|---|---|---|
| BUY | 58 | 12.3% | +3.9% / −3.5% |
| WAIT | 25 | 3.4% | +6.3% / −0.1% |

Held for a fixed 3 months, the buys the model liked did better (t-statistic 1.4; several of the 83 are repeat buys of the same stock, so they are not independent). Under the system's own exits, which sell after a median of 23 days, the order reverses.

**Verdict.** Part 1 of the bar failed narrowly (2.8 against 3 in the first half-year); part 2 passed on the fixed 3-month measure. Not adopted. The ordering BUY above WAIT above AVOID held in both half-years, so the result is worth a second year in a different market, with the bar unchanged, before drawing any conclusion.

**Caveats.** One year, one model, one chart layout. 2024 had a strong first half and a falling second half. The charts are anonymised, but the model's training does include this period.
