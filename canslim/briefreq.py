"""Research briefs on request: anyone using the tracker app can ask for a brief on any NSE stock.

The cloud app cannot run Claude Code, so a request travels as a GitHub issue:

  site  -> submit(sym)   opens an issue "brief: SYM" with the label `brief-request`
  PC    -> work()        (scheduled every 15 min + after the daily scan) picks up open requests, writes the
                         brief with the same headless Claude Code run as canslim.autobrief, commits and pushes
                         data/research/companies/SYM, then closes the issue. The push redeploys the site.

Safety: a request is only honoured if the issue carries the label AND was opened by the repo owner's account
(the site posts with the owner's issues-only token), and the symbol passes a strict pattern and is a known NSE
symbol. Nothing from the issue except that symbol is ever used. Caps: MAX_OPEN queued, MAX_PER_DAY written.

Tokens: the site reads GITHUB_QUEUE_TOKEN from Streamlit secrets (fine-grained, this repo, Issues read/write
only). On this PC the login git already uses is read at call time; nothing is stored.

usage: python -m canslim.briefreq work | list
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

from canslim import datapack

ROOT = Path(__file__).resolve().parent.parent
OWNER = datapack.REPO.split("/")[0]
API = datapack.API
LABEL = "brief-request"
MAX_OPEN, MAX_PER_DAY, FRESH_DAYS = 5, 5, 30
LOCK = ROOT / "data" / "cache" / "briefreq.lock"
SYM_RE = re.compile(r"[A-Z0-9][A-Z0-9&-]{0,19}")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _h(token: str | None) -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _sym(title: str) -> str | None:
    m = re.fullmatch(r"brief:\s*(\S+)", title.strip())
    return m.group(1) if m and SYM_RE.fullmatch(m.group(1)) else None


def requests_list(token: str | None = None, state: str = "open", n: int = 20) -> list:
    """[{symbol, number, state, result, opened, closed}] newest first. Only genuine requests (label + owner)."""
    r = requests.get(f"{API}/issues", headers=_h(token), timeout=30,
                     params={"labels": LABEL, "state": state, "per_page": n, "sort": "created", "direction": "desc"})
    r.raise_for_status()
    out = []
    for i in r.json():
        s = _sym(i.get("title", ""))
        if not s or i.get("user", {}).get("login") != OWNER or "pull_request" in i:
            continue
        out.append({"symbol": s, "number": i["number"], "state": i["state"],
                    "result": {"completed": "done", "not_planned": "failed"}.get(i.get("state_reason"), "queued"),
                    "opened": i["created_at"][:10], "closed": (i.get("closed_at") or "")[:10]})
    return out


def submit(sym: str, token: str, known: set) -> str:
    """Queue a request. Returns a message for the user; raises ValueError for a request that is refused."""
    sym = sym.strip().upper()
    if not SYM_RE.fullmatch(sym) or sym not in known:
        raise ValueError(f"{sym} is not an NSE symbol the scanner knows.")
    open_ = requests_list(token)
    if any(r["symbol"] == sym for r in open_):
        return f"{sym} is already in the queue."
    if len(open_) >= MAX_OPEN:
        raise ValueError(f"The queue is full ({MAX_OPEN} waiting). Try again once one finishes.")
    r = requests.post(f"{API}/issues", headers=_h(token), timeout=30, json={
        "title": f"brief: {sym}", "labels": [LABEL],
        "body": "Research brief requested from the tracker app. Written by the scanner PC, then closed."})
    r.raise_for_status()
    if LABEL not in [l["name"] for l in r.json().get("labels", [])]:
        raise RuntimeError("request was created without its label; the queue token needs Issues read/write")
    return f"{sym} is queued."


# ---------------------------------------------------------------- PC side

def _log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} briefreq: {msg}"
    print(line, flush=True)
    with open(ROOT / "data" / "daily.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _ensure_chrome():
    """Document fetching goes through the logged-in debug Chrome on :9222 (same start as run_daily.bat)."""
    def up():
        try:
            return requests.get("http://127.0.0.1:9222/json/version", timeout=3).ok
        except requests.RequestException:
            return False
    if up():
        return
    subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--remote-debugging-port=9222",
                      rf"--user-data-dir={ROOT}\.browser_profile", "https://www.screener.in/"])
    for _ in range(20):
        time.sleep(1)
        if up():
            return
    raise RuntimeError("debug Chrome did not start")


def _git(*a) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=600, creationflags=NOWIN)


def _publish(sym: str):
    """Commit and push only this company's research folder; anything else in the working tree is left alone."""
    path = f"data/research/companies/{sym}"
    _git("add", "--", path)
    if _git("diff", "--cached", "--quiet", "--", path).returncode != 0:
        p = _git("commit", "-m", f"Research brief: {sym} (requested on the site)", "--", path)
        if p.returncode != 0:
            raise RuntimeError("git commit failed: " + (p.stderr or p.stdout)[-200:])
    p = _git("push", "origin", "HEAD:main")
    if p.returncode != 0:
        raise RuntimeError("git push failed: " + (p.stderr or p.stdout)[-200:])


def _close(token, number, ok: bool, note: str):
    h = _h(token)
    requests.post(f"{API}/issues/{number}/comments", headers=h, timeout=30, json={"body": note[:1000]})
    requests.patch(f"{API}/issues/{number}", headers=h, timeout=30,
                   json={"state": "closed", "state_reason": "completed" if ok else "not_planned"}).raise_for_status()


def work(cap: int = 2):
    from canslim import autobrief, db, stockchart
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 2 * 3600:
        return                                            # another worker is on it
    token = datapack._token()
    todo = list(reversed(requests_list(token)))           # oldest first
    if not todo:
        return
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(str(os.getpid()))
    try:
        c = db.connect()
        c.executescript(autobrief.SCHEMA)
        today = date.today().isoformat()
        done_today = c.execute("SELECT COUNT(*) FROM brief_runs WHERE date=? AND reason='site request'",
                               (today,)).fetchone()[0]
        known = stockchart.universe()
        exe = autobrief.claude_exe()
        for r in todo[:cap]:
            sym, num = r["symbol"], r["number"]
            if sym not in known:
                _close(token, num, False, f"{sym} is not a symbol the scanner has prices for.")
                continue
            if done_today >= MAX_PER_DAY:
                _log(f"daily cap of {MAX_PER_DAY} reached; {sym} waits until tomorrow")
                break
            if not exe:
                _log("Claude Code CLI not found; requests stay queued")
                break
            if autobrief.brief_info(sym)[0] == today:     # written today already (e.g. push failed last time)
                status, secs, note = "ok", 0, ""
            else:
                _log(f"{sym}: writing requested brief (#{num})...")
                LOCK.touch()
                try:
                    _ensure_chrome()
                    status, secs, note = autobrief.run_one(exe, sym)
                except Exception as e:
                    status, secs, note = "failed", 0, str(e)[:200]
                _, sug, tot = autobrief.brief_info(sym)
                c.execute("INSERT INTO brief_runs VALUES(?,?,?,?,?,?,?,?)",
                          (today, sym, "site request", status, secs, sug, tot, note))
                c.commit()
                done_today += 1
            if status != "ok":
                _log(f"{sym}: {status} - {note[:150]}")
                _close(token, num, False, f"Could not write the brief: {status}.")
                continue
            try:
                _publish(sym)
            except Exception as e:                        # brief is on disk; retried on the next run
                _log(f"{sym}: brief written but not published ({e}); will retry")
                continue
            _, sug, tot = autobrief.brief_info(sym)
            _close(token, num, True, f"Brief written: suggested conviction {sug}/5, checklist {tot}/24.")
            _log(f"{sym}: brief published in {secs // 60} min, suggested {sug}/5, checklist {tot}/24")
        c.close()
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["work"]:
        work()
    elif sys.argv[1:] == ["list"]:
        for r in requests_list(datapack._token(), state="all"):
            print(r)
    else:
        sys.exit("usage: python -m canslim.briefreq work|list")
