"""Preferential issues: download announcements from BSE (2016+) and NSE (structured, mid-2023+).

BSE: api.bseindia.com AnnSubCategoryGetData, one company per call, at most one calendar year per call
(longer ranges return nothing). Every announcement is fetched and only fund-raising ones are kept
(headline/subject mentions preferential, warrants, QIP or raising funds). The first public notice of an
issue is usually 'Board Meeting Intimation' (board will consider) or 'Outcome of Board Meeting' /
'Preferential Issue' (board approved), so NEWS_DT of those is the point-in-time date.

NSE: nseindia.com/api/corporate-further-issues-pref, index FIPREFIP (in-principle approval: board
resolution date, allottee category, amount) and FIPREFLS (listing: allotment date, shares, price).
Starts Apr 2023.

Files: data/pref/bse/<SYM>.json {"years_done": [...], "rows": [...]}, data/pref/nse_ip.json, nse_ls.json

usage: python -m canslim.prefissue --bse [--workers 4] [--syms A,B]
       python -m canslim.prefissue --nse
"""
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from canslim.shp import API, _s, bse_codes

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "pref"
FIRST_YEAR = 2016
KEY = re.compile(r"preferential|warrant|\bqip\b|qualified institution|rais\w* (of )?(funds|capital)|fund ?rais",
                 re.I)
FIELDS = ["NEWS_DT", "CATEGORYNAME", "SUBCATNAME", "HEADLINE", "NEWSSUB", "ATTACHMENTNAME", "NEWSID"]


def _page(code, a, b, p):
    u = (API + f"AnnSubCategoryGetData/w?pageno={p}&strCat=-1&strPrevDate={a}&strScrip={code}"
         f"&strSearch=P&strToDate={b}&strType=C&subcategory=-1")
    for i in range(4):
        try:
            j = _s.get(u, timeout=60).json()
            return j.get("Table") or [], (j.get("Table1") or [{"ROWCNT": 0}])[0]["ROWCNT"]
        except Exception:
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"BSE failed {code} {a} p{p}")


def year_rows(code, yr):
    a, b = f"{yr}0101", f"{yr}1231"
    rows, p, total = [], 1, None
    while True:
        t, total = _page(code, a, b, p)
        rows += t
        if not t or len(rows) >= total:
            break
        p += 1
        time.sleep(0.2)
    keep = [{k: x.get(k) for k in FIELDS} for x in rows
            if KEY.search(f"{x.get('HEADLINE') or ''} {x.get('NEWSSUB') or ''} {x.get('SUBCATNAME') or ''}")]
    return keep, len(rows)


def fetch_bse(sym, code) -> tuple[int, int]:
    f = OUT / "bse" / f"{sym}.json"
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"years_done": [], "rows": []}
    this_year = pd.Timestamp.today().year
    new = seen = 0
    for yr in range(FIRST_YEAR, this_year + 1):
        if yr in d["years_done"] and yr != this_year:
            continue
        keep, n = year_rows(code, yr)
        seen += n
        ids = {r["NEWSID"] for r in d["rows"]}
        add = [r for r in keep if r["NEWSID"] not in ids]
        d["rows"] += add
        new += len(add)
        if yr != this_year:
            d["years_done"].append(yr)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return new, seen


def nse_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 "
                      "Safari/537.36", "Accept": "application/json,text/plain,*/*",
                      "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-PREF"})
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-PREF", timeout=30)
    return s


def fetch_nse():
    s = nse_session()
    for idx, name in [("FIPREFIP", "nse_ip"), ("FIPREFLS", "nse_ls")]:
        rows = []
        for m in pd.date_range("2023-01-01", pd.Timestamp.today() + pd.offsets.MonthEnd(0), freq="MS"):
            a, b = m.strftime("%d-%m-%Y"), (m + pd.offsets.MonthEnd(0)).strftime("%d-%m-%Y")
            for i in range(3):
                try:
                    r = s.get(f"https://www.nseindia.com/api/corporate-further-issues-pref?index={idx}"
                              f"&from_date={a}&to_date={b}", timeout=40)
                    rows += r.json().get("data", [])
                    break
                except Exception:
                    time.sleep(3 * (i + 1))
                    s = nse_session()
            print(f"  NSE {idx} {m:%b %Y}: {len(rows)} so far", flush=True)
            time.sleep(0.7)
        seen, uniq = set(), []
        for r in rows:
            k = (r.get("appId"), r.get("stage"))
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        (OUT / f"{name}.json").write_text(json.dumps(uniq, ensure_ascii=False), encoding="utf-8")
        print(f"NSE {idx}: {len(uniq)} records -> {name}.json", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bse", action="store_true")
    ap.add_argument("--nse", action="store_true")
    ap.add_argument("--syms")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    (OUT / "bse").mkdir(parents=True, exist_ok=True)
    if a.nse:
        fetch_nse()
    if not a.bse:
        return
    codes = bse_codes()
    if a.syms:
        syms = a.syms.split(",")
    else:
        from canslim import tune
        U = tune.cached_build()["U"]
        syms = list(U.columns[U.loc[f"{FIRST_YEAR}":].any()])      # liquid at some point since 2016
    this_year = pd.Timestamp.today().year
    todo = []
    for s in syms:
        f = OUT / "bse" / f"{s}.json"
        if f.exists() and set(range(FIRST_YEAR, this_year)) <= set(json.loads(f.read_text(encoding="utf-8"))["years_done"]):
            continue
        todo.append(s)
    missing = [s for s in todo if s not in codes]
    todo = [s for s in todo if s in codes]
    print(f"{len(syms)} symbols, {len(todo)} to fetch, {len(missing)} without a BSE code: {missing[:15]}", flush=True)
    t0, done = time.time(), 0

    def one(s):
        try:
            return s, fetch_bse(s, codes[s]), None
        except Exception as e:
            return s, (0, 0), str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for s, (new, seen), err in ex.map(one, todo):
            done += 1
            print(f"[{done}/{len(todo)}] {s:<12} {seen:>5} announcements, {new:>3} fund-raising kept"
                  + (f"  ERROR {err}" if err else "") + f"  ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
