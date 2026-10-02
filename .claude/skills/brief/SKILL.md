---
name: brief
description: Write a business research brief for an NSE stock in the CAN SLIM project - fetch its concall transcripts, presentations and annual report, read them, and answer the 12-question conviction checklist with cited evidence. Use when the user types /brief SYMBOL or asks for a brief / business research / conviction check on a stock.
---

# /brief SYMBOL

Writes `data/research/companies/<SYM>/brief.md` for the tracker app's Research page. No API: you (Claude Code) do the reading.

## Steps

1. **Fetch** (needs the debug Chrome on :9222; start it the way `run_daily.bat` does if it's down):
   `python -m canslim.docs <SYM>` → `docs/*.txt`, `facts.md`, `sources.md` in `data/research/companies/<SYM>/`.
   Tell the user the counts as soon as it finishes.
2. **Read** `facts.md` and `sources.md` in full. Read the two newest transcripts and the newest presentation in full
   with `python -m canslim.docs <SYM> --read <file> [--start N --length 25000]` (cleaned text, in chunks).
   For older transcripts, search for guidance:
   `python -m canslim.docs <SYM> --in "*transcript.txt" --search "guidance|target|expect|capacity|margin|by end of"`
   — that is what Q7 checks delivery against.
   The annual report is huge: never read it whole. Search it:
   `python -m canslim.docs <SYM> --search "Management Discussion|related party|pledge|qualified opinion|emphasis of matter|contingent liabilit|bonus|preferential|warrant|QIP|promoter"`
   and follow up on anything that needs a closer look with a narrower search.
   Use only these `canslim.docs` commands for documents (they are the only shell commands allowed in unattended runs).
3. **Write** `brief.md` using `template.md` in this folder, exactly that structure (the app parses the checklist table
   and the `Suggested conviction:` line).
4. **Report** to the user in chat: suggested conviction, the 3 strongest points, the red flags, and the open questions
   only they can answer (scuttlebutt). Give the file path.

## Rules for the brief

- **Every score of 2 needs a citation**: `docs/2026-08_transcript.txt p.7` or a facts.md table. Quote management's
  exact words for promises and guidance. No citation → score at most 1.
- **Separate what management says from what the numbers show.** Promises go in the guidance table; delivery is judged
  against facts.md.
- **Guidance table**: every concrete promise (capacity, revenue/margin target, launch, capex, debt target) with the
  call it came from and when it's due. For older calls, mark whether later numbers show it delivered.
  This feeds Q7 and the guidance tracker.
- **Red flags (Q8) are a cap**: any confirmed red flag → suggested conviction at most 2, whatever the total.
- **Q10 cyclicality**: say plainly if margins look like a cyclical peak (commodities, chemicals, metals, sugar,
  shipping, gold-price-linked businesses).
- **Valuation** section: not scored, but always filled. Q12 must be judged against it (a P/E of 200+ means the market
  already sees the story).
- **Documents disagreeing with each other** (e.g. a segment figure differing between the annual report and the
  presentation) go under Red flags as "suspected" with both sources.
- **Q12** is the hardest: if you can't name what the market is missing, score 0 and say so.
- The suggested conviction is a starting point for the user, not a verdict. Write "Suggested", never "Buy" / "Sell".
- Be plain and short. Indian number style (Rs crore). No hype words.
- If no concalls exist (common for small companies), say so at the top and work from the annual report, presentations
  and facts only; most scores will be 0-1.

## Scoring → suggested conviction
Total of 12 questions (0-24): 0-8 → 1, 9-12 → 2, 13-16 → 3, 17-20 → 4, 21-24 → 5. Then apply the red-flag cap.
