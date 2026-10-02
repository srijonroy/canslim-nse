"""Fetch a company's documents for a research brief (no API: Claude Code reads them via the /brief skill).

Downloads from the links on the company's Screener page (logged-in Chrome on :9222) into
data/research/companies/<SYM>/:
  docs/<YYYY-MM>_transcript.pdf/.txt   last N earnings-call transcripts
  docs/<YYYY-MM>_ppt.pdf/.txt          matching investor presentations
  docs/annual_report_<YYYY>.pdf/.txt   latest annual report
  facts.md                             numbers we already hold (quarters, balance sheet, ratios, shareholding,
                                       rule status), pre-filled for the checklist
  sources.md                           every document with its URL, for citations
Already-downloaded files are skipped.

usage: python -m canslim.docs SYM [--concalls 4] [--annual 1]
"""
import argparse
import io
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
COMPANIES = ROOT / "data" / "research" / "companies"
FUND = ROOT / "data" / "fundamentals"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0 Safari/537.36", "Referer": "https://www.bseindia.com/"}
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def screener_html(sym: str) -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        pg = next((x for x in b.contexts[0].pages if "screener.in" in x.url), None) or b.contexts[0].new_page()
        if "screener.in" not in pg.url:
            pg.goto("https://www.screener.in/")
        for suffix in ("consolidated/", ""):
            status, html = pg.evaluate("u => fetch(u).then(r => Promise.all([r.status, r.text()]))",
                                       f"/company/{sym}/{suffix}")
            if status == 200 and 'id="documents"' in html:
                return html
            time.sleep(1.5)
    raise RuntimeError(f"Screener page not found for {sym}")


def links(html: str) -> dict:
    s = BeautifulSoup(html, "html.parser").find(id="documents")
    out = {"concalls": [], "annual": [], "ratings": []}
    for li in s.select(".concalls li"):
        txt = li.get_text(" | ", strip=True)
        m = re.match(r"([A-Z][a-z]{2}) (\d{4})", txt)
        if not m:
            continue
        row = {"period": f"{m.group(2)}-{MONTHS[m.group(1)]:02d}", "label": f"{m.group(1)} {m.group(2)}"}
        for a in li.find_all("a"):
            t = a.get_text(strip=True).lower()
            if t in ("transcript", "ppt") and a.get("href"):
                row[t] = a["href"]
        out["concalls"].append(row)
    for a in s.find_all("a"):
        t = a.get_text(" ", strip=True)
        m = re.match(r"(?:Financial Year|Annual Report)\s*(\d{4})", t)
        if m and a.get("href"):
            out["annual"].append({"year": m.group(1), "url": a["href"]})
        elif t.startswith("Rating update") and a.get("href"):
            out["ratings"].append({"label": t, "url": a["href"]})
    return out


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(data))
    parts = []
    for i, p in enumerate(rd.pages, 1):
        parts.append(f"\n\n--- page {i} ---\n{p.extract_text() or ''}")
    return "".join(parts)


def download(url: str, dest: Path) -> str:
    """Save pdf + extracted txt. Returns a status string."""
    txt = dest.with_suffix(".txt")
    if txt.exists():
        return "cached"
    r = requests.get(url, headers=UA, timeout=90)
    if r.status_code != 200 or r.content[:4] != b"%PDF":
        return f"failed ({r.status_code}, {r.headers.get('content-type')})"
    dest.write_bytes(r.content)
    t = pdf_text(r.content)
    txt.write_text(t, encoding="utf-8")
    return f"ok ({len(t):,} chars)" + (" - little text, may be a scanned PDF" if len(t) < 2000 else "")


def series(sec: dict, key: str, n: int) -> list:
    v = (sec or {}).get(key) or {}
    return list(v.items())[-n:]


def table(sec: dict, keys: list, n: int) -> str:
    cols = [p for p, _ in series(sec, keys[0], n)]
    if not cols:
        return "_not available_\n"
    lines = ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for k in keys:
        d = dict((sec or {}).get(k) or {})
        if d:
            lines.append(f"| {k} | " + " | ".join("" if d.get(c) is None else f"{d.get(c):,.1f}".rstrip("0").rstrip(".")
                                                   for c in cols) + " |")
    return "\n".join(lines) + "\n"


def facts(sym: str) -> str:
    f = FUND / f"{sym.replace('&', 'and')}.json"
    out = [f"# {sym} — facts we already hold\n", f"_Generated {datetime.now():%Y-%m-%d %H:%M} by canslim.docs. "
           "Numbers in Rs crore unless stated. Source: Screener.in data in data/fundamentals._\n"]
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append(f"**Industry:** {' > '.join(dict.fromkeys(d.get('industry') or []))}  \n**Basis:** {d.get('basis')}, "
                   f"fetched {d.get('fetched')}  \n**Snapshot:** " +
                   ", ".join(f"{k} {v}" for k, v in (d.get("top") or {}).items()) + "\n")
        out.append("## Last 8 quarters\n" + table(d.get("quarters"), ["Sales", "Operating Profit", "OPM %",
                                                                       "Other Income", "Interest", "Net Profit"], 8))
        q = d.get("quarters") or {}
        oi, pbt = dict(q.get("Other Income") or {}), dict(q.get("Profit before tax") or {})
        share = [(p, oi[p] / pbt[p] * 100) for p in list(pbt)[-4:] if p in oi and pbt.get(p)]
        if share:
            out.append("Other income as % of profit before tax (last 4 qtrs): " +
                       ", ".join(f"{p} {v:.0f}%" for p, v in share) + "  \n_High = earnings not from operations (Q4)._\n")
        out.append("## Annual\n" + table(d.get("annual"), ["Sales", "Operating Profit", "OPM %", "Net Profit",
                                                            "Dividend Payout %"], 6))
        out.append("## Balance sheet\n" + table(d.get("balance"), ["Equity Capital", "Reserves", "Borrowings",
                                                                    "CWIP", "Fixed Assets", "Total Assets"], 6) +
                   "_Rising CWIP = capacity being built (Q1). A jump in equity capital is either dilution (Q6) or a bonus issue / split (harmless) -- check the annual report._\n")
        out.append("## Efficiency\n" + table(d.get("ratios"), ["Debtor Days", "Inventory Days", "Cash Conversion Cycle",
                                                                "ROCE %"], 6) +
                   "_Debtor/inventory days rising faster than sales = growth may not be converting to cash (Q5)._\n")
        out.append("## Shareholding % (last 8 quarters)\n" + table(d.get("shareholding"), ["Promoters", "FIIs", "DIIs",
                                                                                            "Public", "No. of Shareholders"], 8) +
                   "_Promoters falling = red-flag check (Q8). FIIs+DIIs rising = institutional sponsorship (Q11)._\n")
    else:
        out.append("_No fundamentals file for this symbol._\n")
    dbf = ROOT / "data" / "canslim.db"
    if dbf.exists():
        c = sqlite3.connect(dbf)
        r = c.execute("SELECT date, close, rs, sys_rank, n_fail, failed, group_rank FROM snapshot WHERE symbol=? "
                      "ORDER BY date DESC LIMIT 1", (sym,)).fetchone()
        lists = c.execute("SELECT list, MIN(date), MAX(date), COUNT(*) FROM picks WHERE symbol=? GROUP BY list",
                          (sym,)).fetchall()
        c.close()
        out.append("## System status\n")
        if r:
            out.append(f"As of {r[0]}: close {r[1]:,.2f}, RS {r[2]:.0f}, system rank "
                       f"{r[3] if r[3] is not None else 'not passing'}, industry group rank {r[6]}. "
                       f"{'Passes every rule.' if not r[4] else 'Fails: ' + (r[5] or '')}\n")
        else:
            out.append("Not in the system's universe on any stored day.\n")
        for l_, a, b, n in lists:
            out.append(f"- On the {l_} list {n} day(s), {a} to {b}\n")
    return "\n".join(out)


def fetch(sym: str, n_concalls: int = 4, n_annual: int = 1) -> Path:
    sym = sym.upper()
    base = COMPANIES / sym
    (base / "docs").mkdir(parents=True, exist_ok=True)
    L = links(screener_html(sym))
    src = [f"# {sym} — sources\n", f"_Fetched {datetime.now():%Y-%m-%d %H:%M}. Cite these by file name in the brief._\n",
           "| File | Document | Status | URL |", "|---|---|---|---|"]
    jobs, seen, n_tr = [], set(), 0
    for i, cc in enumerate(L["concalls"][:12]):
        # newest n_concalls entries, then keep looking back (up to 12) until at least 2 transcripts are found
        if i >= n_concalls and n_tr >= 2:
            break
        for kind in ("transcript", "ppt"):
            url = cc.get(kind)
            if not url or url in seen or (i >= n_concalls and kind == "ppt"):
                continue
            seen.add(url)
            n_tr += kind == "transcript"
            jobs.append((f"{cc['period']}_{kind}.pdf", f"{cc['label']} earnings call {kind}", url))
    for ar in L["annual"][:n_annual]:
        jobs.append((f"annual_report_{ar['year']}.pdf", f"Annual report {ar['year']}", ar["url"]))
    for name, what, url in jobs:
        try:
            stt = download(url, base / "docs" / name)
        except Exception as e:
            stt = f"failed ({e.__class__.__name__})"
        print(f"  {name:<32} {stt}", flush=True)
        src.append(f"| docs/{name.replace('.pdf', '.txt')} | {what} | {stt} | {url} |")
        time.sleep(1.0)
    if L["ratings"]:
        src.append("\n## Credit rating notes (links only)\n" + "\n".join(f"- {r['label']}: {r['url']}" for r in L["ratings"][:4]))
    if not L["concalls"]:
        src.append("\n_No earnings calls listed on Screener. Small companies often don't hold them._")
    (base / "sources.md").write_text("\n".join(src) + "\n", encoding="utf-8")
    (base / "facts.md").write_text(facts(sym), encoding="utf-8")
    print(f"{sym}: {len(L['concalls'])} concalls listed, {len(L['annual'])} annual reports listed -> {base}")
    return base


def search(sym: str, terms: list, file_glob: str = "annual_report_*.txt", n: int = 3, width: int = 260) -> str:
    """Keyword-in-context search over a company's downloaded document text (fast on 1M-char annual reports)."""
    out = []
    for f in sorted((COMPANIES / sym.upper() / "docs").glob(file_glob)):
        t = re.sub(r"\s+", " ", f.read_text(encoding="utf-8"))
        out.append(f"##### {f.name} ({len(t):,} chars)")
        for k in terms:
            hits = [m.start() for m in re.finditer(re.escape(k), t, flags=re.I)]
            out.append(f"=== {k}: {len(hits)} hits")
            for h in hits[:n]:
                out.append("   ..." + t[max(0, h - width):h + width])
    return "\n".join(out)


def read(sym: str, name: str, start: int = 0, length: int = 25000) -> str:
    """Cleaned text of one document (page markers and repeated headers squeezed), in chunks."""
    t = (COMPANIES / sym.upper() / "docs" / name).read_text(encoding="utf-8")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return f"[{name}: chars {start:,}-{min(start + length, len(t)):,} of {len(t):,}]\n" + t[start:start + length]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--concalls", type=int, default=4)
    ap.add_argument("--annual", type=int, default=1)
    ap.add_argument("--search", help="terms separated by |, e.g. 'pledge|related party|qualified opinion'")
    ap.add_argument("--in", dest="file_glob", default="annual_report_*.txt", help="which docs to search (glob)")
    ap.add_argument("--read", help="print a document's cleaned text, e.g. 2026-08_transcript.txt")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--length", type=int, default=25000)
    a = ap.parse_args()
    if a.search:
        print(search(a.symbol, [x.strip() for x in a.search.split("|") if x.strip()], a.file_glob))
    elif a.read:
        print(read(a.symbol, a.read, a.start, a.length))
    else:
        fetch(a.symbol, a.concalls, a.annual)
