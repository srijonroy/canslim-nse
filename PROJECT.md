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

**Result 2016–22:** 24.7% a year, worst drop −17.9%, Sharpe 1.37 (before the margin rule: 23.8%, −21%, 1.26) (Nifty 500: about 12% a year). The money comes from the filters themselves: random picks from the same passing pool do about as well.

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

**Compared with pure momentum** (roughly what momentum index funds do): similar return (22–25% a year) but worst drops of −54% to −56%. CAN SLIM's quality rules are what halve the drawdown.

**Book rules that couldn't be tested** (no point-in-time data before 2023): management ownership (18), buybacks / new management (22), consensus estimates and cash flow vs EPS (2), adding to winners (12, needs simulator work).

### Caveats
- **Survivorship bias:** only stocks still listed today are in the price data, so every backtest number is somewhat flattered.
- Prices in the tracker are raw (unadjusted). A split or bonus after you buy will show as a fake loss until you edit the holding.

---

## Code map

| File | What it does |
|---|---|
| `canslim/daily.py` | Daily run: prices → fundamentals → rules → report → database |
| `canslim/db.py` | SQLite schema and writers; `python -m canslim.db --backfill` loads the CSVs in `data/history` |
| `canslim/holdings.py` | Traffic-light logic |
| `canslim/docs.py` | Downloads a company's concall transcripts, presentations and annual report; writes facts.md / sources.md |
| `.claude/skills/brief/` | The `/brief` skill for Claude Code |
| `canslim/paper.py` | Paper portfolio + watching list. Rebuilt from the database on every daily run (`python -m canslim.paper`) |
| `tracker_app.py` | Streamlit app |
| `canslim/portfolio.py` | Backtest simulator (ride-mode options exist but are off) |
| `canslim/tune.py`, `holdtest.py`, `reentry.py`, `emerging.py`, `winners.py`, `runup.py`, `sizetest.py`, `preftest.py` |
| `canslim/prefissue.py` | Preferential issue data: NSE structured records (Apr 2023+, `--nse`) and BSE fund-raising announcements per company (2016+, `--bse`; BSE blocks fast/parallel requests, use 1 worker) → `data/pref/` | Research tests (results under `data/tune/`, `data/research/`) |
| `canslim/prices.py`, `fyers_auth.py` | Fyers price download |
| `canslim/fundamentals.py` | Screener.in fundamentals (via the logged-in Chrome profile on port 9222) |

Not part of this system: `app.py`, `scanner.py`, `morestrictscanner.py` (older, separate scripts).

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

## Change log
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
