# CAN SLIM scanner — project notes

Daily NSE scan based on William O'Neil's *How to Make Money in Stocks* (4th ed.), with rules checked against NSE history from 2014 on.
**Research only. Nothing here places orders.**

---

## How to use it

| What | How |
|---|---|
| Daily scan | Runs automatically Mon–Sat 18:30 (`run_daily.bat`, Windows Task Scheduler "CANSLIM Daily Scan"): prices → rules → report → database → paper portfolio → **automatic research briefs**. Fyers logs in by TOTP when `.env` has FYERS_CLIENT_ID / FYERS_PIN / FYERS_TOTP_SECRET; otherwise it falls back to approval in Chrome. |
| Automatic briefs | `python -m canslim.autobrief` (run by the daily script): briefs names on the CAN SLIM list that have no brief, a brief older than 90 days, or new results since the brief. At most 3 a day, highest rank first. Runs Claude Code headless (`claude -p`, model Sonnet, set `CANSLIM_BRIEF_MODEL` to change), allowed only to read/write files and run `python -m canslim.docs`. Log: `brief_runs` table + `data/research/companies/<SYM>/brief_run.log`. |
| Daily report | `data/reports/latest.html` (one copy per day as `YYYY-MM-DD.html`) |
| Tracker app | Double-click `run_app.bat` → opens http://localhost:8501 |
| Database | `data/canslim.db` (SQLite). Written by every daily run. |
| Big-winner study | `data/reports/winners_study.html` |

### Tracker app pages
- **Today**: market state, the CAN SLIM list (new entries and drop-outs vs the previous scan), the emerging list, and the earnings monitor.
- **Insights**: every research finding about the market, newest first, with a one-line takeaway, status (adopted / rejected / research only) and the evidence. One Markdown file per finding in `data/research/insights/` (header: title, date, status, tags, takeaway, source). **Every new test adds a file here.**
- **Holdings**: your positions with a daily traffic light. Add a holding with *why I'm buying* and *I'm wrong if*. Log HOLD / SELL / NOTE with a reason.
- **Stock**: chart with the 50- and 200-day lines, plus every stored day of rule checks and list appearances for any symbol.
- **Paper portfolio**: the system trading its own lists live from 30 Sep 2026 (notional ₹10 lakh, the backtest's rules, fills at the next open). It's compared with the Nifty 500. **This is the clean out-of-sample test.**
- **Watching**: every stock that left the CAN SLIM list or was sold by the paper portfolio in the last 24 months, with where it is now and whether it **qualifies again**, so a later comeback isn't missed.
- **Research**: business briefs and your conviction score (see below).
- **Journal**: every decision, and **whether your overrides beat the rule**.

### Research briefs (no API, no extra cost)
In Claude Code, type **`/brief SYMBOL`**. Claude runs `python -m canslim.docs SYMBOL`, which downloads the last 4 concall transcripts and presentations and the latest annual report from Screener's links into `data/research/companies/SYMBOL/`, and writes `facts.md` from data we already hold. Claude then reads the documents and writes `brief.md`, with a 12-question checklist where every score of 2 cites a source, a guidance tracker (promises vs delivery), red flags, an "I'm wrong if" and scuttlebutt questions.
The app's Research page shows the brief. **You** set the conviction (1–5) with a reason. Conviction is recorded only, not used for position size, until the journal shows it predicts returns.
Skill files: `.claude/skills/brief/` (`SKILL.md` = instructions, `template.md` = structure).

### The traffic light
| Light | Meaning | Tested? |
|---|---|---|
| 🔴 RED | Fails a CAN SLIM rule, or ranks below 30 among passing stocks. This is the system's sell signal. | **Yes.** It beat 9 "hold longer" rules on 2016–22. |
| 🟠 AMBER | Still passes, but a warning is on: rank 21–30, below the 50-day average, 15%+ off the peak since buying, or RS down 15+ points | No, information only |
| 🟢 GREEN | Passes and ranks in the top 20 | — |
| ⚪ GREY | Not in the system's universe (no fundamentals, or too illiquid) | — |

You can override RED with a written reason. The Journal page scores every override (price when the rule said sell vs now).
After 6–12 months that record shows whether your judgment beats the rule.

---

## The system (current)

**Entry rules** (all must pass; tuned on 2016–22, `data/tune/final.json`):
1. Uptrend: price > 50-day > 150-day > 200-day, and the 200-day is rising
2. Within 15% of the 52-week high
3. Quarterly profit growth ≥ 25%
4. Sales growth ≥ 20%, or 2+ strong quarters in a row
5. 3-year profit growth ≥ 15% a year
6. ROE ≥ 20%
7. RS rating ≥ 80
8. Net profit margin up vs a year ago (book rule 6, adopted 2026-10-02)

Ranked by RS. At most 3 per industry. Liquid stocks only.

**Portfolio** (as backtested): 10 stocks; keep a holding while it passes the rules and ranks ≤ 30; **no new buys unless the market is in an uptrend**; no fixed stop-loss; 0.3% cost each way.

**Result 2016–22:** 25.6% a year, worst drop −21.1%, Sharpe 1.34; 2023 to now 34.4%, −14.2%, 1.41 (Nifty 500: about 12% a year). Restated 2026-11-15 on the live Rs 3 Cr floor with NSE-checked result dates; older test-log rows used the Rs 5 Cr cache (24.7% / −17.9% / 1.37) or Screener dates (26.8% / −20.7% / 1.42). The money comes from the filters themselves: random picks from the same passing pool do about as well.

### Other lists in the report
- **Earnings monitor**: fresh results with operating margin up 6+ points, or profit up 50%+ in each of the last two quarters, and the price confirming. Any size, including new listings.
- **Emerging / turnaround** (higher risk): same earnings signals + RS ≥ 80 + uptrend + near the high, with no ROE or 3-year rule. Test 2016–22: 21.9% a year, worst drop −39%.

---

## Test log

Pass/fail bars are written down before each test runs. **All of 2016–2026 has now been looked at.** No clean historical test is left, so the live record in `data/canslim.db` is the real test from here.

| Date | Test | Result | Decision |
|---|---|---|---|
| 2026-09-30 | Book CAN SLIM vs alternatives, walk-forward 2016–26 | Book rules + market filter: 21% a year, worst drop −30% | Adopted |
| 2026-09-30 | Tuning (41 trials on 2016–22, hold-out 2023–26 run once) | ROE ≥ 20 (was 15). Hold-out 38.5% a year, −16% worst drop | Adopted ROE 20 |
| 2026-09-30 | 8% stop-loss; "go to cash" in corrections; learned blend | All hurt on NSE | Rejected |
| 2026-10-01 | Skip stocks up >100% in 6 months (`runup.py`) | Hurt. Those trades did *better* (+8.4% vs +5.8%) | Rejected; shown as "strong momentum" |
| 2026-10-01 | Big-winner study (`winners.py`) | Price strength is the most reliable predictor; margin expansion and 2 strong quarters help in both periods; ML model 49.5% → 21.6% out of sample | Earnings monitor added; ML not used |
| 2026-10-01 | Emerging / turnaround list (`emerging.py`) | 21.9% a year, −39% worst drop; passed the bar for a separate list, not for replacing CAN SLIM | Separate list |
| 2026-10-02 | Let winners run: after +20%/+50%, sell only below the 200-/150-day or 25–30% off the peak (`holdtest.py` B–F) | All worse: Sharpe 0.66–1.00 vs 1.26, worst drop −26 to −30% vs −21%, although the average winner was +45–49% vs +23% | Rejected |
| 2026-10-02 | Re-entry audit (`reentry.py`) | 13 sold stocks later went up 3×+. **11 were bought back**, but only a median 2% of the run was captured (bought and sold repeatedly) | Led to the next test |
| 2026-10-02 | Ride mode only for re-bought stocks (`holdtest.py` G–J) | All worse (best Sharpe 1.02 vs 1.26) | Rejected. Judgment + journal instead |

**Takeaway from the holding tests:** the 10-baggers fall 25–35% several times along the way, and on price data alone those drops look like a breakdown. No mechanical rule kept them without also keeping losers. That's the gap the journal is meant to measure: can your judgment, using what the data can't see, do better?

| 2026-10-02 | Book audit: untested rules from the book's rule list (pp. 424–426), each added on top (`booktest.py`) | **R6 net margin improving passed** (Sharpe 1.37 vs 1.26, both halves better, DD −17.9% vs −21%; 2023–26 check 1.60 vs 1.57). Failed: 2 strong quarters, top industry groups (pool collapses to 1), RS 85, sales acceleration, accumulation, 5 stocks (28% a year but −35% DD), all combined | **R6 adopted** |
| 2026-10-02 | Institutional sponsorship (book rule 14) on BSE shareholding filings from Dec 2015, point-in-time by filing date (`shp.py`, `insttest.py`) | None passed. Institutions count up: Sharpe 1.34; % up: 1.22; count not falling: 1.36 (DD −13.5%). **MF schemes count up**: Sharpe 1.44, DD −8.3%, but CAGR 17.5%, pool of 2, 20–22 only +0.02 and 2023–26 worse (1.37 vs 1.60) | Not adopted |
| 2026-10-06 | Earlier entry (`earlytest.py`): E1 rank by least stretched, E2 fresh qualifiers only, E3 price > rising 200-day + RS 70, E4 earnings-monitor rule | None passed. E1/E2 barely change entry timing (2.45x off the 1-year low either way: the pool is ~4 stocks, so the rules set the timing, not the ranking). E3 is earlier (2.15x) but Sharpe 0.99 vs 1.37, DD −22.8%. E4 has 10 trades of +100% vs 4, but DD −43% | Not adopted. Earliness costs drawdown; early lists stay as a research radar |
| 2026-10-10 | Do large caps take longer to move? (`sizetest.py`, market-cap rank at the signal: top 100 / 101–250 / 251–500 / 501+) | **Yes for the top 100.** New list entries 2016–22: median 224 trading days to +20% (mid 78, small 65), 14% reach +20% in 3 months (others 45–49%); 2023–26: 113 days vs 45–60. System trades in top-100 names: avg −2.1% (2016–22), +4.1% (2023–26). Portfolio test "no new top-100 buys" **passed the bar on 2016–22** (Sharpe 1.58 vs 1.37, both halves +0.2, DD −14.4% vs −17.9%) but 2023–26 is flat (Sharpe 1.63 vs 1.60, CAGR 36.0% vs 37.7%). Cutoff check: top 50 changes nothing (1.39), top 150 1.53, top 250 worse. Idea came from looking at the same data | Not adopted (user to decide): the rank exit already sells slow large caps within ~2–3 weeks, so they cost little |
| 2026-10-10 | Preferential issues, event study (`prefissue.py` downloads, `preftest.py`; NSE in-principle records Apr 2023+, 474 events in our price data, 84% micro caps; returns vs the median stock of the same size) | **Much of the move comes before the news**: median +10.8% vs peers in the 3 months before the board approval. After it, all events: median ≈ 0 vs peers, but 11.8% doubled in 12 months vs 8.1% for same-size stocks. **Promoter money in**: 6m +6.2% median vs peers (57% beat), 12m +4.6%, 12.9% doubled. **Non-promoter only**: 12m −8.6% (43% beat). Promoter in + dilution >15% (n 62): 3m +8.4%, 6m +13.7%, 67% beat. One market phase only (2023–26); BSE history for 2016–23 not yet downloaded (BSE blocked 4 parallel requests) | Research only, nothing changed. Needs 2016–23 check before any use |
| 2026-10-10 | **22 event types** (`events_dl.py`, `indexchanges.py`, `eventstudy.py`, `eventtests.py`): results reaction, insider buys/sells, pledges, buybacks, bonus, split, demerger, index inclusion/exclusion, auditor/CFO resignations, QIP, preferential, exchange price/volume queries, rating changes, bulk deals. Same-size-peer medians, 2016–22 and 2023–26. Event rules checked by Haiku on 20 event starts per type; buyback/bonus/split/demerger anchored to real corporate actions after scoring 35–58% | Positive in both periods: rating upgrades (12m +8.3% / +14.0%), director buys (+4.3% / +4.4%), promoter buys (+3.7% / +3.0%), strong results + positive reaction (+2.1% / +5.3%). Red flags in both: tender buybacks (−2.6% / −14.2%, 6m 37% beat), CFO resigns (−8.1% / −6.0%), exchange price/volume query (−6.4% / −3.3%), QIP (−4.0% / −4.3%), bulk buys by individuals/companies (−4.5% / −6.8%; fund bulk buys neutral); pledge invoked −13.4% (2016–22 only). Bonus/split/index inclusion: the move is before the news. Preferential issues 2016–22: −5.6% | Research only. Candidates: warning flags on holdings; supporting evidence on picks. Not tested as portfolio rules |
| 2026-10-10 | Red flags inside CAN SLIM (`flagtest.py`): A no buys within 90 days of a red-flag event, B also sell | Both FAIL in both periods: A 20.5%/yr Sharpe 1.15 (2016–22), 30.8% / 1.34 (2023–26); B 17.6% / 0.98. 17.7% of passing stock-weeks flagged, mostly exchange price/volume queries (10.7%) and bulk buys (3–5%), which fire on breakouts. Rare flags (CFO, QIP, buyback, pledge invoked) touch <1% of passing stocks | Rejected. Flags not shown in the report |
| 2026-10-10 | Pyramiding, book rule 12 (`pyramidtest.py`, new `Config.pyramid`): P1 50/30/20 at +2.5/+5%, P2 50/50 at +5%, P3 50/50 at +10% | All FAIL: 2016–22 CAGR 19.3–21.1% vs 24.7%, Sharpe 1.15–1.21 vs 1.37; 2023–26 31–34% vs 37.7%, DD better (−10 to −11 vs −13.7). Base unchanged after the simulator change (sanity check). The system is only 39% invested on average in 2016–22; pyramiding cuts that to 31–34% | Rejected. Cash drag is the bigger lever |
| 2026-10-10 | Promoter ownership, book rule 18 (`promotertest.py`; BSE shareholding field 10098 → `shp.history().promoter_pct`, 241 pool stocks, Dec 2015+): R1 ≥ 50%, R2 ≥ 35%, R3 not down >1pt in a year | All FAIL. R1 20.5%/yr Sharpe 1.29 DD **−11.8%** (pool 2); R2 23.7% / 1.34 / −17.0% (2023–26 1.68 vs 1.60); R3 21.5% / 1.23. Median passing stock already 56% promoter-held | Rejected |
| 2026-10-14 | **Sectors** (`sectortest.py`; literature review in insights). Screener basic industries with >=5 liquid members (~23 groups/date), monthly 2015–26. A: 10 group signals vs next 3/6m excess group return. A3/A4: how long a group stays in the top 20% and what follows. B: CAN SLIM ranked by RS + group strength / sector score; separate 'sector leaders' list | Plain group strength works in all periods (top-minus-bottom groups +4.2 / +3.5 / +4.7% per 3m for 16-19 / 20-22 / 23-26); near-52w-high and share-of-members-near-highs about as good; 'rising fast', earnings breadth, big-caps-lead-small-caps, 3-year reversal and the composite add nothing. A group stays top 20% for a median 2 months (35–48% last 3m+, ~15% 6m+, 5–6% 12m+). Entering the top 20% adds little afterwards; dropping out is followed by −1 to −5% vs the market over 3–12m in every period. B: tilts Sharpe 1.37–1.41 vs 1.37 (16-19 +0.01, fails bar; 2023–26 check 1.65–1.92 vs 1.60); sector leaders list 13.6%/yr, Sharpe 0.47, DD −34% | Nothing adopted. Candidate: 'group left top 20%' as an amber warning on holdings (untested as a rule) |
| 2026-10-14 | Sector warning as a rule (`warntest.py`): W1 group dropped out of top 20% in last 13 weeks, W2 group in bottom 20%, W3 bottom half → no buy / sell | W1 passes 2016–22 (Sharpe 1.44 vs 1.37, 16-19 +0.13, 20-22 +0.03, DD −16.2 vs −17.9) but 2023–26 worse (1.51 vs 1.60, CAGR 34.8 vs 37.7). W2 1.40, W3 1.37 fail | Not a rule. Shown as AMBER on holdings (sectors.py, holdings.py) and in the Sector radar |
| 2026-10-14 | **Seven other frameworks** (`frameworks.py`, `fwtest.py`): Coffee Can, Magic Formula, QGLP-style, GARP, Graham, trend template, stage analysis; rules from the sources, no tuning; 2016–26 | CAN SLIM 28.9%/yr Sharpe 1.42 DD −17.9%. trend template 21.2% / 0.64 / −45%; GARP 14.7% / 0.44 / −45%; Graham 12.7% / 0.85 / −15% (invested 25%, corr 0.39); QGLP 11.9%; Nifty 500 11.8%; Magic 10.7% (−56%); stage analysis 9.7%; Coffee Can 7.5%. Look-ahead check 0 differences; independent agent review, 1 bug fixed | Kept as separate daily lists (app page 'Other frameworks'), not used by CAN SLIM. Next: Graham as a home for CAN SLIM's idle cash |

**Compared with pure momentum** (roughly what momentum index funds do): similar return (22–25% a year) but worst drops of −54% to −56%. CAN SLIM's quality rules are what halve the drawdown.

**Book rules that couldn't be tested** (no point-in-time data before 2023): management ownership (18), buybacks / new management (22), consensus estimates and cash flow vs EPS (2), adding to winners (12, needs simulator work).
| 2026-11-14 | Position sizing and slot count (`weighttest.py`, new `Config.weighting`): rank-weighted (ranks 1-3 get 1.5 slots, 8+ half), volatility-weighted, 5 / 15 / 20 equal slots | All FAIL the bar, 2016–22. Rank-weighted: CAGR 31.0% vs 24.7%, but Sharpe 16–19 0.82 vs 0.85 and DD −24.5 vs −17.9 (it is simply more invested, 46% vs 39%). Volatility-weighted 23.7% / 1.31 / −19.9. 5 slots 30.7% / 1.18 / −31.7. 15 slots 19.9% / 1.38 / −11.9; 20 slots 16.4% / 1.31 / −10.5 (pool is ~4 stocks, extra slots stay empty). Base unchanged after the simulator change (sanity check) | Rejected: keep 10 equal slots. Return and drawdown both follow % invested; cash drag is still the lever |
| 2026-11-14 | Breakout volume as an entry confirmer (`voltest.py`): buy a passing stock only after a volume day (up >= 2% on 2x / 3x / 5x the 50-day average volume, within 10 / 20 / 20 days) | All FAIL, 2016–22: CAGR 20.4 / 21.0 / 15.5% vs 24.7%, Sharpe 1.21 / 1.26 / 1.04 vs 1.37, invested 30 / 29 / 18% vs 39%, win rate unchanged (44–46%). Splitting the current system's 230 trades: with a volume day the average is higher (7.0–10.0% vs 5.5–6.3%) but the median is not (−0.9 to −1.8% both ways) and the 2x and 3x results flip between halves | Rejected as a rule. The rules already require near-high + top RS; volume adds little on top |
| 2026-11-14 | Hold winners while profits grow, cut losers early (`growthhold.py`, new `ride_exit` growth / growth_ma200 + `hold_ok`): once +20%, exit only when quarterly profit growth < 0 / < 15% / < 25% and falling; with a 200-day exit; with an 8% stop on losers | All FAIL, 2016–22: growth-only exits CAGR 10.9–16.5%, DD −45 to −55% (price tops before reported growth); with 200-day exit 22.3% / Sharpe 0.89 / −24.7% vs base 24.7% / 1.37 / −17.9%; 8% stop changes nothing (base avg loss already −6.4%). 2023–26 check: only the 'slows' version beat base on return (42.2 vs 37.7%) with deeper DD (−20.8 vs −13.7) | Rejected: keep the rank / rule exit. 16 hold-longer variants tested so far, none pass |
| 2026-11-14 | Idle cash put to work (`idletest.py`): the idle fraction earns the Nifty 500 or the Graham portfolio instead of 6%, always or only in uptrends; CAN SLIM trades unchanged | All FAIL, 2016–22: Nifty always 28.3% / Sharpe 1.07 / DD −39.5; Nifty in uptrends 24.1% / 1.07 / −27.3; Graham always 23.9% / 1.17 / −26.6; Graham in uptrends 22.8% / 1.17 / −21.1 vs base 24.7% / 1.37 / −17.9. 2023+ check: Graham always 41.0% / 1.66 / −15.5 vs 37.7% / 1.60 / −13.7 (better there, worse in 2016–22) | Rejected: cash is idle when the market is weak, which is when the fill-ins fall too |
| 2026-11-14 | AI chart-reading blind test (`blindtest.py`): Claude Fable 5.2 reads 287 anonymised 2024 charts (204 random stock-dates + the system's 83 buys), answers BUY / WAIT / AVOID; outcomes hidden in a key | Random charts: BUY 7.3% vs AVOID 2.9% avg 3-month excess (WAIT 5.4%); by half-year the gap is 2.8 and 4.7 points against a bar of 3 in both; t = 1.0; confidence uninformative. System's buys: model-BUY 12.3% vs WAIT 3.4% on a fixed 3 months, but 3.9% vs 6.3% under the system's exits | Narrow FAIL of the pre-set bar in 2024. Second year (2022, 253 charts, same day): BUY −0.3% vs AVOID −2.4% (gap 0.8 / 4.3 points by half-year, t = 0.7), and on the system's 49 buys model-BUY was worse (−1.9% vs +6.0% per trade): FAIL. Both years: BUY−AVOID 3.3 points, t = 1.3; on the system's buys model-BUY 1.6% vs WAIT 6.2% per trade. Not adopted |
| 2026-11-15 | **Backtest cache rebuilt.** `data/cache/build.pkl` dated from 1 Oct and still used the old Rs 5 Cr liquidity floor, so every test since 6 Oct ran on a different universe from the live scan (Rs 3 Cr). Rebuilt with current prices, fundamentals and the 3 Cr floor; old cache kept as `build_2026-10-01_5cr.pkl`; `tune.Lab` now warns when the cache's floor differs from the live one | **New baseline, 2016–22: 26.8% a year, Sharpe 1.42, worst drop −20.7%** (was 24.7% / 1.37 / −17.9% on the 5 Cr cache); 2023+: 34.6% / 1.42 / −14.3% (was 37.7% / 1.60 / −13.7%). This also answers the untested 3 Cr floor: about the same | Every test before this row used the 5 Cr cache; compare new tests with the new baseline |
| 2026-11-15 | System vs momentum index funds (`experiments/benchmark_funds.py`; 2016–20 daily history of the momentum indices downloaded from niftyindices.com) | 2016–22: system 26.8% / −20.7% vs Nifty200 Momentum 30 17.4% / −34.2%, Nifty500 Momentum 50 17.5% / −39.4%, Midcap150 Momentum 50 19.8% / −39.6%, Nifty 500 12.8% / −38.3%. 2023–1 Oct 2026: 33.7% / −14.3% vs best index 18.2% / −26.7%. Daily correlation with Momentum 30: 0.45 | **System ahead** on both return and worst drop, both periods |
| 2026-11-15 | Circuit locks (`experiments/circuit_locks.py`, new simulator `no_buy` / `no_sell`): buys blocked on whole-day upper-circuit days, sells on lower-circuit days (retried); pessimistic version also blocks opens at the day's extreme after a ≥4.9% gap | 2016–22: 26.8% → 26.7% / 26.7%; 2023+: 34.6% → 33.8% / 34.2% | Fills at circuits barely matter; backtest numbers stand |
| 2026-11-15 | Survivorship (`experiments/survivorship.py`, `bhav.py`): 548 delisted/merged equity stocks since 2014 (303 ended badly) and 263 still trading without a price file rebuilt from NSE bhavcopies, same split adjustment; no fundamentals exist for them, so they pass the fundamental rules at the listed-stock rate (10%, median of 20 draws) or always (worst case) | Fair estimate: 2016–22 26.8% → 27.6%, 2023+ 34.6% → 34.3%; worst case 27.2% (DD −31.1%) and 32.3%. Writing failures to zero changes nothing — the system never still held a stock when it died (failures leave the liquid universe and the ranking months earlier). Rebuilt pool matches the backtest pool exactly | **Bias ≈ 0.4 points a year at most** |
| 2026-11-15 | Error ranges (`experiments/error_ranges.py`): block bootstrap (2,000 × 63-day blocks), paired vs indices; 200 random-pick runs from the same pool | 2016–22: 26.8%, plausible range 13.5–46.7% (Sharpe 0.54–2.61); 2023–26: 33.7%, 14.7–61.7%. Behind the Nifty 500 in 4.5% / 2.9% of resamples, behind Momentum 30 in 13.7% / 7.4%. Random picks from the pool: 26.3–28.7% and 29.6–38.2%; the RS ranking sits at the 12th / 64th percentile | Lead over the market unlikely to be luck; exact return is very uncertain; the **ranking adds nothing** over random choice within the pool — the filters are the edge |
| 2026-11-15 | **Audit of the backtest itself** (`experiments/audit.py`, outputs `data/tune/audit/`): (1) our result dates vs NSE result filing timestamps; (2) a separately written backtester; (3) 15 random trades re-priced from NSE bhavcopies; (4) every −25% gap adjustment vs NSE corporate actions, and the reverse; (5) momentum index sources | (1) 59,004 stock-quarters matched to an NSE filing (75%): 60% same day, 30% our date later, **10% our date earlier** (median 20 days; some only 2–5 days after the quarter end, e.g. BLUEDART Jun-22 dated 5 Jul, NSE 27 Jul) — Screener's EPS stamp is not always the announcement. 12 of 483 trades bought before the result was public. With the later of the two dates: 2016–22 **26.8% → 25.6%**, Sharpe 1.42 → 1.35, DD −20.7 → −21.1; 2023+ 34.6% → 34.4%. (2) Rewrite gives identical results (26.8% / −20.7%, 34.6% / −14.3%). (3) 13/13 checkable trades match NSE prices; 2 sell on budget-day special sessions missing from `data/bhavcopy`. (4) 306 gap adjustments: 250 have no NSE record, but 243 of those are penny stocks (~Rs 0.20, one tick = 25–33%) outside the universe; 7 in the universe are real bonuses/splits missing from our NSE list; no trade held across any. Fyers history comes pre-adjusted for 756 of 783 NSE splits/bonuses; 6 small bonuses (1:3, 1:4, 1:10) left as fake drops, none held. (5) niftyindices = NSE archive on all 1,802 shared days | **Arithmetic and prices verified. One real flaw: result dates** — fixed the same day (next row) |
| 2026-11-15 | **Result dates fixed: NSE-checked** (`canslim/resultdates.py`, `data.fundamentals`): a quarter counts as known from the later of Screener's EPS stamp and NSE's first result filing (usable at a day's close if filed before the next 09:15 open); 7.5% of quarters moved later, median 20 days. Cache rebuilt (old one kept as `build_2026-11-15_screenerdates.pkl`); the five evidence checks rerun | **New baseline 2016–22: 25.6% a year, Sharpe 1.35, worst drop −21.1%** (was 26.8% / 1.42 / −20.7%); 2023+ 34.4% / 1.41 / −14.2% (was 34.6% / 1.42 / −14.3%). Audit: 0 of 483 trades now bought before the result was public (was 12). Momentum funds: still beaten on return and drop. Circuit locks: 25.6% → 25.6%. Survivorship fair estimate: 25.6% → 25.8% (2016–22), 34.4% → 34.1%. Error ranges: 2016–22 plausible 12.6–45.1% a year; behind the Nifty 500 in 5.7% of resamples (was 4.5%, now just over the 5% line), behind Momentum 30 in 17.4%; 2023+ 3.2% / 7.8% | Compare new tests with this baseline. The lead over the market is likely but no longer clears the 5% luck line in 2016–22 |
| 2026-11-15 | **Result dates: remaining gap closed** (`canslim/resultdates.py` tiers). The first fix matched only 75% of quarters to an NSE filing. The rest: (a) from Mar 2025 NSE files most results as a bare "Outcome of Board Meeting" with no text — now counted when a results follow-up (newspaper publication, press release, presentation, results call) follows within 5 days; checked on 7,225 quarters that also have a proper result filing: same day 94%, more than 3 days early 1%; (b) MCX, ABBOTINDIA, ICICILIFE have no NSE announcements at all — BSE result filings downloaded (`python -m canslim.resultdates --bse`); (c) no filing and a Screener stamp under 21 days after the quarter end (wrong 41–89% of the time where checkable) — moved to the company's usual lag, else the SEBI deadline. Sources for the 27,267 quarters of stocks in the universe: NSE result filing 26,363 (96.7%), confirmed board outcome 378, BSE 81, usual lag 22, Screener stamp kept (no filing, stamp 21+ days after the quarter end) 423 (1.6%) | 2016–22 **25.6% a year, Sharpe 1.34, worst drop −21.1%** (1.35 after the first fix); 2023+ 34.4% / 1.41 / −14.2%. Audit: 0 of 483 trades bought before the result was public; rewrite identical; 14/14 checkable trades match NSE prices. Evidence checks unchanged (survivorship fair estimate 25.7%; behind the Nifty 500 in 5.8% of resamples) | **Baseline: 25.6% / 1.34 / −21.1% (2016–22).** The remaining date gap cost nothing measurable |
| 2026-11-15 | **Strict O'Neil vs the live system** (`experiments/strict_book.py`, live system untouched): each departure from the book reversed alone, then the strict book version. Book rules: quarterly EPS +25%, sales +25% or 3 quarters accelerating, annual EPS +25% in each of 3 years, ROE 17%, buy only on a breakout above a sound base's pivot on volume ≥ 1.4× average and within 5% of the pivot, 8% stop, +20% profit rule with the 8-week hold, no rank exit, no trend template. EPS derived per quarter from Screener's split-adjusted 12-month EPS. A lenient breakout reading (pattern flags as warnings except too deep / V-shaped; breakout up to 20 days old) added after the strict one bought ~1 stock a year | 2016-22 (live 25.6% / 1.34 / −21.1%): EPS instead of profit 24.4% / 1.32 / −19.1; **book A rule 8.5% / 0.39** (pool 4 → 1); book sales 15.8% / 0.89 (2023+ 38.2%); no trend template 25.1% / 1.22 (2023+ 38.1%); **base breakouts 8.7% / 0.75** (invested 2%), lenient 16.6% / 1.30 / −9.1 (2023+ 9.4%); 8% stop 24.9% / 1.32 / −18.9; book sells together 22.4% / 1.12 / −20.7 (2023+ 34.2% / 1.57); **STRICT BOOK 6.5%, invested 1%, ~1 trade a year** (lenient 7.7%) | No departure reversal passes the bar. **The strict book barely trades on NSE**: its A rule and breakout rule leave almost nothing to buy. Live system's departures justified |

### Caveats
- **Survivorship bias:** the price data holds only stocks listed today. Measured on 2026-11-15 by putting 548 delisted stocks back: about 0.4 points a year (see test log).
- **Precision:** with ~4 stocks in the pool on a typical day, a 7-year backtest return has a plausible range of roughly ±15 points a year. Treat headline returns as rough.
- **Trade-to-trade stocks:** the scanner downloads only EQ-series stocks, so stocks moved to the BE segment (8 liquid ones on 30 Sep 2026, e.g. HFCL, STLTECH) are invisible to the daily scan. Left as is: they cannot be traded intraday and are usually under exchange surveillance.
- Prices in the tracker are raw (unadjusted). A split or bonus after you buy will show as a fake loss until you edit the holding.

---

## Code map

| File | What it does |
|---|---|
| `canslim/daily.py` | Daily run: prices → fundamentals → rules → report → database |
| `canslim/db.py` | SQLite schema and writers; `python -m canslim.db --backfill` loads the CSVs in `data/history` |
| `canslim/holdings.py` | Traffic-light logic |
| `canslim/sectors.py` | Sector radar: weekly industry-group strength, weeks in the top 20%, groups that dropped out |
| `canslim/frameworks.py` | Seven other frameworks (Coffee Can, Magic Formula, QGLP-style, GARP, Graham, trend template, stage analysis): rules and daily lists |
| `canslim/stockchart.py` | Price + 20/200-day EMA per stock (split-adjusted, EMAs on full history) for the app's chart panel and the report's chart drawer; finds tickers named in text |
| `canslim/fwtest.py` | Backtest of the other frameworks vs CAN SLIM + look-ahead check (Saturdays via run_daily.bat) |
| `canslim/sectortest.py`, `canslim/warntest.py` | Sector research: which signals identify strong groups, how long they last, warnings as rules |
| `canslim/docs.py` | Downloads a company's concall transcripts, presentations and annual report; writes facts.md / sources.md |
| `.claude/skills/brief/` | The `/brief` skill for Claude Code |
| `canslim/paper.py` | Paper portfolio + watching list. Rebuilt from the database on every daily run (`python -m canslim.paper`) |
| `tracker_app.py` | Streamlit app |
| `canslim/portfolio.py` | Backtest simulator (ride-mode options exist but are off; `no_buy` / `no_sell` masks block fills on given days, e.g. circuit locks) |
| `canslim/exp.py`, `canslim/experiments/` | **Experiment harness — every new test goes here.** One file per test in `canslim/experiments/`; `python -m canslim.exp list` / `run <slug>`. Writes `data/tune/<slug>/results.csv`, the Insights page entry and a running count of variants tested (`data/tune/experiments.csv`). See "Adding a test" below |
| `canslim/bhav.py` | Every NSE stock's daily bars from the bhavcopies, including delisted ones (`data/cache/bhav_eq.parquet`) |
| `tests/test_harness.py` | Offline tests for the harness and the simulator's fill limits: `python -m unittest tests.test_harness -v` |
| `canslim/tune.py`, `holdtest.py`, `reentry.py`, `emerging.py`, `winners.py`, `runup.py`, `sizetest.py`, `preftest.py`, `flagtest.py`, `pyramidtest.py`, `promotertest.py`, `weighttest.py`, `voltest.py`, `growthhold.py`, `idletest.py`, `blindtest.py` |
| `canslim/events_dl.py` | NSE event feeds → `data/events/`: announcements (2012+, monthly), insider trades incl. pledges (2016+), corporate actions (2010+), bulk deals (2016+, per day; API caps 70 rows). One request at a time, resumable |
| `canslim/indexchanges.py` | NSE Indices press releases (semi-annual reviews) → `data/events/index_changes.csv` |
| `canslim/eventstudy.py`, `canslim/eventtests.py` | Shared event-study method (before/after vs same-size median) and the 15 event tests; `announcements` also writes `verify_sample.csv` for a cheap LLM check of the text rules |
| `canslim/prefissue.py` | Preferential issue data: NSE structured records (Apr 2023+, `--nse`) and BSE fund-raising announcements per company (2016+, `--bse`; BSE blocks fast/parallel requests, use 1 worker) → `data/pref/` | Research tests (results under `data/tune/`, `data/research/`) |
| `canslim/prices.py`, `fyers_auth.py` | Fyers price download |
| `canslim/fundamentals.py` | Screener.in fundamentals (via the logged-in Chrome profile on port 9222) |

Not part of this system: `app.py`, `scanner.py`, `morestrictscanner.py` (older, separate scripts).

### Adding a test
New ideas are one file in `canslim/experiments/`, not a new script. The common kind compares variants of the live system:

```python
from canslim.exp import Experiment, Variant
EXPERIMENT = Experiment(slug="fifteen-slots", title="15 slots instead of 10", question="...", tags="sizing",
                        variants=[Variant("current"), Variant("15 slots", cfg={"n": 15})])
```

A `Variant` can change the config (`cfg=`), the ranked pool (`score=`), the simulator inputs (`sim=`: entry_ok, hold_ok, no_buy, no_sell) or supply an equity curve built another way (`curve=`: an index fund, an overlay). The first variant is the base. The standard decision bar is applied to 2016–22 only and 2023+ is shown but never used to choose. Checks that are not variant comparisons (data audits, error ranges) pass `run=` instead. Every run writes its Insights entry automatically, but read the wording before pushing. The old `*test.py` scripts are kept as they are because their results are recorded; they are not the pattern to copy.

The decision years (2016–22) have now been used for well over 100 variants (41 in `tune.py`, the rest across the test scripts, and the count from `exp.py` on top). Each further variant that "passes" is more likely to be luck. Prefer forward evidence: paper trading, and new years as they arrive.

---

## Open items
- [ ] Score conviction vs results once there are 20–30 rated stocks
- [ ] Guidance tracker across briefs: check each open promise when the next results come out
- [ ] Test what successful discretionary investors do that *can* be tested: adding to winners (pyramiding), concentration (5 vs 10 stocks)
- [x] Fyers TOTP login set up in `.env` (2026-10-08); the daily run needs no human
- [ ] Re-login to Screener (Google) in the scan's Chrome before **2026-11-06**, when its session expires
- [x] Shareholding history before 2023: BSE API, Dec 2015 on (`python -m canslim.shp --pool`); tested, no edge as a filter
- [ ] 3 pool stocks returned no BSE filings (FACT, JKLAKSHMI, PGHL), not investigated
- [ ] "Clean winner" test: stocks that doubled before falling 30%
- [x] Audit the backtest itself (2026-11-15, `experiments/audit.py`): arithmetic, prices, split adjustments and index sources verified; result dates are 10% too early (see test log)
- [x] Backtest result dates switched to NSE-checked dates (2026-11-15, `canslim/resultdates.py`); baseline restated
- [ ] Data for the untested book rules: I (BSE shareholding filings name holders > 1% each quarter; score funds by AMFI NAV history), N catalysts (NSE announcement categories: orders, product launch, capacity, MD/CEO; free-text press releases), analyst estimates (no free history: Trendlyne Forecaster paid, or daily Yahoo snapshots from now)
- [ ] Two budget-day special sessions (1 Feb 2020, 1 Feb 2026) missing from `data/bhavcopy`

## Change log

- **2026-11-15**: Result dates: three exchange tiers (NSE result filing, BSE result filing, confirmed NSE board outcome) plus a fallback for early Screener stamps; `q["known_src"]` records which one set each date. BSE files in `data/events/bse_results/`. Cache rebuilt (previous one kept as `build_2026-11-15_nse_tier1.pkl`).
- **2026-11-15**: **Result dates NSE-checked** (`canslim/resultdates.py`, cache `data/events/result_filings.parquet`): `data.fundamentals` now keeps the Screener stamp as `known_screener` and sets `known` to the later of it and NSE's result filing. Affects backtests, the earnings monitor and the framework lists; the live scan's rules are unchanged. Backtest cache rebuilt, baseline restated (25.6% / 1.35 / −21.1% for 2016–22).
- **2026-11-15**: Backtest audit (`canslim/experiments/audit.py`, five checks, results in `data/tune/audit/` and on the Insights page); `tune.Lab` now keeps the fundamentals (`lab.fund`).
- **2026-11-15**: Experiment harness (`canslim/exp.py`, `canslim/experiments/`, see "Adding a test"); simulator fill limits (`no_buy` / `no_sell`); `canslim/bhav.py` (every NSE stock incl. delisted, from bhavcopies); offline tests (`tests/test_harness.py`); backtest cache rebuilt on the live Rs 3 Cr floor with a stale-cache warning in `tune.Lab`; momentum index history 2016–20 filled (`data/indices/old/gap_*.json`). Four evidence checks run (momentum funds, circuit locks, survivorship, error ranges), all in the test log and on the Insights page.
- 2026-10-15: Names of living investors removed from the app, reports and research notes (legal caution). Frameworks now show only their strategy names: Coffee Can, Magic Formula, QGLP-style, GARP, Trend template, Stage analysis (Graham and O'Neil kept). Internal keys `lynch`/`minervini`/`weinstein` renamed `garp`/`trend`/`stage`, database rows migrated.
- 2026-10-15: Chart panel layers, each with an on/off switch: signals (▲▼ backtest trades of the current rules 2016–26 from data/tune/sizetest/trades.csv, joined/left the live CAN SLIM list, paper trades, your holdings + buy-price line), result days (profit vs a year ago, purple = +25%+), RS line vs Nifty 500 in its own pane with 'RS leads' dots (RS line at a 52-week high while price is 5%+ below its high), volume pane (40%+ above the 50-day average coloured green/red, 50-day line), base pivot and buy-zone lines. Hover a day for event details. Lightweight Charts v5 (panes). Stock page: chip to open its chart in the panel. Note: after changing canslim/*.py, restart the local app (Streamlit doesn't reload imported modules).
- 2026-10-15: App chart panel now uses TradingView's open-source Lightweight Charts (loaded from unpkg): wheel zooms, drag scrolls through time, price axis refits to the visible range, values follow the cursor; replaces plotly, which could not scroll after zooming.
- 2026-10-15: Click any stock to see its chart (price, 20- and 200-day EMA, 5 years by default). App: every table with a symbol column opens a panel on the right (1y/2y/5y/All, log scale); symbols named in briefs, insights and the dropped list appear as chips. Daily report: stock names open a chart drawer (self-contained SVG, no internet needed; adds ~0.4 MB per report).
- 2026-10-14: Sector radar (`sectors.py`) in the daily report, the database (table `sector_radar`) and the app page "Sectors"; holdings get an AMBER warning when their industry group dropped out of the top 20% in the last 13 weeks (snapshot column `group_warn`). Seven other frameworks (`frameworks.py`) make daily lists stored as `fw_*` in `picks`, shown on the app page "Other frameworks" with rules, backtest (`fwtest.py`, refreshed every Saturday by run_daily.bat) and Screener links for spot checks.
- **2026-10-10**: App page **Insights** (all research findings, `data/research/insights/*.md`, 10 back-filled from the test log). New research: `sizetest.py` (large caps slow, not adopted) and preferential issues (`prefissue.py`, `preftest.py`, research only).
- **2026-10-08**: Paper portfolio: idle cash now earns 0% (was 6% a year). Backtests (`portfolio.Config.cash_yield`) still assume 6%.
- **2026-10-08**: Fyers TOTP login fixed: the token step answers HTTP 308 with the auth code, which `fyers_auth` treated as an error. Scheduled task now runs on battery and catches up missed runs (3, 5 and 7 Oct had been skipped). Scan of 7 Oct: 9 picks, new CHENNPETRO (brief: suggested 2/5).
- **2026-10-06**: Liquidity filter lowered from Rs 5 Cr to **Rs 3 Cr median daily traded value** (user choice, untested: the backtest results above were on Rs 5 Cr). Universe 942 -> 1,092 stocks; first new pick KAPSTON (Rs 3.5 Cr/day). `factors.MIN_TURNOVER`, `backtest.MIN_TURNOVER`.
- **2026-10-02**: `canslim/shp.py` (BSE shareholding history, holders per category, filing dates) and `canslim/insttest.py`; rule 14 tested, not adopted.
- **2026-10-02**: Book audit; rule 6 (net margin improving) added to the daily rules, `tune.book_score` and `final.json` (old config kept as `final_2026-10-02_before_R6.json`).
- **2026-10-02**: Automation: Fyers TOTP login (`fyers_auth.login_via_totp`, browser fallback), unattended briefs (`canslim/autobrief.py`, step 2 of `run_daily.bat`), `canslim.docs --search/--read`, brief column on the app's Today page. Tested: headless permissions (allowed command runs, others blocked) and a full unattended brief (MOREPENLAB, 90 s, 2/5).
- **2026-10-02**: Briefs for all 8 CAN SLIM picks of 1 Oct (suggested: TDPOWERSYS 4, MCX 4, LUMAXTECH 4, RPEL 4, SKYGOLD 3, CUPID 2, KRISHANA 2, SBC 1). Fetcher now goes back to find ≥2 transcripts; template gained a Valuation section.
- **2026-10-02**: Research briefs via `/brief` in Claude Code (`canslim/docs.py`, skill, Research page, conviction table). First brief: SKYGOLD (suggested 3/5).
- **2026-10-02**: Paper portfolio and "Sold, still watching" list (`canslim/paper.py`, two new app pages). Run on every daily scan.
- **2026-10-02**: SQLite database (`data/canslim.db`), holdings tracker with traffic light and decision journal, Streamlit app (`run_app.bat`), this file. Hold-winners and re-entry tests (all rejected; current sell rule kept).
- **2026-10-01**: Earnings monitor, emerging list, buy-point badge, big-winner study; fundamentals for 384 more companies.
- **2026-09-30**: Daily scan, scheduled task, tuned rules (ROE 20).

## Market data (standalone, not used by the scanner)
`python indexdata.py` downloads only what is missing, then rebuilds everything under `data/indices/`:
- **Every NSE index (204)**: OHLC from Jan 2005. Volume, turnover (Rs cr), P/E, P/B and dividend yield from Jul 2012 (NSE's daily archive). 2005–Jul 2012 and the Apr–Jun 2015 archive gap are OHLC from niftyindices.com, which needs the debug Chrome; no free source publishes index volume before Jul 2012. Index values from before an index's launch date are NSE back-calculations, not real trading.
- Old names are joined into one series: CNX → Nifty (2015), "Free Float Midcap/Smallcap 100" (2016–18). Bad prints in NSE's files are blanked and flagged in `bad_print`: a one-day move of 8% or more that fully reverses the next day, mostly 4 Oct and 4 Nov 2023.
- **`_market_volume.parquet`**: whole-NSE equity volume, turnover, number of trades and advances/declines/unchanged, daily from Jan 2005. Built from NSE stock bhavcopies, which are kept in `data/bhavcopy/` and are not in git. They cover every stock including delisted ones, so they are survivorship-free.
- Files: one `<INDEX>.parquet` per index, `_all.parquet` (long format) and `_summary.csv`.

`python -m canslim.shp --pool|--all|--syms` downloads BSE shareholding history from Dec 2015: holders and % for institutions, mutual funds and FPIs, with filing dates. Stored in `data/shp/`.

## Backup
Git repo (private GitHub). Not committed: `.env`, the Fyers token, `.browser_profile/`, PDFs, `data/cache/`, `data/bhavcopy/`, raw index files and logs. All of these except the secrets can be rebuilt by script.
