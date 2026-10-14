---
title: How to pick sectors: what the research says
date: 2026-10-14
status: Literature review, not yet tested on NSE
tags: sectors, industry groups, momentum, rotation, breadth, flows, issuance
takeaway: Sector strength persists. Industries that have been strong over the past 6–12 months, and industries trading near their 52-week high, keep outperforming for months (US, 37 other countries, India 2000–13). Our own NSE data agrees: group strength predicts the next 3 months in 2015–19, 2020–22 and 2023–26. What does NOT survive testing: business-cycle sector rotation (only works with perfect hindsight), FPI sector flows (no evidence they predict), and RRG charts (no independent test). Promising add-ons: big companies in a group move first and small ones follow; industry-wide earnings news spreads slowly; commodity price moves lead related industries by up to ~6 weeks. Warning signs: groups issuing lots of new shares (IPOs, QIPs) do worse afterwards, and 3–5 year winners tend to reverse.
source: Web literature search 2026-10-14 (papers listed below); data/research/factor_stats_63d.csv for our own group-strength numbers
---
**Question.** Can we tell which sectors will lead next, and use that alongside CAN SLIM?

**Short answer.** We can't call turning points from the economy, but a sector that has *started* to lead tends to keep leading for months, and several measurable things help spot it earlier or rank it better. "Emerging" in practice means catching a group 1–3 months into its move.

### Strong evidence (several studies, many countries)

| Signal | What the research found | Source |
|---|---|---|
| Group strength over 6–12 months | Strong industries keep outperforming. Industry momentum explains much of stock momentum and stays profitable after controls. Found in the US and 37 other countries; India-specific study (2000–13) finds strong sector momentum on NSE. | Moskowitz & Grinblatt 1999; Garg & Varshney 2015 (India) |
| Use months 12→7 more than the last month | The older part of the past year predicts better than the most recent months, especially in large liquid stocks. | Novy-Marx 2012 |
| Group near its 52-week high | Nearness to the 52-week high beats past returns as a predictor, and works at industry level (investors anchor and under-react to industry news). Profitable in 18 of 20 markets, though thin after costs in many. | George & Hwang 2004; Pacific-Basin Finance J. 2015 |
| Long-run reversal | Industries that lost over 3–5 years beat winning industries over the following 5 years. Useful as a warning on very extended groups, not as a buy signal. | Wu & Mazouz 2016; De Bondt & Thaler 1985 |
| Heavy new share issuance | Industries issuing the most new shares underperform the least-issuing by ~0.58%/month (68 markets, 1976–2022). Matches our own NSE finding that QIPs are followed by −4%. | Long, Chiah, Zaremba & Umar 2023 |

### Moderate evidence (good studies, fewer replications)

| Signal | Finding | Source |
|---|---|---|
| Big firms lead small firms within an industry | Small companies react late to industry news that the large ones already priced in. Stronger in neglected industries. Relevant to our small-cap focus. | Hou 2007 |
| Customer → supplier industries | Returns of customer industries predict supplier industries (and competitors) because information spreads slowly. Needs a supply-chain map. | Menzly & Ozbas 2010; Schlag & Zeng 2019 |
| Industry earnings news | A company's results move its peers, and the drift lasts longer when peers' later results confirm it. | Kovacs 2016; Thomas & Zhang 2008 |
| Commodity prices → industries | Commodity price changes forecast 40 of 49 US industry returns up to ~6 weeks ahead (gold/metals, oil), modest out of sample. | Valcarcel, Vivian & Wohar 2017 |
| Fixing momentum crashes | Scaling by recent volatility roughly doubles the Sharpe ratio of industry momentum in one study; residual (stock-specific) momentum improves risk-adjusted returns. | Several, see Quantpedia summary |

### Weak or no evidence

| Idea | Why it's weak |
|---|---|
| Business-cycle sector rotation | Worked only with perfect knowledge of the cycle; with realistic timing and costs the edge disappears (Molchanov & Stangl 2023, reversing Stangl et al. 2009). |
| FPI sector flows (NSDL fortnightly) | No published test shows they predict sector returns; practitioners note the top sector changes every fortnight. |
| Relative Rotation Graphs (RRG) | Only vendor commentary; no independent backtest beyond plain relative strength. |
| Sector breadth (% above 200-day average) | Widely used by practitioners (Weinstein, O'Neil) but no rigorous published test. Worth testing ourselves. |
| Analyst upgrades by industry | Follow sector moves rather than lead them (Boni & Womack 2006). We have no estimate data anyway. |
| Retail fund flows | Money chasing sectors predicts *low* long-run returns (Frazzini & Lamont). |

### Our own NSE numbers already on file
Group strength (average RS of a Screener industry's stocks) as a predictor of each stock's next 3 months: IC 0.05 / 0.04 / 0.057 in 2015–19 / 2020–22 / 2023–26; top fifth beat bottom fifth by 3.0 / 3.6 / 4.6% per quarter. Small but consistent. Earlier test: requiring CAN SLIM picks to be in a top-20% group failed because the pool collapsed (book audit, 2026-10-02). Using group strength as a ranking tilt or for a separate list has not been tested.

### Papers
- Moskowitz & Grinblatt (1999), Do Industries Explain Momentum? J. Finance.
- Garg & Varshney (2015), Momentum Effect in Indian Stock Market: A Sectoral Study, Global Business Review.
- Novy-Marx (2012), Is Momentum Really Momentum? J. Financial Economics.
- George & Hwang (2004), The 52-Week High and Momentum Investing, J. Finance; Industry information and the 52-week high effect (2015), Pacific-Basin Finance J.
- Hou (2007), Industry Information Diffusion and the Lead-Lag Effect in Stock Returns, Review of Financial Studies.
- Menzly & Ozbas (2010), Market Segmentation and Cross-Predictability of Returns, J. Finance.
- Hong, Torous & Valkanov (2007), Do Industries Lead Stock Markets? J. Financial Economics (challenged by Tse 2015).
- Stangl, Jacobsen & Visaltanachoti (2009); Molchanov & Stangl (2023), The Myth of Business Cycle Sector Rotation.
- Long, Chiah, Zaremba & Umar (2023), Composite equity issuance and the cross-section of country and industry returns, Applied Economics.
- Wu & Mazouz (2016), Long-term industry reversals, J. Banking & Finance.
- Valcarcel, Vivian & Wohar (2017), Predictability and underreaction in industry-level returns: evidence from commodity markets, J. Commodity Markets.
- Kovacs (2016), Contemporary Accounting Research; Boni & Womack (2006), JFQA; Frazzini & Lamont (2008), Dumb Money, JFE.
- Faber (2010), Relative Strength Strategies for Investing (SSRN 1585517).
