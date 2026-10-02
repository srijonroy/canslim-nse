"""Big-winner study: what did NSE stocks look like before they doubled, and how often
does a stock with that profile actually double?

Design (fixed before looking at results):
  * Universe: price >= 10, median daily value >= Rs 0.5 Cr, >= 200 days of history,
    earnings history available. Wider than the scanner on purpose (small caps count);
    size is recorded as a feature.
  * Label: max close over the next 252 trading days >= 2x the next day's open.
    Also recorded: 12-month end return and worst drop from entry within the year.
  * DISCOVER on start dates 2016-2021, CHECK once on 2023-2025. 2022 is an embargo year
    so no discovery label window overlaps the check period.
  * Earnings features are as known on the announcement date (point-in-time).
  * Caveat: price files cover currently listed NSE symbols only (delisted failures missing),
    which flatters hit rates in both periods equally.

usage: python -m canslim.winners
"""
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import data, factors
from canslim.research import build

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "research" / "winners"
DISCOVER = ("2016-01-01", "2021-12-31")
CHECK = ("2023-01-01", "2025-12-31")
H = 252
MIN_PRICE, MIN_VALUE = 10, 5e6
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)


# ------------------------------------------------------------------ earnings features
EARN_COLS = ["np_yoy", "sales_yoy", "sales_accel", "np_accel", "sales_min2", "np_min2", "sales_streak",
             "opm", "opm_chg", "opm_chg_q", "npm_chg", "record_sales", "record_np", "ttm_cagr3", "roe",
             "sue", "streak", "inst_chg", "last_ann"]


def earnings_events(fund: dict) -> dict:
    """Per symbol: metrics stamped on the date each quarter's result became known."""
    base = factors.fundamental_events(fund)
    ev = {}
    for sym, f in fund.items():
        if sym not in base:
            continue
        q = f["q"].copy()
        raw = json.loads((data.FUND / f"{sym}.json").read_text()).get("history") or {}
        q["opm"] = data._dated(raw.get("OPM")).reindex(q.index)
        np4, s4 = q.np.shift(4), q.sales.shift(4)
        q["np_yoy"] = factors._cap(pd.Series(np.where(np4 > 0, (q.np / np4 - 1) * 100,
                                                      np.where(q.np > 0, 100.0, np.nan)), index=q.index))
        q["sales_yoy"] = factors._cap((q.sales / s4 - 1) * 100).where(s4 > 0)
        q["sales_accel"] = q.sales_yoy - q.sales_yoy.shift(1)
        q["np_accel"] = q.np_yoy - q.np_yoy.shift(1)
        q["sales_min2"] = np.fmin(q.sales_yoy, q.sales_yoy.shift(1))
        q["np_min2"] = np.fmin(q.np_yoy, q.np_yoy.shift(1))
        q["sales_streak"] = (q.sales_yoy >= 15).astype(int).groupby((q.sales_yoy < 15).cumsum()).cumsum()
        q["opm_chg"] = q.opm - q.opm.shift(4)
        q["opm_chg_q"] = q.opm - q.opm.shift(1)
        q["record_sales"] = (q.sales >= q.sales.cummax()).astype(float).where(q.index >= q.index[min(4, len(q) - 1)])
        q["record_np"] = ((q.np >= q.np.cummax()) & (q.np > 0)).astype(float).where(q.index >= q.index[min(4, len(q) - 1)])
        new = q.set_index("known")[["sales_accel", "np_accel", "sales_min2", "np_min2", "sales_streak", "opm",
                                    "opm_chg", "opm_chg_q", "record_sales", "record_np"]]
        new = new[~new.index.duplicated(keep="last")]
        e = base[sym].join(new, how="outer").sort_index()
        e[new.columns] = e[new.columns].ffill()
        ev[sym] = e[~e.index.duplicated(keep="last")]
    return ev


# ------------------------------------------------------------------ dataset
def dataset() -> pd.DataFrame:
    cache = data.CACHE / "winners_ds.pkl"
    fund_mtime = max(f.stat().st_mtime for f in data.FUND.glob("*.json"))
    if cache.exists() and cache.stat().st_mtime > fund_mtime:
        log("using cached dataset")
        return pd.read_pickle(cache)
    log("building price factors + base fundamentals (research.build) ...")
    B = build()
    P, S, dates = B["P"], B["S"], B["dates"]
    c, o = P["close"], P["open"]
    log(f"build done: {c.shape[1]} symbols, {len(dates)} weekly dates; computing labels")
    entry = o.shift(-1)
    fmax = c.iloc[::-1].rolling(H, min_periods=150).max().iloc[::-1].shift(-1)
    fmin = c.iloc[::-1].rolling(H, min_periods=150).min().iloc[::-1].shift(-1)
    pos = pd.Series(np.arange(len(c)), index=c.index)
    full = pos + H < len(c)                                  # a whole year of future exists
    lab = {"doubled": (fmax / entry >= 2).astype(float).where(fmax.notna() & entry.notna()),
           "max_gain": fmax / entry - 1, "worst": fmin / entry - 1, "ret12": c.shift(-H) / entry - 1}
    lab = {k: v.where(full, axis=0).reindex(dates) for k, v in lab.items()}
    hist = c.notna().rolling(252, min_periods=1).sum() >= 200
    univ = ((c >= MIN_PRICE) & hist).reindex(dates) & (S["turnover"] >= MIN_VALUE)
    log("earnings events with margins / records / streaks ...")
    ev = earnings_events(B["fund"])
    FP = factors.fundamental_panel(ev, dates, EARN_COLS)
    FP = {k: v.reindex(columns=c.columns) for k, v in FP.items()}
    day_no = pd.Series(dates.values.astype("datetime64[D]").astype("int64"), index=dates)
    FP["days_since_ann"] = FP.pop("last_ann").rsub(day_no, axis=0).where(lambda x: x >= 0)
    univ &= FP["np_yoy"].notna()
    feats = {}
    for k in ("prox_high", "trend", "ext50", "vol60", "mom_6_1", "mom_12_1", "ud_vol", "tight", "new_high",
              "vol_surge", "max_ret21", "group_rs"):
        feats[k] = S[k]
    feats["rs"] = S["rs_ibd"].where(univ).rank(axis=1, pct=True) * 99      # RS rating within this universe
    feats["size_pct"] = S["turnover"].where(univ).rank(axis=1, pct=True) * 100
    feats["value_cr"] = S["turnover"] / 1e7
    feats["ret6"] = (c / c.shift(126) - 1).reindex(dates)
    feats.update(FP)
    log("stacking to long table ...")
    cols = {k: v.where(univ).stack(future_stack=True) for k, v in {**feats, **lab}.items()}
    df = pd.DataFrame(cols)
    df = df[univ.stack(future_stack=True).reindex(df.index).fillna(False)]
    df.index.names = ["date", "sym"]
    ind = pd.Series({k: f["industry"] for k, f in B["fund"].items()})
    df["industry"] = ind.reindex(df.index.get_level_values("sym")).values
    df.to_pickle(cache)
    log(f"dataset: {len(df):,} stock-weeks, {df.index.get_level_values('sym').nunique()} stocks")
    return df


# ------------------------------------------------------------------ analysis
BINS = {   # fixed, human-readable bins for earnings features
    "np_yoy": [-np.inf, 0, 25, 50, 100, np.inf], "sales_yoy": [-np.inf, 0, 10, 20, 40, np.inf],
    "sales_accel": [-np.inf, -10, 0, 10, np.inf], "np_accel": [-np.inf, -25, 0, 25, np.inf],
    "sales_min2": [-np.inf, 0, 15, 25, np.inf], "streak": [-0.5, 0.5, 1.5, 3.5, np.inf], "np_min2": [-np.inf, 0, 25, 50, np.inf],
    "sales_streak": [-0.5, 0.5, 1.5, 3.5, np.inf], "opm": [-np.inf, 5, 10, 15, 25, np.inf],
    "opm_chg": [-np.inf, -3, 0, 3, 6, np.inf], "opm_chg_q": [-np.inf, -2, 0, 2, np.inf],
    "npm_chg": [-np.inf, -2, 0, 2, 5, np.inf], "record_sales": [-0.5, 0.5, 1.5], "record_np": [-0.5, 0.5, 1.5],
    "ttm_cagr3": [-np.inf, 0, 15, 25, 40, np.inf], "roe": [-np.inf, 0, 10, 15, 20, 30, np.inf],
    "sue": [-np.inf, 0, 1, 2, np.inf], "inst_chg": [-np.inf, -0.5, 0.5, 2, np.inf],
    "days_since_ann": [-0.5, 14, 30, 60, np.inf], "trend": [-0.5, 0.5, 1.5], "new_high": [-0.5, 0.5, 1.5],
    "prox_high": [0, 0.6, 0.75, 0.85, 0.95, 1.01], "ret6": [-np.inf, 0, 0.25, 0.5, 1, np.inf],
    "value_cr": [0, 1, 5, 25, 100, np.inf],
}


def lift_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per feature bucket: how often stocks in it doubled, in each period, vs that period's base rate."""
    rows = []
    periods = {"discover": df.loc[DISCOVER[0]:DISCOVER[1]], "check": df.loc[CHECK[0]:CHECK[1]]}
    base = {p: d.doubled.mean() for p, d in periods.items()}
    feats = [c for c in df.columns if c not in ("doubled", "max_gain", "worst", "ret12", "industry")]
    for f in feats:
        for p, d in periods.items():
            x = d[f]
            if f in BINS:
                b = pd.cut(x, BINS[f])
            else:                                   # quintiles within each date
                b = x.groupby(level="date").rank(pct=True).pipe(lambda r: pd.cut(r, [0, .2, .4, .6, .8, 1.0],
                                                                                   labels=["Q1 low", "Q2", "Q3", "Q4", "Q5 high"]))
            g = d.groupby(b, observed=True)
            t = pd.DataFrame({"n": g.size(), "hit %": g.doubled.mean() * 100,
                              "median 12m %": g.ret12.median() * 100,
                              "fell 30%+ %": g.worst.apply(lambda w: (w <= -0.3).mean() * 100)})
            t["lift"] = t["hit %"] / (base[p] * 100)
            for lvl, r in t.iterrows():
                rows.append({"feature": f, "bucket": str(lvl), "period": p, **r.round(2).to_dict()})
    out = pd.DataFrame(rows).pivot_table(index=["feature", "bucket"], columns="period",
                                         values=["n", "hit %", "lift", "median 12m %", "fell 30%+ %"], sort=False)
    out.columns = [f"{a} {b}" for a, b in out.columns]
    return out, base


def model_book(df: pd.DataFrame) -> pd.DataFrame:
    """First week of each doubling run per stock: the 'launch' snapshot."""
    d = df[df.doubled == 1].reset_index()
    d = d.sort_values(["sym", "date"])
    gap = d.groupby("sym").date.diff().dt.days
    launches = d[(gap.isna()) | (gap > 60)]
    return launches.set_index(["date", "sym"])


FEATS_MODEL = ["rs", "prox_high", "trend", "ext50", "vol60", "mom_6_1", "ud_vol", "tight", "vol_surge", "max_ret21",
               "group_rs", "size_pct", "ret6", "np_yoy", "sales_yoy", "sales_accel", "np_accel", "sales_min2",
               "np_min2", "sales_streak", "opm", "opm_chg", "opm_chg_q", "npm_chg", "record_sales", "record_np",
               "ttm_cagr3", "roe", "sue", "days_since_ann"]   # inst_chg: shareholding history starts 2023 (Screener), cannot train on it


def model(df: pd.DataFrame):
    """Gradient-boosted trees trained on DISCOVER only, scored on CHECK."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    tr = df.loc[DISCOVER[0]:DISCOVER[1]].dropna(subset=["doubled"])
    te = df.loc[CHECK[0]:CHECK[1]].dropna(subset=["doubled"])
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                         min_samples_leaf=400, l2_regularization=1.0, random_state=7)
    log(f"training on {len(tr):,} discover rows ({tr.doubled.mean():.1%} doubled)")
    clf.fit(tr[FEATS_MODEL], tr.doubled)
    out = {}
    for name, d in (("discover (in-sample)", tr), ("check (out-of-sample)", te)):
        p = pd.Series(clf.predict_proba(d[FEATS_MODEL])[:, 1], index=d.index)
        dec = p.groupby(level="date").rank(pct=True).pipe(lambda r: np.ceil(r * 10).clip(1, 10).astype(int))
        g = d.groupby(dec)
        t = pd.DataFrame({"n": g.size(), "hit %": g.doubled.mean() * 100, "median 12m %": g.ret12.median() * 100,
                          "mean 12m %": g.ret12.mean() * 100,
                          "fell 30%+ %": g.worst.apply(lambda w: (w <= -0.3).mean() * 100)}).round(1)
        t.index.name = "score decile (10 = best)"
        top = p.groupby(level="date", group_keys=False).nlargest(20)
        out[name] = (t, d.loc[top.index].doubled.mean() * 100, d.doubled.mean() * 100)
    log("permutation importance on a 60k sample of the check period ...")
    smp = te.sample(min(60000, len(te)), random_state=1)
    pi = permutation_importance(clf, smp[FEATS_MODEL], smp.doubled, scoring="roc_auc", n_repeats=3, random_state=1)
    imp = pd.Series(pi.importances_mean, index=FEATS_MODEL).sort_values(ascending=False).round(4)
    return clf, out, imp


def canslim_check(df: pd.DataFrame) -> pd.DataFrame:
    """How the tuned scanner's filters do as a 'big winner' detector, same universe and labels."""
    ok = ((df.trend == 1) & (df.prox_high >= 0.85) & (df.np_yoy >= 25) & ((df.sales_yoy >= 20) | (df.streak >= 2))
          & (df.ttm_cagr3 >= 15) & (df.roe >= 20) & (df.rs >= 80))
    rows = []
    for p, (a, b) in (("discover", DISCOVER), ("check", CHECK)):
        d, m = df.loc[a:b], ok.loc[a:b]
        for name, sub in (("all stocks", d), ("passes CAN SLIM filters", d[m])):
            rows.append({"period": p, "group": name, "stock-weeks": len(sub), "hit %": round(sub.doubled.mean() * 100, 1),
                         "median 12m %": round(sub.ret12.median() * 100, 1),
                         "fell 30%+ %": round((sub.worst <= -0.3).mean() * 100, 1)})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 400)
    df = dataset()
    lt, base = lift_table(df)
    lt.to_csv(OUT / "lift_table.csv")
    log(f"base rate of doubling within 12m: discover {base['discover']:.1%}, check {base['check']:.1%}")
    mb = model_book(df)
    mb.to_csv(OUT / "model_book.csv")
    log(f"model book: {len(mb)} launches by {mb.index.get_level_values('sym').nunique()} stocks")
    cs = canslim_check(df)
    cs.to_csv(OUT / "canslim_check.csv", index=False)
    print(cs.to_string(index=False), flush=True)
    clf, res, imp = model(df)
    (OUT / "model.pkl").write_bytes(pickle.dumps({"clf": clf, "features": FEATS_MODEL}))
    imp.to_csv(OUT / "importance.csv")
    for name, (t, top20, base_rate) in res.items():
        t.to_csv(OUT / f"deciles_{name.split()[0]}.csv")
        print(f"\n=== {name}: base {base_rate:.1f}% | top-20 per week {top20:.1f}%\n{t.to_string()}", flush=True)
    print("\n=== what the model leans on (check-period AUC drop when shuffled)\n" + imp.head(15).to_string())
    print("\n=== lift table (hit % = share that doubled within 12m)")
    print(lt[[c for c in lt.columns if c.startswith(("n ", "hit", "lift"))]].to_string())
    from canslim.winners_report import render_report
    log(f"report: {render_report()}")
    log("done")


if __name__ == "__main__":
    main()
