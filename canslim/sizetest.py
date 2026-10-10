"""Check: do large caps take longer to move? Parts 1-2 are descriptive; part 3 is a portfolio test.

Size = market-cap rank on the signal date among stocks we hold prices for (SEBI-style buckets):
  Large = rank 1-100, Mid = 101-250, Small = 251-500, Micro = 501+.
Market cap on a past date = today's share count (Screener market cap / price) x split-adjusted close.
Ignores shares issued or bought back since then, so stocks near a bucket edge may sit in the neighbour.

Two samples, each split 2016-22 / 2023-26 (both periods have been seen in earlier work):
  1) trades: every trade the current system (data/tune/final.json) made
  2) entries: every day a stock joins the passing list after 4+ weeks off it (bigger sample, no slot limits)
     path after the signal: trading days to +20% (close vs signal close), share reaching +20% within 3 / 6
     months, median 3 / 6 / 12-month return, share that fell 20% before rising 20%.
  3) portfolio test, variant "no new buys in the top 100 by market cap" (holdings unaffected).
     Idea came from parts 1-2 on the same data, so a pass is weak evidence.
     Bar (fixed before running, same as earlier tests, judged on 2016-22): Sharpe >= base + 0.03 in BOTH
     halves (16-19, 20-22) and maxDD no worse than base by more than 3 points. 2023-26 reported, not judged.

usage: python -m canslim.sizetest
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tune" / "sizetest"
PERIODS = {"2016-22": tune.TUNE, "2023-26": (tune.HOLD[0], "2026-12-31")}
BUCKETS = [(1, 100, "Large"), (101, 250, "Mid"), (251, 500, "Small"), (501, 10 ** 9, "Micro")]


def share_counts(syms) -> pd.Series:
    out = {}
    for s in syms:
        f = ROOT / "data" / "fundamentals" / f"{s}.json"
        if not f.exists():
            continue
        top = json.loads(f.read_text()).get("top", {})
        mc, px = top.get("Market Cap"), top.get("Current Price")
        if mc and px:
            out[s] = mc / px                      # crore shares
    return pd.Series(out)


def bucket(rank: float) -> str:
    for a, b, name in BUCKETS:
        if a <= rank <= b:
            return name
    return "n/a"


def path_stats(C: np.ndarray, j: int, k: int) -> dict:
    """Forward path of column j from row k (signal close)."""
    p0 = C[k, j]
    fwd = C[k + 1:k + 253, j]
    r = fwd / p0 - 1
    up = np.flatnonzero(r >= 0.20)
    dn = np.flatnonzero(r <= -0.20)
    t_up = int(up[0]) + 1 if len(up) else np.nan     # never within 12 months -> 253 in the summary
    t_dn = int(dn[0]) + 1 if len(dn) else np.nan

    def ret_at(n):
        return r[n - 1] if len(r) >= n and not np.isnan(r[n - 1]) else np.nan
    return {"days_to_20": t_up if not np.isnan(t_up) else (253.0 if len(r) >= 252 else np.nan), "hit20_3m": float(t_up <= 63) if len(r) >= 63 else np.nan,
            "hit20_6m": float(t_up <= 126) if len(r) >= 126 else np.nan,
            "ret_3m": ret_at(63), "ret_6m": ret_at(126), "ret_12m": ret_at(252),
            "fell20_first": float(not np.isnan(t_dn) and (np.isnan(t_up) or t_dn < t_up)) if len(r) >= 126 else np.nan}


def summarize(df: pd.DataFrame, cols: dict) -> pd.DataFrame:
    order = [b[2] for b in BUCKETS]
    g = df.groupby("size")
    t = pd.DataFrame({"n": g.size()})
    for name, (col, fn) in cols.items():
        t[name] = g[col].agg(fn)
    return t.reindex([o for o in order if o in t.index])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    final = json.loads((OUT.parent / "final.json").read_text())
    print("loading data ...", flush=True)
    lab = tune.Lab()
    C = lab.P["close"]
    sh = share_counts(C.columns)
    print(f"  share counts for {len(sh)} of {C.shape[1]} stocks", flush=True)
    mcap = C[sh.index] * sh                       # Rs crore
    mrank = mcap.rank(axis=1, ascending=False)
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    cfg = pf.Config(**final["cfg"])
    Cv, cidx = C.values, {s: i for i, s in enumerate(C.columns)}
    rows = {i: d for i, d in enumerate(C.index)}
    pos = {d: i for i, d in rows.items()}

    # 1) system trades
    trades = []
    for per, (a, b) in PERIODS.items():
        res = lab.run(sc, cfg, period=(a, b))
        t = res.trades.copy()
        t["period"] = per
        trades.append(t)
        print(f"  {per}: {len(t)} trades, CAGR {res.stats['CAGR %']}%", flush=True)
    T = pd.concat(trades, ignore_index=True)
    T["entry_date"], T["exit_date"] = pd.to_datetime(T.entry_date), pd.to_datetime(T.exit_date)
    sig = [C.index[pos[d] - 1] for d in T.entry_date]          # decision close = day before the fill
    T["mcap_cr"] = [mcap.at[d, s] if s in mcap.columns else np.nan for d, s in zip(sig, T.sym)]
    T["rank"] = [mrank.at[d, s] if s in mrank.columns else np.nan for d, s in zip(sig, T.sym)]
    T["size"] = T["rank"].map(lambda r: bucket(r) if r == r else "n/a")
    T["days"] = [pos[x] - pos[e] for e, x in zip(T.entry_date, T.exit_date)]   # trading days held
    # did the trade touch +20% (close) while held?
    T["hit20_held"] = [float(np.nanmax(Cv[pos[e]:pos[x] + 1, cidx[s]] / en) - 1 >= 0.20)
                       for s, e, x, en in zip(T.sym, T.entry_date, T.exit_date, T.entry)]
    T.to_csv(OUT / "trades.csv", index=False)

    # 2) new list entries
    passing = sc.notna()
    prev4 = passing.shift(1).rolling(4, min_periods=1).max().fillna(0).astype(bool)
    new = passing & ~prev4
    ev = []
    for d, row in new.iterrows():
        k = pos.get(d)
        if k is None:
            continue
        for s in row.index[row.values]:
            r = mrank.at[d, s] if s in mrank.columns else np.nan
            ev.append({"date": d, "sym": s, "rank": r, "mcap_cr": mcap.at[d, s] if s in mcap.columns else np.nan,
                       "size": bucket(r) if r == r else "n/a", **path_stats(Cv, cidx[s], k)})
    E = pd.DataFrame(ev)
    E["period"] = np.where(E.date <= pd.Timestamp(tune.TUNE[1]), "2016-22",
                           np.where(E.date >= pd.Timestamp(tune.HOLD[0]), "2023-26", "pre-2016"))
    E = E[E.period != "pre-2016"]
    E.to_csv(OUT / "entries.csv", index=False)

    med, mean = "median", "mean"
    for per in PERIODS:
        t = T[T.period == per]
        print(f"\n=== System trades {per} ===")
        tt = summarize(t, {"median days held": ("days", med), "avg return %": ("ret", mean),
                           "median return %": ("ret", med),
                           "reached +20% while held %": ("hit20_held", mean), "median mcap Cr": ("mcap_cr", med)})
        g = t.groupby("size")
        tt["return per month held %"] = (g.ret.sum() / g.days.sum() * 21).reindex(tt.index)   # pooled
        for c in ["avg return %", "median return %", "return per month held %", "reached +20% while held %"]:
            tt[c] = (tt[c] * 100).round(1)
        tt["median mcap Cr"] = tt["median mcap Cr"].round(0)
        print(tt.to_string())
        tt.to_csv(OUT / f"trades_summary_{per}.csv")
        e = E[E.period == per]
        print(f"\n=== New list entries {per} (path after the signal) ===")
        et = summarize(e, {"median days to +20%": ("days_to_20", med), "+20% within 3m %": ("hit20_3m", mean),
                           "+20% within 6m %": ("hit20_6m", mean), "median 3m %": ("ret_3m", med),
                           "median 6m %": ("ret_6m", med), "median 12m %": ("ret_12m", med),
                           "fell 20% before +20% %": ("fell20_first", mean)})
        for c in et.columns[2:]:
            et[c] = (et[c] * 100).round(1)
        print(et.to_string())
        et.to_csv(OUT / f"entries_summary_{per}.csv")
    # 3) portfolio test
    print("\n=== Portfolio test: no new buys in the top 100 by market cap ===")
    ok = (mrank > 100).reindex(index=sc.index, columns=sc.columns).fillna(True)
    rows = []
    for name, eo in [("base (current)", None), ("no top-100 buys", ok)]:
        for per, (a, b) in PERIODS.items():
            res = lab.run(sc, cfg, period=(a, b), entry_ok=eo)
            row = {"variant": name, "period": per, **res.stats,
                   "avg cash %": round((1 - res.exposure.mean()) * 100, 1)}
            if per == "2016-22":
                for h, (x, y) in tune.HALVES.items():
                    row[f"Sharpe {h}"] = pf.stats(res.equity.loc[x:y])["Sharpe"]
            rows.append(row)
    R = pd.DataFrame(rows)
    print(R.to_string(index=False))
    R.to_csv(OUT / "portfolio.csv", index=False)
    b0, v0 = R.iloc[0], R.iloc[2]
    passed = (all(v0[f"Sharpe {h}"] >= b0[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
              and v0["maxDD %"] >= b0["maxDD %"] - 3)
    print(f"bar: {'PASS' if passed else 'FAIL'}")
    print(f"\nunsized trades: {(T['size'] == 'n/a').sum()}, unsized entries: {(E['size'] == 'n/a').sum()}")
    print(f"written to {OUT}")


if __name__ == "__main__":
    main()
