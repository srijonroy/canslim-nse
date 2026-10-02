"""Candidate systems + honest walk-forward test.

Systems (all use the same liquid universe; all decisions point-in-time):
  momentum     baseline: rank by RS alone (does anything else add value?)
  book_rules   O'Neil's CAN SLIM as hard filters, ranked by RS
  blend_fixed  book-gated, equal-weight blend of the book's factors (nothing fitted)
  blend_wf     book-gated, factor weights re-learned every January from PAST data only
               (expanding window IC, negative-IC factors dropped) -> each year is out-of-sample

Each system is run with the book's market filter (M) and 8% stop variants.

usage: python -m canslim.system
"""
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim.market import market_state_series
from canslim.research import SIGN, build

OUT = Path(__file__).resolve().parent.parent / "data" / "system"
BLEND = ["rs_ibd", "prox_high", "np_yoy", "sue", "sales_yoy", "ttm_cagr3", "roe", "ud_vol", "group_rs"]
CANDIDATES = BLEND + ["mom_12_1", "ram", "accel", "streak", "npm_chg", "tight", "vol60", "max_ret21",
                      "ext50", "inst_chg", "days_since_ann", "new_high", "vol_surge"]


def pct(x: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    return x.where(mask).rank(axis=1, pct=True)


def gates(S, U, has_f):
    """Book's minimum conditions: uptrend (Stage 2), within 25% of the 52-wk high, profitable."""
    return U & has_f & (S["trend"] == 1) & (S["prox_high"] >= 0.75) & (S["np_pos"] == 1)


def score_momentum(S, U, has_f):
    return pct(S["rs_ibd"], U & has_f)


def score_book_rules(S, U, has_f):
    rs = pct(S["rs_ibd"], U & has_f)
    ok = gates(S, U, has_f) & (S["np_yoy"] >= 25) & ((S["sales_yoy"] >= 20) | (S["streak"] >= 2)) \
        & (S["ttm_cagr3"] >= 15) & (S["roe"] >= 15) & (rs >= 0.80) & (S["prox_high"] >= 0.85)
    return rs.where(ok)


def score_blend(S, U, has_f, weights: dict | pd.DataFrame):
    g = gates(S, U, has_f)
    tot = None
    for f in (weights.columns if isinstance(weights, pd.DataFrame) else weights):
        w = weights[f]
        r = pct(S[f] * SIGN.get(f, 1), g).fillna(0.5)            # missing -> neutral
        term = r.mul(w.reindex(r.index).ffill(), axis=0) if isinstance(w, pd.Series) else r * w
        tot = term if tot is None else tot + term
    return tot.where(g)


def walk_forward_weights(S, U, has_f, fwd, h=63, min_years=3, t_min=1.0):
    """For each rebalance date: weights = mean IC per factor over data whose forward
    window had fully ENDED before the start of that calendar year. Refit yearly."""
    g = U & has_f            # IC over the whole investable universe (more stable than the gated subset)
    ic = {}
    for f in CANDIDATES:
        x = (S[f] * SIGN.get(f, 1)).where(g)
        y = fwd[h].where(g)
        ic[f] = x.rank(axis=1).corrwith(y.rank(axis=1), axis=1)
    ic = pd.DataFrame(ic)
    dates = S["rs_ibd"].index
    W = pd.DataFrame(index=dates, columns=CANDIDATES, dtype=float)
    first = dates[0]
    prior = pd.Series({f: 1 / len(BLEND) for f in BLEND}).reindex(CANDIDATES).fillna(0)
    for yr in sorted(set(dates.year)):
        cutoff = pd.Timestamp(f"{yr}-01-01") - pd.Timedelta(days=int(h * 1.5))   # fwd window ended
        hist = ic[:cutoff].dropna(how="all")
        if (cutoff - first).days < 365 * min_years or len(hist) < 50:
            W.loc[str(yr)] = prior.values          # not enough history yet: book's equal weights
            continue
        m = hist.mean()
        t = m / (hist.std() / np.sqrt(len(hist) / (h / 5)))
        w = m.where((m > 0) & (t > t_min), 0)                      # keep only reliably positive
        W.loc[str(yr)] = (w / w.sum()).values if w.sum() > 0 else prior.values
    return W, ic


def market_state(P):
    idx = pd.read_parquet(Path(__file__).resolve().parent.parent / "data" / "prices" / "NSE_NIFTY500-INDEX.parquet")
    vol = (P["close"] * P["volume"]).sum(axis=1)
    idx = idx.assign(volume=vol.reindex(idx.index)).dropna()
    idx = idx[idx.volume > 0]
    return market_state_series(idx)["state"]


def benchmarks(P, U, start, end):
    n500 = pd.read_parquet(Path(__file__).resolve().parent.parent / "data" / "prices" /
                           "NSE_NIFTY500-INDEX.parquet")["close"].loc[start:end]
    r = P["close"].pct_change(fill_method=None).clip(-0.5, 1)
    Ud = U.reindex(r.index).ffill().shift(1).fillna(False).astype(bool)
    ew = (1 + r.where(Ud).mean(axis=1).fillna(0)).loc[start:end].cumprod()
    return {"Nifty 500 (price)": n500 / n500.iloc[0], "Equal-weight liquid universe": ew / ew.iloc[0]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    B = build()
    S, U, has_f, fwd, P = B["S"], B["U"], B["has_f"], B["fwd"], B["P"]
    industry = {k: f["industry"] for k, f in B["fund"].items()}
    ms = market_state(P).reindex(P["close"].index).ffill()
    W, ic = walk_forward_weights(S, U, has_f, fwd)
    W.dropna(how="all").groupby(W.dropna(how="all").index.year).first().round(3).T \
        .to_csv(OUT / "walk_forward_weights.csv")
    print("walk-forward weights by year (0 = dropped):")
    print(W.dropna(how="all").groupby(W.dropna(how="all").index.year).first().round(2).T.to_string())
    start = pd.Timestamp("2016-01-01")          # common start for every system
    end = S["rs_ibd"].index[-1]
    scores = {
        "momentum": score_momentum(S, U, has_f),
        "book_rules": score_book_rules(S, U, has_f),
        "blend_fixed": score_blend(S, U, has_f, {f: 1 / len(BLEND) for f in BLEND}),
        "blend_wf": score_blend(S, U, has_f, W.dropna(how="all")),
    }
    rows, curves = [], {}
    for name, sc in scores.items():
        for mkt in ("none", "no_new", "cash"):
            for stop in (0.08, None):
                cfg = pf.Config(market=mkt, stop=stop)
                res = pf.simulate(sc.loc[start:], P["open"], P["close"], cfg, ms, industry, start=start)
                key = f"{name} | M={mkt} | stop={'8%' if stop else 'off'}"
                curves[key] = res.equity
                rows.append({"system": key, **res.stats})
                res.trades.to_csv(OUT / f"trades_{name}_{mkt}_{'stop' if stop else 'nostop'}.csv", index=False)
                print(key, res.stats, flush=True)
    for k, v in benchmarks(P, U, start, end).items():
        curves[k] = v
        rows.append({"system": k, **pf.stats(v)})
    table = pd.DataFrame(rows).set_index("system")
    table.to_csv(OUT / "results.csv")
    yearly = pd.DataFrame({k: pf.yearly(v) for k, v in curves.items()})
    yearly.to_csv(OUT / "yearly.csv")
    pd.DataFrame(curves).to_parquet(OUT / "curves.parquet")
    print("\n=== Results", start.date(), "->", end.date(), "(costs 0.3%/side, next-open fills)")
    print(table.sort_values("Sharpe", ascending=False).to_string())
    print("\n=== Calendar-year returns %")
    print(yearly.T.to_string())


if __name__ == "__main__":
    main()
