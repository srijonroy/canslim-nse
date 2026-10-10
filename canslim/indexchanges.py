"""NSE index inclusions / exclusions from NSE Indices press releases (niftyindices.com/Press_Release).

Semi-annual reviews are announced around late January-February and late July-August. File names are
ind_prsDDMMYYYY.pdf (sometimes with _1/_2), so every day in those windows is tried. Each release is parsed
into (announce date, effective date, index, included/excluded, symbol).

Files: data/events/index_pr/*.pdf, data/events/index_changes.csv

usage: python -m canslim.indexchanges
"""
import io
import re
import time
from pathlib import Path

import pandas as pd
import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "events" / "index_pr"
URL = "https://niftyindices.com/Press_Release/ind_prs{}.pdf"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}
BROAD = ["Nifty 50", "Nifty Next 50", "Nifty 100", "Nifty 200", "Nifty 500", "Nifty Midcap 150",
         "Nifty Midcap 100", "Nifty Midcap 50", "Nifty Smallcap 250", "Nifty Smallcap 100", "Nifty Smallcap 50"]


def download():
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update(H)
    today = pd.Timestamp.today()
    for yr in range(2016, today.year + 1):
        for a, b in [(f"{yr}-01-15", f"{yr}-03-10"), (f"{yr}-07-15", f"{yr}-09-10")]:
            found = 0
            for d in pd.date_range(a, min(pd.Timestamp(b), today)):
                for suf in ["", "_1", "_2"]:
                    name = f"{d:%d%m%Y}{suf}"
                    f = OUT / f"{name}.pdf"
                    if f.exists():
                        found += 1
                        continue
                    try:
                        r = s.get(URL.format(name), timeout=40)
                    except Exception:
                        time.sleep(3)
                        continue
                    if r.status_code == 200 and r.content[:4] == b"%PDF":
                        f.write_bytes(r.content)
                        found += 1
                        print(f"  found {name}", flush=True)
                    time.sleep(0.25)
            print(f"{yr} {a[5:7]}: {found} releases", flush=True)


def norm_index(h: str):
    h = re.sub(r"\s+", " ", h).strip()
    h = re.sub(r"(?i)^nifty\s?", "Nifty ", h)
    for name in sorted(BROAD, key=len, reverse=True):
        if re.fullmatch(re.escape(name).replace(r"\ ", r"\s?") + r"(\s+index)?\s*\**", h, flags=re.I):
            return name
    return None


def parse(f: Path) -> list[dict]:
    text = "\n".join(p.extract_text() or "" for p in PdfReader(f).pages)
    m = re.match(r"(\d{2})(\d{2})(\d{4})", f.stem)
    ann = pd.Timestamp(f"{m[3]}-{m[2]}-{m[1]}")
    em = re.search(r"effective from ([A-Z][a-z]+ \d{1,2}, ?\d{4})", text)
    eff = pd.to_datetime(em[1].replace(", ", ",").replace(",", ", "), errors="coerce") if em else pd.NaT
    rows, index, action = [], None, None
    for line in text.splitlines():
        t = line.strip()
        hm = re.match(r"^(?:\d+\)|[a-z]\))\s*(.+)$", t)
        if hm and "nifty" in hm[1].lower():
            index = norm_index(hm[1])
            action = None
            continue
        if re.search(r"being excluded", t, re.I):
            action = "excluded"
            continue
        if re.search(r"being included", t, re.I):
            action = "included"
            continue
        sm = re.match(r"^\d+\s+.+?\s([A-Z0-9&\-]{2,20})\s*\*?$", t)
        if sm and index and action:
            rows.append({"announced": ann, "effective": eff, "index": index, "action": action, "symbol": sm[1],
                         "file": f.name})
    return rows


def main():
    download()
    rows = []
    for f in sorted(OUT.glob("*.pdf")):
        try:
            rows += parse(f)
        except Exception as e:
            print(f"  parse failed {f.name}: {e}", flush=True)
    d = pd.DataFrame(rows).drop_duplicates(["announced", "index", "action", "symbol"])
    d.to_csv(OUT.parent / "index_changes.csv", index=False)
    print(d.groupby(["index", "action"]).size().to_string())
    print(f"{len(d)} changes from {d.file.nunique()} releases -> data/events/index_changes.csv")


if __name__ == "__main__":
    main()
