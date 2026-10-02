"""Unattended research briefs after the daily scan, via Claude Code in headless mode (no API key: it uses the
Claude Code login on this PC).

Which stocks: those on the latest CAN SLIM list whose brief is missing, older than STALE_DAYS, or older than the
newest earnings-call document (a new quarter's results came out). Highest system rank first, at most MAX_PER_DAY,
to keep Claude Code usage in check.

How: `claude -p "<use the brief skill for SYM>"` in the project folder, with tools restricted to reading/writing files
and the `python -m canslim.docs` command. Any other shell command is refused (nobody is there to approve it).
Each run is logged to data/research/companies/<SYM>/brief_run.log and to the brief_runs table in data/canslim.db.

usage: python -m canslim.autobrief [--dry-run] [--max N] [--only SYM]
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from canslim import db, docs

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "daily.log"
MAX_PER_DAY, STALE_DAYS, TIMEOUT_S = 3, 90, 45 * 60
# Windows runs shell commands through PowerShell, so both shell tools get the same single allowed prefix
ALLOWED = ["Read", "Grep", "Glob", "Write", "Edit", "Skill",
           "Bash(python -m canslim.docs:*)", "PowerShell(python -m canslim.docs:*)"]
# a model included in the Claude Code plan (the interactive default may need paid credits)
MODEL = os.environ.get("CANSLIM_BRIEF_MODEL", "sonnet")
PROMPT = ("Use the brief skill to write the research brief for {sym}. This is an unattended scheduled run: nobody "
          "will answer questions, so do not ask any. Follow the skill exactly, write "
          "data/research/companies/{sym}/brief.md, and finish with a 5-line plain-text summary: suggested conviction, "
          "checklist total, the strongest point, the biggest red flag or risk, and the valuation in one line.")

SCHEMA = """CREATE TABLE IF NOT EXISTS brief_runs(
  date TEXT, symbol TEXT, reason TEXT, status TEXT, seconds INTEGER, suggested INTEGER, total INTEGER, note TEXT);"""


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} autobrief: {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def claude_exe() -> str | None:
    """`claude` on PATH, else the newest binary bundled with the VS Code extension."""
    exe = shutil.which("claude")
    if exe:
        return exe
    pats = [os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe")]
    found = sorted((p for pat in pats for p in glob.glob(pat)), key=os.path.getmtime)
    return found[-1] if found else None


def brief_info(sym: str):
    f = docs.COMPANIES / sym / "brief.md"
    if not f.exists():
        return None, None, None
    t = f.read_text(encoding="utf-8")
    d = re.search(r"Brief date:\s*(\d{4}-\d{2}-\d{2})", t)
    s = re.search(r"Suggested conviction:\s*(\d)", t)
    rows = re.findall(r"^\|\s*\d{1,2}\s*\|[^|]+\|\s*([0-2])\s*\|", t, flags=re.M)
    return (d.group(1) if d else None, int(s.group(1)) if s else None, sum(map(int, rows)) if rows else None)


def newest_call(sym: str) -> str | None:
    """YYYY-MM of the newest downloaded earnings-call document."""
    per = [p.name[:7] for p in (docs.COMPANIES / sym / "docs").glob("20??-??_*.txt")]
    return max(per) if per else None


def candidates(c) -> list:
    d = c.execute("SELECT MAX(date) FROM picks WHERE list='canslim'").fetchone()[0]
    if not d:
        return []
    syms = [r[0] for r in c.execute("SELECT symbol FROM picks WHERE list='canslim' AND date=? ORDER BY rank", (d,))]
    out = []
    for s in syms:
        bdate = brief_info(s)[0]
        if bdate is None:
            out.append((s, "no brief yet"))
            continue
        age = (date.today() - date.fromisoformat(bdate)).days
        if age > STALE_DAYS:
            out.append((s, f"brief {age} days old"))
            continue
        try:                                   # cheap: lists Screener links, downloads only what's new
            docs.fetch(s)
        except Exception as e:
            log(f"{s}: document check failed ({e}); keeping the existing brief")
            continue
        nc = newest_call(s)
        if nc and nc > bdate[:7]:
            out.append((s, f"new results/call {nc} after brief {bdate}"))
    return out


def run_one(exe: str, sym: str) -> tuple:
    try:
        docs.fetch(sym)                         # documents first, so the headless run starts with them on disk
    except Exception as e:
        return "fetch failed", 0, str(e)[:200]
    before = brief_info(sym)[0]
    t0 = time.time()
    cmd = [exe, "-p", PROMPT.format(sym=sym), "--model", MODEL, "--allowedTools", *ALLOWED, "--output-format", "text"]
    logf = docs.COMPANIES / sym / "brief_run.log"
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT_S, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        out = (p.stdout or "") + ("\n[stderr]\n" + p.stderr if p.stderr else "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        out, rc = "timed out", -1
    secs = int(time.time() - t0)
    logf.write_text(f"{datetime.now():%Y-%m-%d %H:%M} rc={rc} {secs}s\n{out}", encoding="utf-8")
    after = brief_info(sym)[0]
    if rc == 0 and after == date.today().isoformat():      # brief.md rewritten today
        return "ok", secs, out.strip().splitlines()[-1][:200] if out.strip() else ""
    return ("timeout" if rc == -1 else f"failed rc={rc}"), secs, out.strip()[-300:]


def main(dry=False, cap=MAX_PER_DAY, only=None):
    c = db.connect()
    c.executescript(SCHEMA)
    todo = [(only.upper(), "requested")] if only else candidates(c)
    if not todo:
        log("no briefs needed today")
        return
    log("needed: " + ", ".join(f"{s} ({r})" for s, r in todo) + (f"; doing at most {cap}" if len(todo) > cap else ""))
    if dry:
        return
    exe = claude_exe()
    if not exe:
        log("Claude Code CLI not found (install Claude Code or the VS Code extension); skipping briefs")
        return
    for sym, reason in todo[:cap]:
        log(f"{sym}: writing brief ({reason})...")
        status, secs, note = run_one(exe, sym)
        _, sug, tot = brief_info(sym)
        c.execute("INSERT INTO brief_runs VALUES(?,?,?,?,?,?,?,?)",
                  (date.today().isoformat(), sym, reason, status, secs, sug, tot, note))
        c.commit()
        log(f"{sym}: {status} in {secs // 60} min" + (f", suggested {sug}/5, checklist {tot}/24" if status == "ok" else f" - {note[:150]}"))
    c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=MAX_PER_DAY)
    ap.add_argument("--only")
    a = ap.parse_args()
    main(a.dry_run, a.max, a.only)
