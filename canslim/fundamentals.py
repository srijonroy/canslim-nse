"""Fundamentals from Screener.in company pages, fetched through the logged-in
debuggable Chrome (port 9222). One JSON per symbol in data/fundamentals/.

Keeps full history as shown on the page (~13 quarters, ~12 years), which is
what the point-in-time backtest needs. Refresh weekly; be gentle (1 req/s).

usage: python -m canslim.fundamentals [--max-age-days 7] [--limit N] [SYMBOL ...]
"""
import argparse
import io
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
FUND = ROOT / "data" / "fundamentals"
MIN_INTERVAL = 1.3        # Screener tolerates ~48 req/min; stay under


def _num(x):
    if pd.isna(x):
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _table(soup, section: str) -> dict:
    """{row label: {column label: value}} for a Screener section table."""
    t = soup.select_one(f"section#{section} table")
    if t is None:
        return {}
    df = pd.read_html(io.StringIO(str(t)))[0]
    df = df.rename(columns={df.columns[0]: "label"})
    df["label"] = df["label"].astype(str).str.replace("+", "", regex=False).str.strip()
    cols = [c for c in df.columns if c != "label"]
    return {r["label"]: {c: _num(r[c]) for c in cols} for _, r in df.iterrows()}


CHARTS = {"q_sales_npm": "Quarter Sales-GPM-OPM-NPM", "ttm_eps": "EPS"}


def fetch_history(page, company_id: str, consolidated: bool) -> dict:
    """Long history from Screener's chart API: quarterly sales + margins since ~2011,
    and TTM EPS stamped on each result announcement date (point-in-time)."""
    out = {}
    for key, q in CHARTS.items():
        time.sleep(MIN_INTERVAL)
        u = (f"/api/company/{company_id}/chart/?q={quote(q)}&days=10000"
             f"&consolidated={'true' if consolidated else 'false'}")
        r = page.evaluate("u => fetch(u).then(r => r.ok ? r.json() : null).catch(() => null)", u)
        for ds in (r or {}).get("datasets", []):
            out[ds["metric"]] = ds["values"]
    return out


def parse(html: str) -> dict:
    s = BeautifulSoup(html, "lxml")
    q, pl, bs = _table(s, "quarters"), _table(s, "profit-loss"), _table(s, "balance-sheet")
    sh, ra = _table(s, "shareholding"), _table(s, "ratios")
    top = {}
    for li in s.select("#top-ratios li"):
        name = li.select_one(".name")
        val = li.select_one(".number")
        if name and val:
            top[name.get_text(strip=True)] = _num(val.get_text(strip=True))
    ind = [a.get_text(strip=True) for a in s.select("section#peers a[href*='/market/']")]
    cid = s.select_one("[data-company-id]")
    return {"company_id": cid["data-company-id"] if cid else None, "quarters": q, "annual": pl, "balance": bs, "shareholding": sh,
            "ratios": ra, "top": top, "industry": ind}


def _has_data(d: dict) -> bool:
    eps = d["quarters"].get("EPS in Rs", {})
    return sum(v is not None for v in eps.values()) >= 4


def screener_name(sym: str) -> str:
    """NSE:ABC-EQ -> ABC"""
    return sym.split(":")[-1].rsplit("-", 1)[0]


def path_for(name: str) -> Path:
    return FUND / (name.replace("&", "and") + ".json")


def fetch(page, name: str) -> dict | None:
    for suffix in ("consolidated/", ""):
        time.sleep(MIN_INTERVAL)
        url = f"/company/{quote(name)}/{suffix}"
        res = page.evaluate("u => fetch(u).then(r => [r.status, r.text()]).then(a => Promise.all(a))", url)
        status, html = res
        if status == 429:
            print(f"  429 on {name}; cooling down 90s", flush=True)
            time.sleep(90)
            return fetch(page, name)
        if status != 200:
            continue
        d = parse(html)
        if _has_data(d):
            if d.get("company_id"):
                d["history"] = fetch_history(page, d["company_id"], suffix == "consolidated/")
            d.update(symbol=name, basis=suffix.strip("/") or "standalone",
                     fetched=datetime.now().isoformat(timespec="seconds"))
            return d
    return None


def load(name: str) -> dict | None:
    p = path_for(name)
    return json.loads(p.read_text()) if p.exists() else None


def update(names: list, max_age_days: float = 7) -> None:
    from playwright.sync_api import sync_playwright
    FUND.mkdir(parents=True, exist_ok=True)
    t0, done, miss = time.time(), 0, []
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = b.contexts[0]
        page = next((x for x in ctx.pages if "screener.in" in x.url), None)
        if page is None:
            page = ctx.new_page()
            page.goto("https://www.screener.in/")
        skipped = 0
        for i, n in enumerate(names, 1):
            f = path_for(n)
            if f.exists() and time.time() - f.stat().st_mtime < max_age_days * 86400                     and "history" in json.loads(f.read_text()):
                skipped += 1
                continue
            try:
                d = fetch(page, n)
            except Exception as e:  # network hiccup / page navigated -- skip, next run retries
                print(f"  {n}: {e}", flush=True)
                d = None
            if d is None:
                miss.append(n)
            else:
                f.write_text(json.dumps(d))
                done += 1
            el = time.time() - t0
            left = len(names) - i
            rate = el / max(done + len(miss), 1)
            print(f"[{i}/{len(names)}] {n:<14} {'ok' if d else 'MISSING'}  fetched={done} "
                  f"missing={len(miss)} already-had={skipped}  eta {rate * left / 60:.0f}m", flush=True)
    (FUND / "_missing.txt").write_text("\n".join(miss))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--max-age-days", type=float, default=7)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.symbols:
        names = a.symbols
    else:
        from canslim.prices import universe
        syms = universe()
        # most liquid first (today's traded value via Fyers quotes), so research can start early
        try:
            from canslim.fyers_auth import get_client
            fy, val = get_client(), {}
            for i in range(0, len(syms), 50):
                r = fy.quotes({"symbols": ",".join(syms[i:i + 50])})
                for d in r.get("d", []):
                    val[d["n"]] = (d["v"].get("volume") or 0) * (d["v"].get("lp") or 0)
                time.sleep(0.4)
            syms.sort(key=lambda s: -val.get(s, 0))
        except Exception as e:
            print("liquidity ordering skipped:", e)
        names = [screener_name(s) for s in syms]
        if a.limit:
            names = names[: a.limit]
    print(len(names), "companies", flush=True)
    update(names, a.max_age_days)
