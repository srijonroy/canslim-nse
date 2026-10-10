---
title: What moves NSE stocks: 22 event types tested
date: 2026-10-10
status: Research only
tags: corporate actions, insiders, promoters, earnings, red flags, timing
takeaway: Few events give an edge AFTER the news. The ones that held in both periods: credit-rating upgrades (+8% to +14% vs peers over 12 months), insider buying (+3% to +4%), strong results the market liked (+2% to +5%). Clear red flags in both periods: tender-offer buybacks (−3% to −14%), CFO resignations (−6% to −8%), exchange price/volume queries (−3% to −6%), QIPs (−4%), bulk-deal buying by individuals/companies (−5% to −9%). For bonus issues, splits and index inclusion, the move comes BEFORE the news.
source: canslim/eventtests.py, canslim/eventstudy.py, canslim/events_dl.py, canslim/indexchanges.py, data/research/events/
---
**Method.** Every event 2016–2026 for stocks in our price data. Day 0 = when the news became public (NSE announcement time, insider-trade disclosure, result date). The "buy" is the close the day after (2 days after for results). Every return is compared with the **median stock of the same market-cap size over the same dates**. The table shows the median 12-month result vs peers and, in brackets, the share of stocks that beat their peers. 50% = no edge.

| Event | Events | Before the news (3m) | 12m after, 2016–22 | 12m after, 2023–26 | Verdict |
|---|---|---|---|---|---|
| Credit rating **upgrade** | 454 | +6% | **+8.3% (58%)** | **+14.0% (60%)** | Positive in both |
| Director / executive **buys** in the market | 910 | −1% | +4.3% (55%) | +4.4% (54%) | Small, consistent |
| Promoter **buys** in the market | 3,069 | −2% | +3.7% (54%) | +3.0% (53%) | Small, consistent |
| Profit growth >25% **and** price reaction > +5% on results | 1,840 | +7% | +2.1% (52%), 6m +2.8% | +5.3% (56%) | Small, consistent |
| Stock split (board approval) | 353 | **+11–14%** | +2.8% (53%), 6m +5.0% | −0.4% (50%) | Move is before the news |
| Bonus issue (board approval) | 405 | **+11–16%** | −1.9% (49%) | −5.4% (46%) | Move is before; lags after |
| Index inclusion (Nifty 50 … Smallcap 50) | 1,869 | +3% | −0.6% (49%) | −1.1% (48%) | No edge after the news |
| Index exclusion | 1,896 | −2% | 0.0% (50%) | −3.1% (46%) | Small rebound after leaving, 2016–22 only |
| Preferential issue (all) | 782 | +4–9% | −5.6% (44%) | +0.1% (50%) | No edge overall (promoter-funded ones looked better in 2023–26, see separate finding) |
| Promoter **sells** in the market | 2,072 | +3–4% | −0.5% (49%) | −0.6% (49%) | Neutral |
| Pledge created by promoter | 870 | −2% | −4.5% (46%) | +10.8% (57%) | Mixed |
| Pledge released | 799 | 0% | −5.4% (46%) | +5.6% (56%) | Mixed |
| **Pledge invoked** (lender took the shares) | 289 | −5% | **−13.4% (36%)** | +0.3% (52%) | Red flag in 2016–22 |
| **QIP** (share sale to institutions) | 420 | +7–9% | −4.0% (46%) | −4.3% (44%) | Red flag, both |
| **Buyback, tender offer** | 276 | +5–6% | −2.6% (47%), 6m −5.1% (37%) | **−14.2% (32%)** | Red flag, both |
| **CFO resigns** | 226 | 0% | **−8.1% (43%)** | **−6.0% (40%)** | Red flag, both |
| **Exchange query** on unusual price/volume | 5,768 | +5–8% | −6.4% (44%) | −3.3% (46%) | Red flag, both (micro caps −6.5%) |
| Statutory auditor resigns | 223 | 0% | +11.0% (57%), only 46 events | +0.5% (51%) | No clear effect (rare before SEBI's 2019 rules) |
| Credit rating downgrade | 60 | −5% | +1.4% (53%) | (5 events) | Too few |
| Demerger | 36 | | | | Too few clean cases |
| Bulk deal **buy by a fund** | 1,161 | +3% | +2.1% (53%) | +0.4% (51%) | No edge |
| Bulk deal **buy by an individual / company** | 4,354 | +2–4% | −4.5% (47%) | −6.8 to −8.6% (41–43%) | Red flag: bulk-deal trading marks speculative stocks (their bulk *sells* lag too) |

**How the events were found (no LLM in the pipeline).** Text rules on 1.48 million NSE announcements (2012–2026), 330,000 insider-trade disclosures, the corporate-actions list, 118,000+ bulk deals (one-sided clients only) and NSE Indices press releases. A Haiku model then checked 20 random event starts per type. Rules that scored under 80% (buyback, bonus, split, demerger) were fixed by anchoring each event to a real corporate action. Other rule accuracy: CFO 89%, auditor 95%, ratings 90–95%, exchange queries 100%, QIP 50% (often a later step, so QIP dates can be a little late).

**What it means for us**
- **For buying:** nothing here is strong enough to be a buy rule. Rating upgrades and insider buying are worth showing as supporting evidence next to a CAN SLIM pick.
- **For warnings:** tender buybacks, CFO resignations, exchange price/volume queries, QIPs and pledge invocations are worth flagging on any holding.
- **About the news:** for bonus issues, splits, preferential issues and index inclusion, most of the move happens before the announcement. Buying on that news is late.

**Caveats.** Medians vs same-size peers. Small event counts in some rows. Only stocks we hold prices for (about 2,200 NSE stocks; survivors only). Nothing tested as a portfolio yet.
