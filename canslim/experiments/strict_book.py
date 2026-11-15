"""Strict book version of CAN SLIM vs the live system: what does each departure from O'Neil cost or gain?

The live system (data/tune/final.json) is NOT changed. Every variant below is built here from the same cached
data. The first rows change ONE thing from the live system; the last rows are the strict book version.

Book rules used (How to Make Money in Stocks; checklist pp. 424-426), fixed before running:
  C  latest quarterly EPS up >= 25% vs a year ago; sales up >= 25%, or sales growth rising 3 quarters in a row
  A  annual EPS up >= 25% in EACH of the last 3 fiscal years; ROE >= 17%
  N  buy only on a breakout above the pivot of a sound base (no faulty-pattern flags), and not more than 5%
     above the pivot when bought
  S  breakout day volume >= 40% above its 50-day average
  L  RS rating >= 80 (unchanged)
  M  no new buys unless the market is in an uptrend (unchanged)
  Sell  8% stop-loss from the buy price; take profits at +20%, except a stock up 20% within 3 weeks of the buy
        is held at least 8 weeks; no selling just because the stock fell down the ranking
Lenient reading of N (a second, equally defensible reading, decided after seeing the strict one buy ~1 stock a
year): faulty-pattern flags are warnings except "too deep" and "V-shaped"; the breakout may be up to 20 trading
days old as long as the price is still within 5% of the pivot (the book's buy zone).
Not in the book, so dropped in the strict version: the 50/150/200-day trend template.
Kept in both (data not yet available for a strict version): institutional sponsorship (I), new products /
management (N catalyst), analyst estimates.

EPS: Screener's quarterly table has profit, not EPS, before the last 13 quarters. Its EPS history (12-month EPS,
split-adjusted) gives the profit-per-share ratio at each result: shares = 12-month profit / 12-month EPS. Quarterly
EPS = quarterly profit / that ratio, which captures new share issues and minority interests. Before a company's
first EPS stamp, constant shares are assumed (= profit growth).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import data as D
from canslim import patterns
from canslim.exp import Experiment, Variant

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "tune" / "strict-book"
_C = {}


def say(*a):
    print(" ", *a, flush=True)


# ---------------------------------------------------------------- fundamentals on EPS
def eps_events(fund: dict) -> dict:
    """Per stock, indexed by the date each quarter became known: eps_yoy, eps_cagr3, sales25_or_accel, fy3_25."""
    ev = {}
    for sym, f in fund.items():
        q = f["q"].copy()
        if len(q) < 8:
            continue
        p = ROOT / "data" / "fundamentals" / f"{sym}.json"
        eps = D._dated((json.loads(p.read_text()).get("history") or {}).get("EPS")) if p.exists() else pd.Series(dtype=float)
        ttm_np = q.np.rolling(4).sum()
        stamp = []
        for qe in q.index:                            # the 12-month EPS printed with this quarter's result
            later = eps.index[(eps.index > qe) & (eps.index <= qe + pd.Timedelta(days=120))]
            stamp.append(eps[later[0]] if len(later) else np.nan)
        ratio = (ttm_np / pd.Series(stamp, index=q.index)).where((ttm_np > 0) & (pd.Series(stamp, index=q.index) > 0))
        ratio = ratio.ffill()                        # only the past: no future share counts
        first = ratio.first_valid_index()
        if first is not None:                        # before the first stamp: constant shares (= profit growth)
            ratio = ratio.fillna(ratio[first])
        else:
            ratio = pd.Series(1.0, index=q.index)
        e = q.np / ratio
        e4 = e.shift(4)
        q["eps_yoy"] = np.where(e4 > 0, (e / e4 - 1) * 100, np.where(e > 0, 100.0, np.nan)).clip(-100, 300)
        ttm = e.rolling(4).sum()
        t12 = ttm.shift(12)
        q["eps_cagr3"] = (((ttm / t12) ** (1 / 3) - 1) * 100).where((t12 > 0) & (ttm > 0))
        s4 = q.sales.shift(4)
        sy = ((q.sales / s4 - 1) * 100).where(s4 > 0)
        q["sales25_or_accel"] = ((sy >= 25) | ((sy > sy.shift(1)) & (sy.shift(1) > sy.shift(2)) & (sy.shift(2) > sy.shift(3)))).astype(float)
        # fiscal years (Apr-Mar): EPS summed over the 4 quarters, known when the March quarter is known
        fy = pd.Series([d.year + (d.month > 3) for d in q.index], index=q.index)
        g = pd.DataFrame({"e": e, "fy": fy, "known": q.known}).groupby("fy")
        y = pd.DataFrame({"e": g.e.sum(), "n": g.e.count(), "known": g.known.max()})
        y = y[y.n == 4]
        gr = y.e / y.e.shift(1) - 1
        ok = (y.e.shift(1) > 0) & (gr >= 0.25)
        y["fy3_25"] = (ok & ok.shift(1, fill_value=False) & ok.shift(2, fill_value=False)
                       & (y.index.to_series().diff() == 1) & (y.index.to_series().diff().shift(1) == 1)
                       & (y.index.to_series().diff().shift(2) == 1)).astype(float)
        x = q.set_index("known")[["eps_yoy", "eps_cagr3", "sales25_or_accel"]]
        x = x[~x.index.duplicated(keep="last")]
        fyx = y.set_index("known")["fy3_25"]
        fyx = fyx[~fyx.index.duplicated(keep="last")]
        x = x.join(fyx, how="outer").sort_index().ffill()
        ev[sym] = x
    return ev


def panels(ctx) -> dict:
    if "P" in _C:
        return _C["P"]
    f = OUT / "eps_panels.pkl"
    if f.exists() and f.stat().st_mtime > (ROOT / "data" / "cache" / "build.pkl").stat().st_mtime:
        _C["P"] = pd.read_pickle(f)
        return _C["P"]
    say("building EPS panels ...")
    ev = eps_events(ctx.lab.fund)
    dates = ctx.lab.S["np_yoy"].index
    cols = ctx.lab.S["np_yoy"].columns
    out = {k: {} for k in ("eps_yoy", "eps_cagr3", "sales25_or_accel", "fy3_25")}
    for sym, e in ev.items():
        x = e.reindex(e.index.union(dates)).ffill().reindex(dates)
        for k in out:
            out[k][sym] = x[k]
    P = {k: pd.DataFrame(v, index=dates).reindex(columns=cols) for k, v in out.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(P, f)
    _C["P"] = P
    return P


# ---------------------------------------------------------------- pool
def pool(ctx, eps=False, book_a=False, book_sales=False, trend=True) -> pd.DataFrame:
    """The live rules (final.json) with the chosen book substitutions. Returns RS rank where the stock passes."""
    S, U, has_f, r = ctx.lab.S, ctx.lab.U, ctx.lab.has_f, ctx.rules
    E = panels(ctx)
    base = U & has_f
    rs = S["rs_ibd"].where(base).rank(axis=1, pct=True)
    ok = base.copy()
    if trend and r.get("trend"):
        ok &= S["trend"] == 1
    ok &= S["prox_high"] >= r["prox"]
    ok &= (E["eps_yoy"] if eps else S["np_yoy"]) >= r["np_yoy"]
    if book_sales:
        ok &= E["sales25_or_accel"] == 1
    else:
        ok &= (S["sales_yoy"] >= r["sales"]) | (S["streak"] >= 2)
    if book_a:
        ok &= (E["fy3_25"] == 1) & (S["roe"] >= 17)
    else:
        ok &= ((E["eps_cagr3"] if eps else S["ttm_cagr3"]) >= r["cagr3"]) & (S["roe"] >= r["roe"])
    ok &= rs >= r["rs"] / 100
    if r.get("npm_up"):
        ok &= S["npm_chg"] > 0
    return rs.where(ok)


def strict_pool(ctx):
    return pool(ctx, eps=True, book_a=True, book_sales=True, trend=False)


# ---------------------------------------------------------------- base breakout on volume
FAULTS_OK = ()        # strict: any faulty-pattern flag disqualifies the base


def breakout_mask(ctx, lenient=False) -> pd.DataFrame:
    """True at a rebalance date when, since the previous rebalance, the stock closed above the pivot of a sound
    base (detected on data up to the day before) on volume >= 1.4x its 50-day average, and the decision close
    is still within 5% of that pivot. Computed for every stock in any pool used here."""
    key = "ML" if lenient else "M"
    if key in _C:
        return _C[key]
    f = OUT / ("breakout_mask_lenient.parquet" if lenient else "breakout_mask.parquet")
    if f.exists() and f.stat().st_mtime > (ROOT / "data" / "cache" / "build.pkl").stat().st_mtime:
        _C[key] = pd.read_parquet(f)
        return _C[key]
    cand = ctx.score.notna() | strict_pool(ctx).notna() | pool(ctx, eps=True).notna() \
        | pool(ctx, book_a=True).notna() | pool(ctx, book_sales=True).notna() | pool(ctx, trend=False).notna()
    cand = cand.loc["2016-01-01":]
    P = ctx.lab.P
    days = P["close"].index
    pos = {d: i for i, d in enumerate(days)}
    reb = list(cand.index)
    mask = pd.DataFrame(False, index=cand.index, columns=cand.columns)
    frames, n, hits = {}, 0, 0
    for j, d in enumerate(reb):
        syms = cand.columns[cand.loc[d].values]
        if not len(syms):
            continue
        i1 = pos[d]
        i0 = (i1 - 19) if lenient else (pos[reb[j - 1]] + 1 if j else i1 - 4)
        for s in syms:
            if s not in frames:
                frames[s] = pd.DataFrame({k: P[k][s] for k in ("open", "high", "low", "close", "volume")})
            df = frames[s]
            c, v = df["close"].values, df["volume"].values
            avg = pd.Series(v[max(0, i0 - 60):i1 + 1]).rolling(50, min_periods=30).mean().values
            for t in range(i0, i1 + 1):
                k = t - max(0, i0 - 60)
                a = avg[k - 1] if k >= 1 else np.nan
                if not (np.isfinite(c[t]) and np.isfinite(a) and v[t] >= 1.4 * a):
                    continue                          # the cheap volume test first
                n += 1
                b = patterns.detect(df.iloc[max(0, t - 400):t])
                bad = [x for x in b.faults if x.startswith(("too deep", "V-shaped"))] if lenient else b.faults
                if b.kind == "none" or bad or not np.isfinite(b.pivot):
                    continue
                if c[t] > b.pivot and c[i1] <= b.pivot * 1.05:
                    mask.at[d, s] = True
                    hits += 1
                    break
        if d.month == 1 and d.day <= 7:
            say(f"breakout scan {d.date()}: {n} volume days checked, {hits} breakouts")
    OUT.mkdir(parents=True, exist_ok=True)
    mask.to_parquet(f)
    _C[key] = mask
    return mask


# ---------------------------------------------------------------- variants
BOOK_SELL = {"stop": 0.08, "profit_take": 0.20, "hold8": True, "keep_rank": 10 ** 10}
brk = lambda ctx: {"entry_ok": breakout_mask(ctx)}
brk_len = lambda ctx: {"entry_ok": breakout_mask(ctx, lenient=True)}


def explain(t, passed):
    T = t[t.period == "2016-22"].set_index("variant")
    H = t[t.period == "2023+"].set_index("variant")
    b = T.iloc[0]
    lines = []
    for n in T.index[1:]:
        r = T.loc[n]
        lines.append(f"{n}: {r['CAGR %']}% / Sharpe {r['Sharpe']} / DD {r['maxDD %']} "
                     f"(2023+ {H.loc[n, 'CAGR %']}%)")
    s = T.loc["STRICT BOOK (all of the above)"]
    take = (f"Live system 2016-22: {b['CAGR %']}% a year, Sharpe {b['Sharpe']}, worst drop {b['maxDD %']}%. "
            f"Strict book version: {s['CAGR %']}%, Sharpe {s['Sharpe']}, worst drop {s['maxDD %']}% "
            f"(2023+: {H.iloc[0]['CAGR %']}% vs {H.loc['STRICT BOOK (all of the above)', 'CAGR %']}%). "
            + ("Departures that pass the bar when reversed: " + ", ".join(passed) + "."
               if passed else "No single return to the book passes the bar."))
    return take, "**Each change on its own, 2016-22** (vs live):\n\n- " + "\n- ".join(lines)


EXPERIMENT = Experiment(
    slug="strict-book", title="Strict O'Neil vs the live system: what each departure costs",
    question="The live system departs from the book in several places (profit instead of EPS, softer A and sales "
             "rules, a trend template, no base breakouts, no stop-loss, no profit-taking). What does each departure "
             "cost or gain, and how does a strict book version do?",
    tags="CAN SLIM, book, EPS, bases, breakouts, stop-loss, profit-taking", explain=explain,
    method="Same data, dates and costs as every test. One variant per departure, each changed alone from the live "
           "system, then the strict book version with all of them, and the strict entry with the live exit. Book "
           "thresholds fixed before running (see canslim/experiments/strict_book.py).",
    variants=[
        Variant("live system"),
        Variant("1 EPS instead of profit (C and A)", score=lambda ctx: pool(ctx, eps=True)),
        Variant("2 book A: EPS +25% each of 3 yrs, ROE 17", score=lambda ctx: pool(ctx, book_a=True)),
        Variant("3 book sales: +25% or 3-qtr acceleration", score=lambda ctx: pool(ctx, book_sales=True)),
        Variant("4 drop the trend template", score=lambda ctx: pool(ctx, trend=False)),
        Variant("5 buy only on base breakouts on volume", sim=brk),
        Variant("6 8% stop-loss", cfg={"stop": 0.08}),
        Variant("7 book sells: +20% profit, 8-week rule, no rank exit",
                cfg={"profit_take": 0.20, "hold8": True, "keep_rank": 10 ** 10}),
        Variant("6+7 book sells together (stop + profit rule), live entry", cfg=BOOK_SELL),
        Variant("5b base breakouts, lenient reading", sim=brk_len),
        Variant("STRICT BOOK (all of the above)", score=strict_pool, sim=brk, cfg=BOOK_SELL),
        Variant("strict book entry, live exit", score=strict_pool, sim=brk),
        Variant("BOOK, lenient breakouts", score=strict_pool, sim=brk_len, cfg=BOOK_SELL),
    ])
