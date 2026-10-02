"""Institutional sponsorship history (book rule 14) from BSE shareholding-pattern filings.

Source: BSE's public JSON API behind bseindia.com/corporates/shppublicshareholder (no login, no browser).
Coverage: every quarter from Dec 2015 (BSE qtr code 88, first SEBI-LODR format) to now, for any BSE-listed
company, including the number of holders per category -- O'Neil's "number of funds owning the stock".
Point-in-time: each filing carries its authorisation date (Fld_AuthoriseDate); a quarter is only "known" from
that date (fallback: quarter end + 21 days, the SEBI deadline), so backtests have no look-ahead.

Stored: data/shp/<SYM>.json  {qcode: {"filed": "YYYY-MM-DD"|None, "rows": {fld_id: [holders, pct]}}}
Category ids (stable across the 2016 and 2023 formats):
  10041 mutual funds | 10065 all institutions (old) | 10139 + 10141 domestic + foreign institutions (new)
  10045 FPI (old)    | 10120 + 10121 FPI cat I + II (new)

usage: python -m canslim.shp --pool          (stocks that ever passed the current rules)
       python -m canslim.shp --syms MCX,RPEL
       python -m canslim.shp --all           (every stock with fundamentals; ~1.5 h)
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "shp"
API = "https://api.bseindia.com/BseIndiaAPI/api/"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
     "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com",
     "Accept": "application/json, text/plain, */*"}
FIRST_Q = 88                       # Dec 2015
KEEP = {10041, 10045, 10065, 10120, 10121, 10139, 10141}
_s = requests.Session()
_s.headers.update(H)


def q_end(q: int) -> pd.Timestamp:
    return pd.Timestamp("2015-12-31") + pd.offsets.QuarterEnd(q - FIRST_Q)


def last_q(today=None) -> int:
    """Code of the last completed quarter (Sep 2026 = 131 on any day in Oct-Dec 2026)."""
    t = pd.Timestamp(today or pd.Timestamp.today())
    return FIRST_Q + (t.year - 2016) * 4 + t.quarter - 1


def bse_codes() -> dict:
    """NSE symbol -> BSE scrip code, matched on ISIN."""
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "bse_scrips.json"
    if not f.exists() or time.time() - f.stat().st_mtime > 30 * 86400:
        r = _s.get(API + "ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=", timeout=120)
        r.raise_for_status()
        f.write_text(r.text, encoding="utf-8")
    isin = {x["ISIN_NUMBER"]: x["SCRIP_CD"] for x in json.loads(f.read_text(encoding="utf-8")) if x.get("ISIN_NUMBER")}
    m = pd.read_csv(ROOT / "data" / "NSE_CM.csv", header=None, usecols=[5, 13], names=["isin", "sym"])
    return {s: isin[i] for i, s in zip(m["isin"], m["sym"]) if i in isin}


def _get(code, q):
    for i in range(3):
        try:
            r = _s.get(API + f"Corp_shpSec_SHPPubShold_ng/w?SCRIPCODE={code}&QtrCode={q}.00", timeout=30)
            j = r.json()
            filed = ((j.get("Table") or [{}])[0].get("Fld_AuthoriseDate") or "")[:10] or None
            rows = {x["Fld_Id"]: [x["Fld_NoOfShareHolders"] or 0, float(x["Fld_TotalPercentageOf_A_B_C2"] or 0)]
                    for x in j.get("Table1", []) if x.get("Fld_Id") in KEEP and x.get("Fld_ShareHolderName") is None}
            return {"filed": filed, "rows": rows}
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def fetch(sym: str, code: str) -> int:
    f = OUT / f"{sym}.json"
    d = json.loads(f.read_text()) if f.exists() else {}
    new = 0
    for q in range(FIRST_Q, last_q() + 1):
        k = str(q)
        if k in d and (d[k]["rows"] or q < last_q() - 2):   # keep filled quarters; retry empty recent ones
            continue
        r = _get(code, q)
        if r is not None:
            d[k] = r
            new += 1
    f.write_text(json.dumps(d))
    return new


def history(sym: str) -> pd.DataFrame:
    """One row per filed quarter: holders and % for institutions, mutual funds, FPIs; 'known' = date usable."""
    f = OUT / f"{sym}.json"
    if not f.exists():
        return pd.DataFrame()
    out = []
    for k, v in json.loads(f.read_text()).items():
        r = {int(i): x for i, x in v["rows"].items()}
        if not r:
            continue
        g = lambda *ids: [sum(r[i][0] for i in ids if i in r), round(sum(r[i][1] for i in ids if i in r), 2)]
        inst = g(10065) if 10065 in r else g(10139, 10141)
        fpi = g(10045) if 10045 in r else g(10120, 10121)
        qe = q_end(int(k))
        known = max(pd.Timestamp(v["filed"]), qe) if v["filed"] else qe + pd.Timedelta(days=21)
        out.append({"q": qe, "known": known, "inst_n": inst[0], "inst_pct": inst[1],
                    "mf_n": g(10041)[0], "mf_pct": g(10041)[1], "fpi_n": fpi[0], "fpi_pct": fpi[1]})
    return pd.DataFrame(out).sort_values("q").reset_index(drop=True) if out else pd.DataFrame()


def panel(field: str, index: pd.DatetimeIndex, syms) -> pd.DataFrame:
    """Daily point-in-time panel of `field` (or `<field>_chg` = change vs previous filed quarter)."""
    base, chg = (field[:-4], True) if field.endswith("_chg") else (field, False)
    cols = {}
    for s in syms:
        h = history(s)
        if h.empty:
            continue
        v = h[base].diff() if chg else h[base]
        ser = pd.Series(v.values, index=h.known).groupby(level=0).last()
        cols[s] = ser.reindex(index.union(ser.index)).ffill().reindex(index)
    return pd.DataFrame(cols, index=index).reindex(columns=list(syms))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--syms")
    g.add_argument("--pool", action="store_true")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    codes = bse_codes()
    if a.syms:
        syms = a.syms.split(",")
    else:
        from canslim import tune
        lab = tune.Lab()
        if a.pool:
            rules = json.loads((ROOT / "data" / "tune" / "final.json").read_text())["rules"]
            sc = tune.book_score(lab.S, lab.U, lab.has_f, rules)
            syms = list(sc.columns[sc.notna().any()])
        else:
            syms = list(lab.has_f.columns[lab.has_f.any()])
    missing = [s for s in syms if s not in codes]
    syms = [s for s in syms if s in codes]
    print(f"{len(syms)} symbols with a BSE code, {len(missing)} without (NSE-only): {missing[:15]}", flush=True)
    t0, done = time.time(), 0

    def one(s):
        return s, fetch(s, codes[s])
    with ThreadPoolExecutor(a.workers) as ex:
        for s, n in ex.map(one, syms):
            done += 1
            h = history(s)
            last = h.iloc[-1] if len(h) else None
            print(f"[{done}/{len(syms)}] {s:<12} +{n:>2} qtrs, {len(h)} total"
                  + (f", latest {last.q:%b %Y}: {last.inst_n} institutions {last.inst_pct}%, {last.mf_n} MF schemes"
                     if last is not None else "") + f"  ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
