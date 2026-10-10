"""Event study: what does a stock do around a preferential issue? Descriptive only.

Events: NSE in-principle records (data/pref/nse_ip.json, Apr 2023+), one per company per 90 days.
Day 0 = board resolution date (first trading day on/after it). The outcome is often filed after the close,
so the "buy" is the close of day +1.
  before:  close day -63 -> close day -1 (did it run up before the news?)
  after:   close day +1 -> +21 / +63 / +126 / +252 trading days
Benchmark = median return of all stocks in the same market-cap bucket (sizetest buckets) over the same
window, so a small-cap boom doesn't flatter the result. Excess = event return - benchmark.
Issue price vs market: first NSE listing record for the symbol allotted 0-365 days after the board date
(offer price / close on day 0 - 1). Dilution = amount raised / market cap on day 0.

Caveats: 2023-26 only (one market phase, already seen in other work); 12-month figures only for events up
to Sep 2025; only stocks in our price panel (505 of 824 records); amounts include warrants not yet paid.

usage: python -m canslim.preftest
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import tune
from canslim.sizetest import BUCKETS, bucket, share_counts

ROOT = Path(__file__).resolve().parent.parent
PREF = ROOT / "data" / "pref"
OUT = ROOT / "data" / "research" / "pref"
H = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


def load_events(cols) -> pd.DataFrame:
    ip = pd.DataFrame(json.loads((PREF / "nse_ip.json").read_text(encoding="utf-8")))
    ip["brd"] = pd.to_datetime(ip.dateBrdResoln, format="%d-%b-%Y", errors="coerce")
    ip["amt_cr"] = pd.to_numeric(ip.totalAmtRaised, errors="coerce") / 1e7
    ip = ip[ip.nseSymbol.isin(cols) & ip.brd.notna()].sort_values("brd")
    keep, last = [], {}
    for i, r in ip.iterrows():
        if r.nseSymbol in last and (r.brd - last[r.nseSymbol]).days < 90:
            continue
        last[r.nseSymbol] = r.brd
        keep.append(i)
    ls = pd.DataFrame(json.loads((PREF / "nse_ls.json").read_text(encoding="utf-8")))
    ls["allot"] = pd.to_datetime(ls.dateOfAllotmentOfShares, format="%d-%b-%Y", errors="coerce")
    ls["price"] = pd.to_numeric(ls.offerPricePerSecurity, errors="coerce")
    ev = ip.loc[keep, ["nseSymbol", "brd", "categoryOfAllottee", "considerationBy", "amt_cr"]].rename(
        columns={"nseSymbol": "sym", "categoryOfAllottee": "allottee", "considerationBy": "consideration"})
    price = []
    for s, d in zip(ev.sym, ev.brd):
        m = ls[(ls.nseSymbol == s) & (ls.allot >= d) & (ls.allot <= d + pd.Timedelta(days=365)) & (ls.price > 0)]
        price.append(m.sort_values("allot").price.iloc[0] if len(m) else np.nan)
    ev["offer"] = price
    return ev.reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    print("loading data ...", flush=True)
    B = tune.cached_build()
    C = B["P"]["close"]
    sh = share_counts(C.columns)
    mcap = C[sh.index] * sh
    mrank = mcap.rank(axis=1, ascending=False)
    bmap = mrank.apply(lambda col: col.map(lambda r: bucket(r) if r == r else None))
    ev = load_events(C.columns)
    print(f"  {len(ev)} events in the price panel", flush=True)
    Cv, idx, cidx = C.values, C.index, {s: i for i, s in enumerate(C.columns)}
    bv = bmap.reindex(columns=C.columns).values
    rows = []
    for e in ev.itertuples():
        k0 = idx.searchsorted(e.brd)
        if k0 + 1 >= len(idx):
            continue
        j = cidx[e.sym]
        p0, p1 = Cv[k0, j], Cv[k0 + 1, j]
        b = bv[k0, j]
        same = bv[k0] == b
        r = {"sym": e.sym, "date": idx[k0], "allottee": e.allottee, "consideration": e.consideration,
             "size": b or "n/a", "amt_cr": e.amt_cr, "mcap_cr": mcap.at[idx[k0], e.sym] if e.sym in mcap else np.nan,
             "premium": e.offer / p0 - 1 if e.offer == e.offer and p0 > 0 else np.nan}
        if k0 >= 64:
            pre = Cv[k0 - 1, j] / Cv[k0 - 64, j] - 1
            prem = np.nanmedian((Cv[k0 - 1] / Cv[k0 - 64] - 1)[same]) if b else np.nan
            r["before 3m"], r["before 3m excess"] = pre, pre - prem
        for name, h in H.items():
            if k0 + 1 + h < len(idx):
                ret = Cv[k0 + 1 + h, j] / p1 - 1
                bench = np.nanmedian((Cv[k0 + 1 + h] / Cv[k0 + 1] - 1)[same]) if b else np.nan
                r[name], r[f"{name} excess"] = ret, ret - bench
                if name == "12m" and b:
                    r["bench doubled"] = np.nanmean((Cv[k0 + 1 + h] / Cv[k0 + 1] - 1)[same] >= 1)
        rows.append(r)
    E = pd.DataFrame(rows)
    E["dilution"] = E.amt_cr / E.mcap_cr
    E.to_csv(OUT / "events.csv", index=False)

    def table(by):
        g = E.groupby(by)
        t = pd.DataFrame({"n": g.size()})
        t["before 3m median excess %"] = g["before 3m excess"].median() * 100
        for name in H:
            t[f"{name} n"] = g[f"{name} excess"].count()
            t[f"{name} median excess %"] = g[f"{name} excess"].median() * 100
            t[f"{name} beat %"] = g[f"{name} excess"].apply(lambda x: (x.dropna() > 0).mean() * 100)
        t[f"12m mean excess %"] = g["12m excess"].mean() * 100
        t["12m doubled %"] = g["12m"].apply(lambda x: (x.dropna() >= 1).mean() * 100)
        t["same-size stocks doubled %"] = g["bench doubled"].mean() * 100
        return t.round(1)

    E["all"] = "all events"
    E["dilution band"] = pd.cut(E.dilution, [-1, 0.05, 0.15, 100], labels=["<5%", "5-15%", ">15%"])
    E["price vs market"] = pd.cut(E.premium, [-10, -0.10, 0.0, 10], labels=["discount >10%", "discount 0-10%", "premium"])
    E["size"] = pd.Categorical(E["size"], [b[2] for b in BUCKETS] + ["n/a"])
    E["promoter money"] = np.where(E.allottee.str.contains("Promoter") & ~E.allottee.eq("Non Promoter"),
                                   "promoter in", "non-promoter only")
    E["promoter x dilution"] = E["promoter money"] + " / dilution " + E["dilution band"].astype(str)
    out = []
    for by in ["all", "allottee", "promoter money", "consideration", "size", "dilution band", "price vs market",
               "promoter x dilution"]:
        t = table(by)
        print(f"\n=== by {by} ===")
        print(t.drop(columns=[c for c in t.columns if c.endswith(" n") and c != "12m n"]).to_string())
        out.append(t.assign(split=by))
    pd.concat(out).to_csv(OUT / "summary.csv")
    print(f"\nwritten to {OUT}")


if __name__ == "__main__":
    main()
