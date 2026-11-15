"""How much do the backtests gain from only containing stocks that are still listed today?

The Fyers price files hold only today's listed stocks (and not all of them). The NSE bhavcopies hold every stock
that traded. Stocks missing from the price files are rebuilt from the bhavcopies (same split/bonus adjustment) and
put back. Renamed stocks (same ISIN, new symbol) are not counted as missing.

Screener has no fundamentals for most of them, so the test is a WORST CASE for the system: a missing stock is
assumed to pass the fundamental rules whenever it passes the price rules (trend, near high, RS). The real
system would have rejected many of them (falling profits fail the growth and ROE rules).

When a stock stops trading the holding is sold at the next rebalance:
  exit at last price        what a merger, buyback or delisting offer roughly pays
  failures go to zero       stocks that ended in trade-to-trade (BE/BZ) or 70%+ below their 1-year high are
                            written down to nothing (most pessimistic)
Also shown: the same three runs for the price rules alone (no fundamentals at all), the upper bound of the bias.
"""
import numpy as np
import pandas as pd

from canslim import bhav, factors, tune
from canslim import data as D
from canslim import portfolio as pf
from canslim.exp import PERIODS, Experiment, Outcome, md_table

KEYS = ("open", "high", "low", "close", "volume")
N_DRAW = 20


def missing_stocks(P_cols):
    d = bhav.load()
    L = d.date.max()
    d = d.assign(sym=d["sym"].astype(str), isin=d["isin"].astype(str), series=d["series"].astype(str))
    last = d.groupby("sym").agg(last=("date", "max"), n=("date", "size"), isn=("isin", "last"), ser=("series", "last"))
    last["norm"] = last.index.str.replace("&", "and")
    recent = d[d.date > L - pd.Timedelta(days=30)]
    live_isin = recent.groupby("isin").sym.agg(set).to_dict()
    renamed = [s for s, r in last.iterrows() if r.isn in live_isin and s not in live_isin[r.isn]]
    equity = last.isn.str.startswith("INE")                       # INF... = ETFs / fund units
    m = last[~last.norm.isin(set(P_cols)) & ~last.index.isin(renamed) & (last.n >= 60) & equity]
    m = m.assign(gone=m["last"] < L - pd.Timedelta(days=30))
    return d[d.sym.isin(m.index)], m, L


def rebuilt_panel(rows: pd.DataFrame, info: pd.DataFrame, idx: pd.DatetimeIndex, L):
    """Wide adjusted panels for the missing stocks, extended after their last trade with an exit price."""
    rows = rows.assign(pri=rows.series.map({"EQ": 0, "BE": 1, "BZ": 2}))
    rows = rows.sort_values(["sym", "date", "pri"]).drop_duplicates(["sym", "date"])
    out = {k: {} for k in KEYS}
    fail, last_day = {}, {}
    for s, g in rows.groupby("sym"):
        df = D.adjust(g.set_index("date")[list(KEYS)].astype(float))
        df = df.reindex(idx[(idx >= df.index[0]) & (idx <= df.index[-1])]).dropna(how="all")
        if len(df) < 60:
            continue
        k = df.index[-1]
        hi = df.close.iloc[-252:].max()
        gone = info.at[s, "last"] < L - pd.Timedelta(days=30)
        fail[s] = bool(gone and (info.at[s, "ser"] in ("BE", "BZ") or df.close.iloc[-1] < 0.3 * hi))
        last_day[s] = k
        for c in KEYS:
            out[c][s.replace("&", "and")] = df[c]
    out = {c: pd.DataFrame(v).reindex(idx) for c, v in out.items()}
    names = {s: s.replace("&", "and") for s in last_day}
    return out, {names[s]: v for s, v in last_day.items()}, {names[s]: v for s, v in fail.items()}


def with_exit(Pm, last_day, fail, zero):
    """After a stock's last trade, every price = its exit price, volume 0 (so it can be sold, never bought)."""
    Q = {k: v.copy() for k, v in Pm.items()}
    for s, k in last_day.items():
        after = Q["close"].index > k
        px = 0.0 if (zero and fail.get(s)) else Q["close"].at[k, s]
        for c in ("open", "high", "low", "close"):
            Q[c].loc[after, s] = px
        Q["volume"].loc[after, s] = 0.0
    return Q


def price_parts(P, dates):
    """The live system's price inputs (same formulas as factors.price_factors), sampled on rebalance dates."""
    c, h, v = P["close"], P["high"], P["volume"]
    ret = lambda a, b: c.shift(a) / c.shift(b) - 1
    rs = 0.4 * ret(0, 63) + 0.2 * ret(63, 126) + 0.2 * ret(126, 189) + 0.2 * ret(189, 252)
    prox = c / h.rolling(252, min_periods=200).max()
    ma50, ma150, ma200 = (c.rolling(n, min_periods=int(n * .9)).mean() for n in (50, 150, 200))
    trend = ((c > ma50) & (ma50 > ma150) & (ma150 > ma200) & (ma200 > ma200.shift(21))).astype(float).where(ma200.notna())
    F = {"turnover": (c * v).rolling(50, min_periods=40).median()}
    U = factors.universe_mask(P, F)
    return {k: x.reindex(dates) for k, x in (("rs", rs), ("prox", prox), ("trend", trend), ("U", U))}


def score(X, M, rules, use_fund=True):
    """M: rank_ok (has fundamentals data - RS is ranked among these, as in tune.book_score), fund_pass, alive."""
    base = X["U"].fillna(False).astype(bool) & M["alive"]
    if use_fund:
        base &= M["rank_ok"]
    rs = X["rs"].where(base).rank(axis=1, pct=True)
    ok = base & (X["trend"] == 1) & (X["prox"] >= rules["prox"]) & (rs >= rules["rs"] / 100)
    if use_fund:
        ok &= M["fund_pass"]
    return rs.where(ok)


def run(ctx) -> Outcome:
    lab, rules = ctx.lab, ctx.rules
    idx, dates = lab.P["close"].index, lab.S["rs_ibd"].index
    rows, info, L = missing_stocks(lab.P["close"].columns)
    Pm, last_day, fail = rebuilt_panel(rows, info, idx, L)
    miss = list(Pm["close"].columns)
    gone_flag = {s.replace("&", "and"): g for s, g in info["gone"].items()}
    gone = [s for s in miss if gone_flag.get(s)]
    gap_ = [s for s in miss if not gone_flag.get(s)]
    print(f"  missing equity stocks rebuilt: {len(miss)} = {len(gone)} delisted/merged "
          f"({sum(fail.values())} ended badly) + {len(gap_)} still trading but without a price file", flush=True)
    surv = list(lab.P["close"].columns)
    allcols = surv + miss
    # fundamentals pass mask: the live rules without the price parts; missing stocks are assumed to pass (worst case)
    fr = {k: v for k, v in rules.items() if k not in ("trend", "prox", "rs")}
    surv_f = tune.book_score(lab.S, lab.U, lab.has_f, {**fr, "trend": False, "prox": None, "rs": None})
    full = lambda m: m.reindex(columns=allcols).fillna(False).astype(bool).assign(**{s: True for s in miss})
    alive = pd.DataFrame(True, index=dates, columns=allcols)
    for s, k in last_day.items():
        alive.loc[alive.index > k, s] = False
    Pq = {z: {k: pd.concat([lab.P[k], v], axis=1) for k, v in with_exit(Pm, last_day, fail, z).items()}
          for z in (False, True)}
    X = price_parts(Pq[False], dates)           # per-stock factors; the exit-price tail is masked by `alive`
    # sanity: the listed-only pool rebuilt here must match the live pool
    M = lambda cols: {"alive": alive & pd.Series({c: c in cols for c in allcols}),
                      "rank_ok": full(lab.has_f.reindex(dates)), "fund_pass": full(surv_f.notna())}
    check = score(X, M(set(surv)), rules)[surv]
    live = ctx.score.reindex_like(check)
    diff = int((check.notna() != live.notna()).values.sum())
    print(f"  sanity: rebuilt pool differs from the backtest pool in {diff} of {int(live.notna().values.sum())} "
          f"stock-days", flush=True)
    U = X["U"].fillna(False).astype(bool) & alive
    last_scan = U.index[U.index <= L][-1]
    now_liquid = [s for s in gap_ if U.at[last_scan, s]]
    # fair estimate: an added stock passes the fundamental rules at the same rate as listed stocks that pass the
    # price rules (one random draw per stock per quarter, as results arrive quarterly); median of N_DRAW draws
    lst = score(X, M(set(surv)), {**rules}, use_fund=False)[surv]            # listed, price rules passed
    hasf = lab.has_f.reindex(dates)[surv].fillna(False).astype(bool)
    pp = lst.notna() & hasf
    rate = float((pp & surv_f.notna()).values.sum() / max(pp.values.sum(), 1))
    print(f"  listed stocks passing the price rules also pass the fundamental rules {rate:.0%} of the time", flush=True)
    qkey = pd.PeriodIndex(dates, freq="Q")
    rng = np.random.default_rng(3)

    def draw():
        u = pd.DataFrame(rng.random((len(qkey.unique()), len(miss))), index=qkey.unique(), columns=miss) < rate
        fp = full(surv_f.notna())
        fp[miss] = u.reindex(qkey).set_axis(dates).values
        return fp
    universes = {"listed stocks only (as backtested)": (set(surv), False, False),
                 "+ delisted / merged, fair estimate": (set(surv) | set(gone), False, True),
                 "+ delisted / merged, worst case": (set(surv) | set(gone), False, False),
                 "+ delisted, worst case, failures written to zero": (set(surv) | set(gone), True, False),
                 "+ no price file (still trading), fair estimate": (set(surv) | set(gap_), False, True),
                 "+ both, fair estimate": (set(allcols), False, True)}
    out = []
    sim = lambda sc, P, per: pf.simulate(sc.loc[per[0]:per[1]], P["open"], P["close"], ctx.cfg(), lab.ms, lab.ind,
                                         start=per[0], end=per[1], V=P["volume"])
    for rules_name, use_fund in (("CAN SLIM rules", True), ("price rules only", False)):
        for pname, per in PERIODS.items():
            for uname, (cols, zero, fair) in universes.items():
                if fair and not use_fund:
                    continue
                P = Pq[zero]
                draws = []
                for _ in range(N_DRAW if fair else 1):
                    m = M(cols)
                    if fair:
                        m["fund_pass"] = draw()
                    r = sim(score(X, m, rules, use_fund), P, per)
                    tr = r.trades
                    mt = tr[tr.sym.isin(miss)] if len(tr) else tr
                    draws.append({"CAGR %": r.stats["CAGR %"], "Sharpe": r.stats["Sharpe"], "maxDD %": r.stats["maxDD %"],
                                  "trades": len(tr), "trades in added stocks": len(mt),
                                  "avg return of those %": round(mt.ret.mean() * 100, 1) if len(mt) else np.nan})
                d = pd.DataFrame(draws).median().round(2).to_dict()
                if fair:
                    c = pd.DataFrame(draws)["CAGR %"]
                    d["CAGR range of draws"] = f"{c.min()} .. {c.max()}"
                out.append({"rules": rules_name, "period": pname, "universe": uname, **d})
                print(f"  {rules_name:<16} {pname:<8} {uname:<50} CAGR {d['CAGR %']:>5}  Sharpe {d['Sharpe']:>5}  "
                      f"maxDD {d['maxDD %']:>6}  added-stock trades {d['trades in added stocks']:.0f}", flush=True)
    t = pd.DataFrame(out)
    T = t.set_index(["rules", "period", "universe"])
    v = lambda p, u, c="CAGR %", r="CAN SLIM rules": T.loc[(r, p, u), c]
    base, fair_dl, worst_dl, zero_dl, fair_gap, fair_both = list(universes)
    bias = {p: round(v(p, base) - v(p, fair_dl), 1) for p in PERIODS}
    takeaway = (f"{len(gone)} stocks delisted or merged since 2014 ({sum(fail.values())} ended badly); most had become "
                f"too small to trade long before they vanished. Screener has no fundamentals for them, so they were "
                f"given the fundamental pass rate of listed stocks ({rate:.0%}). Fair estimate: 2016-22 return "
                f"{v('2016-22', base)}% -> {v('2016-22', fair_dl)}% a year (worst drop {v('2016-22', base, 'maxDD %')}% -> "
                f"{v('2016-22', fair_dl, 'maxDD %')}%), 2023-26 {v('2023+', base)}% -> {v('2023+', fair_dl)}%. "
                f"Worst case (all of them pass): 2016-22 {v('2016-22', worst_dl)}% with a {v('2016-22', worst_dl, 'maxDD %')}% "
                f"worst drop, 2023-26 {v('2023+', worst_dl)}%. Writing failures down to zero changes nothing - the system "
                f"never still held a stock when it died. ")
    worst = max(bias.values())
    decision = (f"Missing dead stocks flatter the return by about {max(worst, 0)} points a year at most - the edge survives"
                if worst < 3 else
                f"Missing dead stocks flatter the return by about {worst} points a year - backtest returns are that much too high")
    takeaway += decision + "."
    yrs = info.loc[info.gone, "last"].dt.year.value_counts().sort_index()
    body = ("**Delisted or merged equity stocks by year they stopped trading.** "
            + ", ".join(f"{y}: {n}" for y, n in yrs.items())
            + f".\n\n**Still trading, liquid on {last_scan.date()}, but not in the backtest cache:** "
            f"{', '.join(sorted(now_liquid)) or 'none'}. Some have price files added after the cache was built; the "
            "rest are in the trade-to-trade (BE) segment, which the scanner does not download.\n\n"
            f"Notes: bhavcopy data ends {L.date()}. Sanity check: the listed-only pool rebuilt here differs from the "
            f"backtest pool in {diff} stock-days. Fair-estimate rows are the median of {N_DRAW} random draws (range shown).")
    return Outcome(t, decision, takeaway, body, status="Checked")


EXPERIMENT = Experiment(
    slug="survivorship", title="Do the backtests only look good because dead stocks are missing?",
    question="The price data only holds stocks listed today, so every stock that went bust or was delisted since "
             "2016 is invisible to the backtest. How much does that flatter the results?",
    tags="survivorship bias, delisted, realism, evidence", bar=None, run=run,
    method="NSE bhavcopies 2014-2026 (every stock that traded, series EQ/BE/BZ) rebuilt with the same split/bonus "
           "adjustment as the live price files; renamed stocks matched by ISIN. Missing stocks get the same price "
           "rules and are assumed to pass the fundamental rules (worst case). Same simulator, costs and market "
           "filter. A sanity run rebuilds the live pool from scratch and must match it.")
