---
title: Can a strong AI model pick buy points from a chart alone? Blind tests on 2024 and 2022
date: 2026-11-14
status: Tested on two years, not adopted
tags: AI, chart reading, blind test, entry, CAN SLIM
takeaway: Claude Fable 5.2 read 540 anonymised charts (no names, no dates, rescaled prices) from 2024 and 2022. On random stocks its BUY calls beat its AVOID calls by 4.4 points of 3-month return over the index in 2024 and 2.1 points in 2022, missing the bar set beforehand in both years (3 points in each half-year). Over both years the gap is 3.3 points on 90 BUY calls, still within what chance produces. On the system's own buys the model added nothing: the buys it liked did worse than the ones it told us to wait on under the system's exits in both years (1.6% vs 6.2% per trade). Not adopted. The one steady pattern is that its AVOID calls were the weakest group in both years.
source: canslim/blindtest.py, data/tune/blindtest/2024 and /2022 (key.csv, answers_fable.jsonl, scored_fable.csv)
---
**Why tested.** The question was whether a capable model can find good buy points from the chart, where coded chart rules (pivots, volume surges) added nothing. An earlier blind test on US500 intraday setups with a weaker model failed.

**Method.** For each chart the model saw one year of daily candles up to the decision date, the 50- and 200-day averages, volume and a relative-strength line, with the name and dates removed and prices rescaled to start at 100. It answered BUY, WAIT or AVOID with a confidence of 1–5. It ran in a bare folder holding only the images. Outcomes were kept in a separate key: return over the next 63 trading days from the next open, minus the Nifty 500's, and whether +20% came before −8% within 126 days.

Samples: 204 random stock-dates (17 liquid stocks on the first scan date of each month of 2024) and all 83 buys the current system made in 2024 (50 different stocks).

Bar, fixed before running: (1) on the random charts BUY beats AVOID by at least 3 points of average excess return in both half-years; (2) on the system's buys, BUY does no worse than the rest.

## 2024

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

**Verdict for 2024.** Part 1 of the bar failed narrowly (2.8 against 3 in the first half-year); part 2 passed on the fixed 3-month measure. Not adopted. The ordering BUY above WAIT above AVOID held in both half-years, so the result is worth a second year in a different market, with the bar unchanged, before drawing any conclusion.

**Caveats.** One year, one model, one chart layout. 2024 had a strong first half and a falling second half. The charts are anonymised, but the model's training does include this period.

## 2022 (second year, same bar, run the same day)

2022 was a choppy, falling market. 253 charts: 204 random stock-dates and the system's 49 buys.

| Model's call | Charts | Avg 3-month return over index | Median | Beat the index | +20% before −8% |
|---|---|---|---|---|---|
| BUY | 45 | −0.3% | −1.8% | 44% | 31% |
| WAIT | 70 | 0.5% | −3.9% | 41% | 27% |
| AVOID | 89 | −2.4% | −3.0% | 42% | 22% |

| Half-year | BUY | WAIT | AVOID | BUY minus AVOID |
|---|---|---|---|---|
| Jan–Jun 2022 | −2.2% (27) | 0.1% (30) | −3.0% (45) | 0.8 points |
| Jul–Dec 2022 | 2.6% (18) | 0.8% (40) | −1.7% (44) | 4.3 points |

- BUY minus AVOID over the year: 2.1 points, t-statistic 0.7. WAIT did better than BUY.
- The simple rule did better than the model's BUY calls this year: 1.2% for the 29 charts that passed against −1.3% for the rest, and 45% of them reached +20% before −8%.

| Model's call on the system's 2022 buys | Buys | Avg 3-month return over index | System's actual result per trade (avg / median) |
|---|---|---|---|
| BUY | 38 | −3.0% | −1.9% / −3.9% |
| WAIT | 11 | 3.6% | +6.0% / +7.5% |

Both parts of the bar failed in 2022.

## Both years together

| | BUY | WAIT | AVOID |
|---|---|---|---|
| Random charts (408): avg 3-month return over index | 3.5% (90) | 3.1% (147) | 0.2% (171) |
| System's buys (132): system's actual result per trade | 1.6% (96) | 6.2% (36) | – |

- Random charts, BUY minus AVOID: 3.3 points, t-statistic 1.3. BUY against everything else: 2.0 points, t-statistic 0.8.
- The model does not separate BUY from WAIT. What it marks AVOID did worst in both years.
- On stocks the system already chose, the model's preference did not help in either year under the system's exits.

**Final verdict.** The bar failed in both years. A strong model reading anonymised charts does not give a reliable buy signal, and adds nothing on top of the system's own picks. Not adopted. If revisited, the one lead is the AVOID call as a warning, which would need its own test on fresh years.
