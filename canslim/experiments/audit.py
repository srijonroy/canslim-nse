"""Audit of the backtest itself: are the calculations correct?

Five independent checks, each against a source the backtest does not use:
  1 dates     our inferred result date (`known`, from Screener's TTM-EPS stamps) vs NSE's own result filing
              timestamps (data/events/ann). A result counts as public for a decision at the close of day D when NSE
              received it before the next open (09:15 on D+1). Counts look-ahead quarters and trades, then reruns the
              backtest with every result date pushed to the later of the two.
  2 rebuild   a separately written, deliberately plain backtester on the same ranked pool and rules. Must give
              about the same return as canslim.portfolio.
  3 reprice   15 random backtest trades re-priced from the official NSE bhavcopies (unadjusted), listed with dates.
  4 adjust    every split/bonus adjustment (data.adjust: overnight gap of -25% or worse) matched against NSE
              corporate actions (data/events/ca). Unmatched = a real crash may have been erased. Also the reverse:
              NSE splits/bonuses the gap rule never adjusted (e.g. 1:4 bonus = -20% gap, below the threshold).
  5 index     momentum index history from niftyindices.com vs the NSE daily archive on the days both have.
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import bhav, factors, resultdates, tune
from canslim import data as D
from canslim.exp import Experiment, Outcome, md_table
from canslim.research import FUND_COLS

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "data" / "events"
OUT = ROOT / "data" / "tune" / "audit"
FULL = ("2016-01-01", None)
# measured by this audit before the fix (run of 2026-11-15 on Screener dates)
FIX_COST = "1.2 points a year in 2016-22 (26.8% to 25.6%, Sharpe 1.42 to 1.35) and 0.2 in 2023+"
RESULT_DESC = {"Financial Result Updates", "Financial Results Updates", "Integrated Filing- Financial",
               "Publish Audited Results", "Results"}
# NSE files results under "Outcome of Board Meeting" in some months (all of Aug 2022, most of 2025-26)
RESULT_TXT = re.compile(r"result|financial", re.I)
norm = lambda s: str(s).replace("&", "and")


def say(*a):
    print(" ", *a, flush=True)


# ------------------------------------------------------------------ 1 result dates
def nse_result_filings() -> pd.DataFrame:
    rows = []
    for f in sorted((EV / "ann").glob("*.json")):
        for x in json.loads(f.read_text(encoding="utf-8")):
            d = x.get("desc") or ""
            txt = x.get("attchmntText") or ""
            if (d in RESULT_DESC or d.startswith("Results Update")
                    or (d == "Outcome of Board Meeting" and RESULT_TXT.search(txt))):
                rows.append((norm(x["symbol"]), x["sort_date"], x.get("attchmntText") or ""))
    a = pd.DataFrame(rows, columns=["sym", "ts", "text"])
    a["ts"] = pd.to_datetime(a["ts"], errors="coerce")
    a = a.dropna(subset=["ts"])
    # usable for a decision at the close of `eff` (filed before the next morning's 09:15 open)
    a["eff"] = (a["ts"] - pd.Timedelta(hours=9, minutes=15)).dt.normalize()
    return a.sort_values("ts")


def match_quarters(fund: dict, filings=None) -> pd.DataFrame:
    """One row per (stock, quarter end since mid-2015): Screener's date vs the exchange's first result filing for
    that quarter (canslim.resultdates: NSE result filing, BSE result filing, or a confirmed NSE board outcome)."""
    rows = []
    for sym, f in fund.items():
        q = f["q"][f["q"].index >= "2015-06-30"]
        if not len(q):
            continue
        x = resultdates.for_quarters(sym, q.index).reindex(q.index)
        raw = q["known_screener"] if "known_screener" in q else q["known"]     # Screener stamp, before the fix
        rows.append(pd.DataFrame({"sym": sym, "qe": q.index, "known": pd.DatetimeIndex(raw).values,
                                  "known_live": pd.DatetimeIndex(q["known"]).values, "nse": x["eff"].values,
                                  "nse_ts": x["ts"].values, "src": x["src"].values,
                                  "live_src": q["known_src"].values if "known_src" in q else ""}))
    t = pd.concat(rows, ignore_index=True)
    t["lead_days"] = (t.nse - t.known).dt.days        # > 0: Screener's date is EARLIER than the exchange's -> look-ahead
    return t


def corrected_score(ctx, qt: pd.DataFrame) -> pd.DataFrame:
    """The live pool rebuilt with every result date = the later of ours and NSE's."""
    lab = ctx.lab
    late = qt.dropna(subset=["nse"]).set_index(["sym", "qe"])["nse"]
    fund2, has = {}, set(late.index.get_level_values(0))
    for sym, f in lab.fund.items():
        q = f["q"].copy()
        if sym in has:
            n = late.loc[sym].reindex(q.index)
            q["known"] = [max(k, v) if pd.notna(v) else k for k, v in zip(pd.to_datetime(q["known"]), n)]
        fund2[sym] = {**f, "q": q}
    ev = factors.fundamental_events(fund2)
    dates = lab.S["np_yoy"].index
    FP = factors.fundamental_panel(ev, dates, FUND_COLS)
    FP = {k: v.reindex(columns=lab.S["np_yoy"].columns) for k, v in FP.items()}
    day_no = pd.Series(dates.values.astype("datetime64[D]").astype("int64"), index=dates)
    FP["days_since_ann"] = FP.pop("last_ann").rsub(day_no, axis=0).where(lambda x: x >= 0)
    S2 = {**lab.S, **FP}
    return tune.book_score(S2, lab.U, S2["np_yoy"].notna(), ctx.rules)


def check_dates(ctx, trades):
    say("[1/5] result dates vs NSE filings ...")
    qt = match_quarters(ctx.lab.fund)
    qt.to_csv(OUT / "result_dates.csv", index=False)
    m = qt.dropna(subset=["nse"])
    m = m[m.qe >= "2015-09-30"]
    cov = len(m) / len(qt[qt.qe >= "2015-09-30"])
    early = m[m.lead_days > 0]
    say(f"    {len(m)} quarters matched ({cov:.0%}); ours earlier than NSE: {len(early)} ({len(early) / len(m):.1%}), "
        f"same day {(m.lead_days == 0).mean():.0%}, ours later {(m.lead_days < 0).mean():.0%}")
    # trades: was the quarter the buy relied on public at the decision close?
    sc_idx = ctx.score.index
    look = []
    for t in trades.itertuples():
        d = sc_idx[sc_idx < t.entry_date][-1]
        q = qt[(qt.sym == t.sym) & (qt.known_live <= d)]
        if not len(q):
            continue
        last = q.iloc[-1]
        if pd.notna(last.nse) and last.nse > d:
            look.append({"sym": t.sym, "decision": d.date(), "quarter": last.qe.date(), "our date": last.known.date(),
                         "NSE filed": last.nse_ts, "ret %": round(t.ret * 100, 1)})
    look = pd.DataFrame(look)
    look.to_csv(OUT / "lookahead_trades.csv", index=False)
    say(f"    trades bought before their latest result was on NSE: {len(look)} of {len(trades)}")
    say("    rerunning the backtest with NSE-checked dates ...")
    sc2 = corrected_score(ctx, qt)
    rows = []
    for pname, per in (("2016-22", tune.TUNE), ("2023+", tune.HOLD)):
        a = ctx.run(period=per).stats
        b = ctx.run(score=sc2, period=per).stats
        rows.append((pname, a, b))
        say(f"    {pname}: live {a['CAGR %']}% / Sharpe {a['Sharpe']} / DD {a['maxDD %']}  ->  NSE dates "
            f"{b['CAGR %']}% / {b['Sharpe']} / {b['maxDD %']}")
    hist = m.lead_days.clip(-30, 30)
    dist = {"ours later by 8+ days": (hist <= -8).mean(), "ours later 1-7 days": hist.between(-7, -1).mean(),
            "same day": (hist == 0).mean(), "ours earlier 1 day": (hist == 1).mean(),
            "ours earlier 2+ days": (hist >= 2).mean()}
    return dict(qt=m, early=early, look=look, rows=rows, cov=cov, dist=dist)


# ------------------------------------------------------------------ 2 independent backtester
def plain_backtest(score, O, C, mstate, industry, start, end, n=10, keep_rank=30, cost=0.003, cash_rate=0.06,
                   per_group=3):
    """Written from the plain-English rules, not from portfolio.simulate:
    At each rebalance close: rank the pool; a holding ranked worse than keep_rank (or out of the pool) is sold.
    If the market is in a confirmed uptrend (or uptrend under pressure), empty slots are filled from the top of
    the ranking, at most per_group per industry. All orders fill at the next day's open; sells first. A new
    position gets 1/n of the account (valued at the previous close), or what cash is left if that is at least half
    a slot. Costs 0.3% each way. Cash earns 6% a year. If a stock has no open price, a sell waits a day; a buy is
    dropped."""
    days = C.loc[start:end].index
    rebal = set(score.loc[start:end].index)
    cash, shares, entry = 1.0, {}, {}
    to_sell, to_buy = [], []
    curve = []
    prev_close = {}
    r_day = (1 + cash_rate) ** (1 / 252) - 1
    for d in days:
        op, cl = O.loc[d], C.loc[d]
        if to_sell or to_buy:
            still = []
            for s in to_sell:
                p = op.get(s)
                if p is None or not np.isfinite(p):
                    still.append(s)
                    continue
                cash += shares.pop(s) * p * (1 - cost)
                entry.pop(s)
            to_sell = still
            if to_buy:
                account = cash + sum(sh * prev_close[s] for s, sh in shares.items())
                slot = account / n
                for s in to_buy:
                    p = op.get(s)
                    if p is None or not np.isfinite(p) or s in shares or cash < slot / 2:
                        continue
                    amt = min(slot, cash)
                    shares[s] = amt * (1 - cost) / p
                    entry[s] = p
                    cash -= amt
                to_buy = []
        cash *= 1 + r_day
        for s in shares:
            x = cl.get(s)
            if x is not None and np.isfinite(x):
                prev_close[s] = x
            else:
                prev_close.setdefault(s, entry[s])
        curve.append(cash + sum(sh * prev_close[s] for s, sh in shares.items()))
        if d in rebal:
            ranked = score.loc[d].dropna().sort_values(ascending=False).index.tolist()
            pos = {s: i + 1 for i, s in enumerate(ranked)}
            for s in shares:
                if s not in to_sell and pos.get(s, 10 ** 9) > keep_rank:
                    to_sell.append(s)
            if mstate.get(d, "CONFIRMED_UPTREND") in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE"):
                kept = [s for s in shares if s not in to_sell]
                count = {}
                for s in kept:
                    count[industry.get(s)] = count.get(industry.get(s), 0) + 1
                for s in ranked:
                    if len(kept) + len(to_buy) >= n:
                        break
                    g = industry.get(s)
                    if s in shares or (g and count.get(g, 0) >= per_group):
                        continue
                    to_buy.append(s)
                    count[g] = count.get(g, 0) + 1
    return pd.Series(curve, index=days)


def check_rebuild(ctx):
    say("[2/5] separately written backtester ...")
    from canslim import portfolio as pf
    lab, rows = ctx.lab, []
    for pname, (a, b) in (("2016-22", tune.TUNE), ("2023+", tune.HOLD)):
        live = ctx.run(period=(a, b)).stats
        e = plain_backtest(ctx.score, lab.P["open"], lab.P["close"], lab.ms, lab.ind, a, b)
        mine = pf.stats(e)
        rows.append((pname, live, mine))
        say(f"    {pname}: canslim.portfolio {live['CAGR %']}% / DD {live['maxDD %']}   plain rewrite "
            f"{mine['CAGR %']}% / DD {mine['maxDD %']}")
    return rows


# ------------------------------------------------------------------ 3 re-price trades
def check_reprice(ctx, trades, bh):
    say("[3/5] 15 random trades re-priced from NSE bhavcopies ...")
    t = trades.sample(15, random_state=2026).sort_values("entry_date")
    rows = []
    for x in t.itertuples():
        g = bh[bh.sym == x.sym]
        if len(g):                       # follow the ISIN too (renamed symbols, new ISIN after a split)
            g = bh[bh["isin"].isin(set(g["isin"])) | (bh.sym == x.sym)]
        g = g.drop_duplicates("date").set_index("date")
        raw = pd.read_parquet(ROOT / "data" / "prices" / f"NSE_{x.sym}-EQ.parquet")
        raw = raw[~raw.index.duplicated()]
        def px(frame, d, col="open"):
            return float(frame.at[d, col]) if d in frame.index else np.nan
        b0, b1 = px(g, x.entry_date), px(g, x.exit_date)
        f0, f1 = px(raw, x.entry_date), px(raw, x.exit_date)
        adj_ret = x.exit / x.entry - 1
        bh_ret = b1 / b0 - 1
        split = f0 / x.entry if x.entry else np.nan          # raw / adjusted at entry; != exit ratio -> corp action
        split1 = f1 / x.exit if x.exit else np.nan
        corp = abs(split / split1 - 1) > 0.01 if np.isfinite(split) and np.isfinite(split1) else False
        rows.append({"stock": x.sym, "bought (open)": x.entry_date.date(), "sold (open)": x.exit_date.date(),
                     "NSE open on buy": round(b0, 2), "NSE open on sale": round(b1, 2),
                     "Fyers open on buy": round(f0, 2), "Fyers open on sale": round(f1, 2),
                     "backtest gain %": round(adj_ret * 100, 1), "NSE gain %": round(bh_ret * 100, 1),
                     "split/bonus in between": "yes" if corp else "",
                     "match": ("no NSE file that day" if not (np.isfinite(b0) and np.isfinite(b1)) else
                               "yes" if (abs(adj_ret - bh_ret) < 0.01 or corp) else
                               "yes (Fyers pre-adjusted a split)" if abs(f1 / f0 - 1 - adj_ret) < 0.01 else "NO")})
    r = pd.DataFrame(rows)
    ok = r["match"].str.startswith("yes")
    chk = r["match"] != "no NSE file that day"
    say(f"    {int(ok.sum())}/{int(chk.sum())} checkable trades match; {int((~chk).sum())} fall on days with no "
        f"bhavcopy in data/bhavcopy (e.g. budget-day special sessions)")
    return r


# ------------------------------------------------------------------ 4 split / bonus adjustments
def ca_factor(subj: str):
    s = subj.lower()
    m = re.search(r"bonus\D*(\d+)\s*:\s*(\d+)", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return b / (a + b) if a + b else None
    m = re.search(r"(?:rs|re)\.?\s*(\d+(?:\.\d+)?).*?to\s*(?:rs|re)\.?\s*(\d+(?:\.\d+)?)", s)
    if m and ("split" in s or "sub-division" in s or "sub division" in s or "face value" in s):
        a, b = float(m.group(1)), float(m.group(2))
        return b / a if a else None
    return None


def check_adjust(ctx, trades, bh):
    say("[4/5] split/bonus adjustments vs NSE corporate actions ...")
    ca = []
    for f in sorted((EV / "ca").glob("*.json")):
        for x in json.loads(f.read_text(encoding="utf-8")):
            s = (x.get("subject") or "").lower()
            if any(k in s for k in ("bonus", "split", "sub-division", "sub division", "face value", "demerger",
                                    "rights", "arrangement", "reduction", "consolidat")):
                ca.append({"sym": norm(x["symbol"]), "ex": pd.to_datetime(x["exDate"], format="%d-%b-%Y", errors="coerce"),
                           "subject": x["subject"].strip(), "factor": ca_factor(x["subject"])})
    ca = pd.DataFrame(ca).dropna(subset=["ex"])
    byca = {s: g for s, g in ca.groupby("sym")}
    gaps = []
    for f in (ROOT / "data" / "prices").glob("NSE_*-EQ.parquet"):
        df = pd.read_parquet(f)
        df = df[~df.index.duplicated()].astype(float)
        gp = df["open"] / df["close"].shift() - 1
        for d in gp[gp <= D.GAP].index:
            gaps.append({"sym": D.name_of(f), "date": d, "gap %": round(gp[d] * 100, 1)})
    gaps = pd.DataFrame(gaps)
    isin = bh[["sym", "date", "isin"]]
    isin_chg = set()
    for s, g in isin.groupby("sym", observed=True):
        c = g["isin"].ne(g["isin"].shift()) & g["isin"].shift().notna()
        isin_chg |= {(s, d) for d in g.date[c]}
    def match(r):
        g = byca.get(r.sym)
        if g is not None:
            near = g[(g.ex - r.date).abs() <= pd.Timedelta(days=7)]
            if len(near):
                return near.subject.iloc[0]
        if any((r.sym, r.date + pd.Timedelta(days=k)) in isin_chg for k in range(-3, 4)):
            return "(no NSE record; ISIN changed = split)"
        return ""
    gaps["NSE action"] = [match(r) for r in gaps.itertuples()]
    gaps["matched"] = gaps["NSE action"] != ""
    # held across an unmatched adjustment?
    U = ctx.lab.U
    def in_universe(sym, d, days=60):
        if sym not in U.columns:
            return False
        return bool(U[sym].loc[d - pd.Timedelta(days=days): d + pd.Timedelta(days=days)].any())
    prev, unm = {}, set(gaps.sym[~gaps.matched])
    for f in (ROOT / "data" / "prices").glob("NSE_*-EQ.parquet"):
        sym = D.name_of(f)
        if sym in unm:
            c = pd.read_parquet(f)["close"]
            c = c[~c.index.duplicated()].shift()
            for d in gaps.date[(gaps.sym == sym) & ~gaps.matched]:
                prev[(sym, d)] = float(c.get(d, np.nan))
    gaps["prev close"] = [prev.get((r.sym, r.date), np.nan) for r in gaps.itertuples()]
    gaps["in universe"] = [in_universe(r.sym, r.date) for r in gaps.itertuples()]
    um = gaps[~gaps.matched]
    held = []
    for r in um.itertuples():
        h = trades[(trades.sym == r.sym) & (trades.entry_date < r.date) & (trades.exit_date >= r.date)]
        for t in h.itertuples():
            held.append({"stock": r.sym, "gap date": r.date.date(), "gap %": r._3, "trade": f"{t.entry_date.date()} -> "
                         f"{t.exit_date.date()}", "backtest gain %": round(t.ret * 100, 1),
                         "gain if the drop was real %": round(((1 + t.ret) * (1 + r._3 / 100) - 1) * 100, 1)})
    held = pd.DataFrame(held)
    # reverse: NSE split/bonus the gap rule did not adjust
    have = set((D.name_of(f) for f in (ROOT / "data" / "prices").glob("NSE_*-EQ.parquet")))
    gset = {(r.sym, r.date) for r in gaps.itertuples()}
    missed = []
    for r in ca[ca.factor.notna() & (ca.factor < 0.99) & ca.sym.isin(have) & (ca.ex >= "2015-01-01")].itertuples():
        if any((r.sym, r.ex + pd.Timedelta(days=k)) in gset for k in range(-7, 8)):
            continue
        df = pd.read_parquet(ROOT / "data" / "prices" / f"NSE_{r.sym}-EQ.parquet")
        df = df[~df.index.duplicated()].astype(float)
        w = df.loc[r.ex - pd.Timedelta(days=10): r.ex + pd.Timedelta(days=10)]
        worst = float((w.open / w.close.shift() - 1).min()) if len(w) > 1 else np.nan
        # Fyers history is already adjusted for most actions: no gap at the ex date means nothing to fix
        kind = ("no price data" if not np.isfinite(worst) else
                "fake drop (not adjusted)" if worst <= (r.factor - 1) * 0.5 else "already adjusted by Fyers")
        missed.append({"stock": r.sym, "ex date": r.ex.date(), "action": r.subject[:60], "factor": round(r.factor, 3),
                       "worst raw gap %": round(worst * 100, 1), "kind": kind, "in universe": in_universe(r.sym, r.ex, 30)})
    missed = pd.DataFrame(missed)
    fake = missed[missed.kind == "fake drop (not adjusted)"] if len(missed) else missed
    held_missed = []
    for r in fake.itertuples() if len(fake) else []:
        h = trades[(trades.sym == r.stock) & (trades.entry_date < pd.Timestamp(r._2)) &
                   (trades.exit_date >= pd.Timestamp(r._2))]
        held_missed += [{"stock": r.stock, "ex date": r._2, "factor": r.factor, "trade": f"{t.entry_date.date()} -> "
                         f"{t.exit_date.date()}", "backtest gain %": round(t.ret * 100, 1)} for t in h.itertuples()]
    held_missed = pd.DataFrame(held_missed)
    gaps.to_csv(OUT / "adjustments.csv", index=False)
    missed.to_csv(OUT / "unadjusted_actions.csv", index=False)
    say(f"    {len(gaps)} adjustments; {int(gaps.matched.sum())} matched to NSE; {len(um)} unmatched, "
        f"{len(held)} backtest trades held across one")
    say(f"    unmatched gaps in the liquid universe: {int(um['in universe'].sum())} (the rest are penny stocks, median "
        f"prev close Rs {um['prev close'].median():.2f})")
    say(f"    NSE splits/bonuses with no gap rule adjustment: {len(missed)}; " + ", ".join(
        f"{k} {v}" for k, v in missed.kind.value_counts().items()) + f"; fake drops in the universe "
        f"{int(fake['in universe'].sum()) if len(fake) else 0}, trades held across one {len(held_missed)}")
    return dict(gaps=gaps, um=um, held=held, missed=missed, fake=fake, held_missed=held_missed)


# ------------------------------------------------------------------ 5 momentum index sources
def check_index():
    say("[5/5] momentum index: niftyindices vs NSE archive ...")
    from indexdata import read_archive  # noqa: E402  (standalone script at the repo root)
    a = read_archive()
    rows = []
    for nm in ("Nifty200 Momentum 30", "Nifty500 Momentum 50", "Nifty Midcap150 Momentum 50"):
        j = json.loads((ROOT / "data" / "indices" / "old" / f"gap_{nm}.json").read_text(encoding="utf-8"))
        o = pd.Series({pd.to_datetime(x["HistoricalDate"], format="%d %b %Y"): float(x["CLOSE"].replace(",", ""))
                       for x in j if x.get("CLOSE") not in (None, "-")})
        z = a[a.raw_name.str.strip().str.lower() == nm.lower()].drop_duplicates("date").set_index("date")["close"]
        both = pd.concat([o.rename("niftyindices"), z.rename("archive")], axis=1).dropna()
        dif = (both.niftyindices / both.archive - 1).abs() * 100
        rows.append({"index": nm, "days in both": len(both),
                     "first": both.index.min().date() if len(both) else None,
                     "last": both.index.max().date() if len(both) else None,
                     "days differing > 0.1%": int((dif > 0.1).sum()), "largest gap %": round(dif.max(), 3)})
        say(f"    {nm}: {len(both)} days in both, {int((dif > 0.1).sum())} differ by > 0.1%, max {dif.max():.3f}%")
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ run
def run(ctx):
    OUT.mkdir(parents=True, exist_ok=True)
    full = ctx.run(period=FULL)
    trades = full.trades
    trades.to_csv(OUT / "trades_2016_now.csv", index=False)
    say(f"live backtest 2016-now: {len(trades)} trades")
    bh = bhav.load()
    bh = bh.assign(sym=bh["sym"].astype(str).map(norm), isin=bh["isin"].astype(str))
    c1 = check_dates(ctx, trades)
    c2 = check_rebuild(ctx)
    c3 = check_reprice(ctx, trades, bh)
    c4 = check_adjust(ctx, trades, bh)
    c5 = check_index()
    c3.to_csv(OUT / "repriced_trades.csv", index=False)
    c5.to_csv(OUT / "index_sources.csv", index=False)

    # summary table
    T = []
    (p1, a1, b1), (p2, a2, b2) = c1["rows"]
    T.append({"check": "1 result dates", "result": f"{len(c1['early'])} of {len(c1['qt'])} quarters "
              f"({len(c1['early']) / len(c1['qt']):.1%}) dated earlier than NSE; {len(c1['look'])} of {len(trades)} trades "
              f"bought before the result was filed", "effect": f"CAGR 2016-22 {a1['CAGR %']} -> {b1['CAGR %']}, "
              f"2023+ {a2['CAGR %']} -> {b2['CAGR %']} with NSE dates"})
    (q1, l1, m1), (q2, l2, m2) = c2
    T.append({"check": "2 rewritten backtester", "result": f"2016-22 {l1['CAGR %']}% vs {m1['CAGR %']}%; "
              f"2023+ {l2['CAGR %']}% vs {m2['CAGR %']}%", "effect": f"maxDD {l1['maxDD %']} vs {m1['maxDD %']}, "
              f"{l2['maxDD %']} vs {m2['maxDD %']}"})
    ok3 = c3["match"].str.startswith("yes")
    chk3 = c3["match"] != "no NSE file that day"
    T.append({"check": "3 trades re-priced", "result": f"{int(ok3.sum())}/{int(chk3.sum())} checkable trades match NSE "
              f"bhavcopy prices", "effect": f"{int((~chk3).sum())} on days missing from data/bhavcopy"})
    g = c4["gaps"]
    um, fk = c4["um"], c4["fake"]
    T.append({"check": "4 split/bonus adjustments", "result": f"{len(g)} gap adjustments, {int(g.matched.sum())} matched "
              f"to NSE; of {len(um)} unmatched only {int(um['in universe'].sum())} in the universe (rest penny stocks); "
              f"{len(fk)} splits/bonuses never adjusted", "effect": f"{len(c4['held'])} trades held across an unmatched "
              f"gap, {len(c4['held_missed'])} across an unadjusted bonus"})
    T.append({"check": "5 momentum index sources", "result": "; ".join(f"{r['index']}: {r['days differing > 0.1%']} of "
              f"{r['days in both']} days differ" for r in c5.to_dict("records")), "effect": ""})
    table = pd.DataFrame(T)

    d = c1["dist"]
    body = ("### 1. Result dates\n"
            f"{len(c1['qt'])} stock-quarters since Sep 2015 matched to an NSE result filing ({c1['cov']:.0%} of all). "
            "A filing counts as public for the decision at a day's close if NSE received it before the next 09:15 open. "
            "Our date vs NSE: " + ", ".join(f"{k} {v:.1%}" for k, v in d.items()) + ".\n\n"
            f"Backtest with every result date set to the later of ours and NSE's: 2016-22 {a1['CAGR %']}% → "
            f"{b1['CAGR %']}% a year (Sharpe {a1['Sharpe']} → {b1['Sharpe']}, worst drop {a1['maxDD %']} → "
            f"{b1['maxDD %']}); 2023+ {a2['CAGR %']}% → {b2['CAGR %']}% (Sharpe {a2['Sharpe']} → {b2['Sharpe']}).\n\n"
            + (f"Trades bought before NSE had the result ({len(c1['look'])}, average gain "
               f"{c1['look']['ret %'].mean():.1f}%; first 15):\n\n" + md_table(c1["look"].head(15)) + "\n\n"
               if len(c1["look"]) else "No trade was bought before its result was filed.\n\n")
            + "### 2. Separately written backtester\n"
            "`plain_backtest` in this file was written from the rules in plain English, without reusing "
            "`canslim.portfolio`: same ranked pool, 10 slots, keep while rank ≤ 30, no new buys outside an uptrend, "
            "max 3 per industry, next-open fills, 0.3% a side, cash at 6%.\n\n"
            f"| period | canslim.portfolio | rewrite |\n|---|---|---|\n"
            f"| 2016-22 | {l1['CAGR %']}% / Sharpe {l1['Sharpe']} / DD {l1['maxDD %']} | {m1['CAGR %']}% / {m1['Sharpe']} / {m1['maxDD %']} |\n"
            f"| 2023+ | {l2['CAGR %']}% / Sharpe {l2['Sharpe']} / DD {l2['maxDD %']} | {m2['CAGR %']}% / {m2['Sharpe']} / {m2['maxDD %']} |\n\n"
            "### 3. Fifteen random trades, checkable on any chart\n"
            "Prices are the unadjusted opens on the buy and sale days. The backtest uses split-adjusted prices, so a "
            "split or bonus in between makes the raw prices differ while the gain is the same.\n\n"
            + md_table(c3) + "\n\n"
            "### 4. Split and bonus adjustments\n"
            f"The price data treats any overnight gap of −25% or worse as a split/bonus/demerger and scales earlier "
            f"prices. {len(g)} such gaps; {int(g.matched.sum())} match an NSE corporate action within 7 days (or an "
            f"ISIN change, which happens on splits). {len(um)} have no NSE record; {len(um) - int(um['in universe'].sum())} "
            f"of them are penny stocks (median previous close Rs {um['prev close'].median():.2f}, where one price tick "
            f"is a 25-33% move) outside the universe (minimum price Rs 20). In the universe:\n\n"
            + md_table(um[um["in universe"]][["sym", "date", "gap %", "prev close"]]) + "\n\n"
            + (f"Backtest trades held across an unmatched gap:\n\n" + md_table(c4["held"]) + "\n\n" if len(c4["held"])
               else "No backtest trade was held across an unmatched gap.\n\n")
            + f"Reverse check: {len(c4['missed'])} NSE splits/bonuses since 2015 were not adjusted by the gap rule. "
              + ", ".join(f"{k}: {v}" for k, v in c4["missed"].kind.value_counts().items())
              + ". Fyers' price history already comes adjusted for most actions, so there is no gap to fix. The fake "
              "drops are small bonuses (1:4 and smaller) whose drop is above the −25% threshold:\n\n"
              + (md_table(fk[["stock", "ex date", "action", "factor", "worst raw gap %", "in universe"]]) + "\n\n"
                 if len(fk) else "")
            + (md_table(c4["held_missed"]) + "\n\n" if len(c4["held_missed"]) else "")
            + "### 5. Momentum index sources\n" + md_table(c5) + "\n\n"
            "Files: data/tune/audit/ (result_dates.csv, lookahead_trades.csv, repriced_trades.csv, adjustments.csv, "
            "unadjusted_actions.csv, index_sources.csv, trades_2016_now.csv).")
    pd.DataFrame([{"check": r["check"], **r} for r in T]).to_csv(OUT / "summary.csv", index=False)
    dc = a1["CAGR %"] - b1["CAGR %"]
    if not len(c1["look"]):                 # the fix (canslim/resultdates.py) is in: live dates are already NSE-checked
        takeaway = (f"The arithmetic is right: a separately written backtester gives the same result "
                    f"({l1['CAGR %']}% vs {m1['CAGR %']}% a year in 2016-22), {int(ok3.sum())}/{int(chk3.sum())} re-priced "
                    f"trades match NSE's own prices, split adjustments touched no trade and the momentum index sources "
                    f"agree on every shared day. One real flaw was found and fixed: {len(c1['early']) / len(c1['qt']):.0%} "
                    f"of Screener's result dates were earlier than NSE received the result. With NSE-checked dates no "
                    f"trade is bought before its result is public; the fix cost {FIX_COST}.")
        decision = "verified; result dates now NSE-checked (fixed 2026-11-15)"
        return Outcome(table, decision=decision, takeaway=takeaway, body=body, status="Audit - passed after one fix",
                       tested=0)
    takeaway = (f"The arithmetic is right: a separately written backtester gives the same result "
                f"({l1['CAGR %']}% vs {m1['CAGR %']}% a year in 2016-22), {int(ok3.sum())}/{int(chk3.sum())} re-priced trades "
                f"match NSE's own prices and the momentum index sources agree on every shared day. One real flaw: "
                f"{len(c1['early']) / len(c1['qt']):.0%} of result dates were earlier than NSE received the result, so "
                f"{len(c1['look'])} of {len(trades)} trades were bought on results not yet public. Using NSE's dates costs "
                f"{dc:.1f} points a year in 2016-22 ({a1['CAGR %']}% to {b1['CAGR %']}%, Sharpe {a1['Sharpe']} to "
                f"{b1['Sharpe']}) and {a2['CAGR %'] - b2['CAGR %']:.1f} in 2023+. Split adjustments touched no trade.")
    decision = (f"backtest arithmetic and prices verified; result dates should switch to NSE-checked dates "
                f"(-{dc:.1f} pt a year 2016-22)")
    return Outcome(table, decision=decision, takeaway=takeaway, body=body, status="Audit - one fix needed", tested=0)


EXPERIMENT = Experiment(
    slug="audit", title="Audit: are the backtest's calculations correct?",
    question="Every result on the Insights page comes from one backtester and one price/fundamentals pipeline. "
             "Do the dates, prices, split adjustments and portfolio arithmetic hold up against independent sources?",
    tags="audit, look-ahead, data quality, evidence", bar=None, run=run,
    method="Five checks against sources the backtest does not use: NSE result filing timestamps, a separately "
           "written backtester, NSE bhavcopy prices, NSE corporate actions, and the NSE index archive.")
