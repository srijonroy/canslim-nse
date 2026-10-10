"""Daily portfolio simulator for a ranked stock list.

Mechanics (all decided at the close, executed at the NEXT day's open):
  * every rebalance date: rank eligible stocks by score; hold up to `n` names,
    keeping an existing holding while its rank <= `keep_rank` (cuts churn)
  * stop loss: a close <= entry * (1 - stop) sells at the next open (book: 7-8%)
  * market filter (book's M): 'none' | 'no_new' (no new buys in a correction)
    | 'cash' (also sell everything in a correction)
  * costs per side; idle cash earns `cash_yield` p.a. (Indian liquid-fund proxy)
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Config:
    n: int = 10
    keep_rank: int = 30
    stop: float = 0.08            # None/0 disables
    market: str = "none"          # none | no_new | cash
    cost: float = 0.003           # per side
    cash_yield: float = 0.06
    max_per_group: int = 3        # diversification: max holdings per industry (0 = off)
    # extra sell rules from the book (all off by default)
    exit_ma50: bool = False       # close < 50-day MA on volume >= 1.5x average
    profit_take: float = 0.0      # take profit at +x (book 20-25%) ...
    hold8: bool = False           # ... unless +20% within 3 weeks of entry -> hold 8 weeks first
    vol_stop: float = 0.0         # stop at k * 1-month sigma below entry, floored 8%, capped 30%
    market_exit: str = "none"     # none | losers: in a correction sell positions below entry
    # "ride" mode for winners (off by default): once a holding is up >= ride_after it is no longer
    # sold for dropping out of the ranking; it exits only on ride_exit
    ride_after: float = 0.0       # e.g. 0.20; 0 = off
    ride_exit: str = "ma200"      # ma200 | ma150 | trail  (close below the MA, or trail% below peak close)
    trail: float = 0.25
    ride_scope: str = "all"       # all | reentry: ride mode only for a stock bought again after an earlier sale
    # pyramiding (book rule 12, off by default): ((gain_from_first_buy, fraction_of_slot), ...); the first entry
    # is the initial buy (gain 0), later ones are added at the next open once the close is up that much
    pyramid: tuple = ()


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    exposure: pd.Series
    stats: dict = field(default_factory=dict)


def simulate(score: pd.DataFrame, O: pd.DataFrame, C: pd.DataFrame, cfg: Config,
             mstate: pd.Series | None = None, industry: dict | None = None,
             start=None, end=None, entry_ok: pd.DataFrame | None = None, V: pd.DataFrame | None = None) -> Result:
    days = C.loc[start:end].index
    rebal = set(score.index)
    o, c = O.reindex(days), C.reindex(days)
    cols = {s: i for i, s in enumerate(c.columns)}
    ov, cv = o.values, c.values
    need_aux = cfg.exit_ma50 or cfg.vol_stop
    if need_aux:
        full = C.loc[:end]
        ma50v = full.rolling(50, min_periods=40).mean().reindex(days).values
        sigv = full.pct_change(fill_method=None).rolling(60, min_periods=40).std().reindex(days).values
        if V is not None:
            vfull = V.reindex(full.index)
            vv = vfull.reindex(days).values
            avgvv = vfull.rolling(50, min_periods=40).mean().reindex(days).values
    if cfg.ride_after and cfg.ride_exit in ("ma200", "ma150"):
        w = int(cfg.ride_exit[2:])
        ridema = C.loc[:end].rolling(w, min_periods=int(w * 0.8)).mean().reindex(days).values
    ind = industry or {}
    cash, pos = 1.0, {}             # pos: sym -> dict(shares, entry, since)
    pending_sell, pending_buy, sold_before, pending_add = set(), [], set(), []
    eq, expo, trades = [], [], []
    daily_rf = (1 + cfg.cash_yield) ** (1 / 252) - 1
    for k, d in enumerate(days):
        # 1) execute yesterday's decisions at today's open
        for s in list(pending_sell):
            p = ov[k, cols[s]]
            if np.isnan(p):
                continue             # no print today; try again tomorrow
            h = pos.pop(s)
            sold_before.add(s)
            cash += h["shares"] * p * (1 - cfg.cost)
            ret = (h["shares"] * p * (1 - cfg.cost) / h["spent"] - 1 if h.get("adds")
                   else p / h["entry"] * (1 - cfg.cost) ** 2 - 1)
            trades.append({"sym": s, "entry_date": h["since"], "exit_date": d, "entry": h["entry"],
                           "exit": p, "ret": ret, "why": h.get("why", ""), "adds": h.get("adds", 0)})
            pending_sell.discard(s)
        for s in pending_add:                       # pyramiding: add to a holding that is up
            h = pos.get(s)
            p = ov[k, cols[s]]
            if h is None or s in pending_sell or np.isnan(p):
                continue
            amt = min(h["slot"] * cfg.pyramid[h["tr"] - 1][1], cash)
            if amt > 0:
                h["shares"] += amt * (1 - cfg.cost) / p
                h["spent"] += amt
                h["adds"] = h.get("adds", 0) + 1
                cash -= amt
        pending_add = []
        if pending_buy:
            port = cash + sum(h["shares"] * np.nan_to_num(cv[k - 1, cols[s]]) for s, h in pos.items())
            slot = port / cfg.n
            for s in pending_buy:
                p = ov[k, cols[s]]
                frac0 = cfg.pyramid[0][1] if cfg.pyramid else 1.0
                if np.isnan(p) or s in pos or cash < slot * frac0 * 0.5:
                    continue
                spend = min(slot * frac0, cash)
                pos[s] = {"shares": spend * (1 - cfg.cost) / p, "entry": p, "since": d, "k0": k,
                          "can_ride": cfg.ride_scope == "all" or s in sold_before,
                          "spent": spend, "slot": slot, "tr": 1}
                if cfg.vol_stop:
                    sg = sigv[k - 1, cols[s]] if k else np.nan
                    pos[s]["stop"] = float(np.clip(cfg.vol_stop * (sg if sg == sg else 0.03) * np.sqrt(21), 0.08, 0.30))
                cash -= spend
            pending_buy = []
        # 2) mark to market at the close
        cash *= 1 + daily_rf
        val = 0.0
        for s, h in pos.items():
            px = cv[k, cols[s]]
            if np.isnan(px):     # carry last known price
                px = h.get("last", h["entry"])
            h["last"] = px
            h["peak"] = max(h.get("peak", h["entry"]), px)
            val += h["shares"] * px
        eq.append(cash + val)
        expo.append(val / (cash + val))
        # 3) decisions at the close
        for s, h in pos.items():
            j, gain, age = cols[s], h["last"] / h["entry"] - 1, k - h["k0"]
            if cfg.pyramid and h["tr"] < len(cfg.pyramid) and gain >= cfg.pyramid[h["tr"]][0]:
                pending_add.append(s)
                h["tr"] += 1
            if cfg.ride_after and not h.get("ride") and h.get("can_ride", True) and gain >= cfg.ride_after:
                h["ride"] = True
            if h.get("ride"):
                if cfg.ride_exit == "trail":
                    out = h["last"] <= h["peak"] * (1 - cfg.trail)
                else:
                    out = h["last"] < ridema[k, j]          # NaN MA -> False -> keep
                if out:
                    pending_sell.add(s); h["why"] = f"ride exit ({cfg.ride_exit})"
                continue
            if cfg.stop and h["last"] <= h["entry"] * (1 - cfg.stop):
                pending_sell.add(s); h["why"] = "stop"
            elif cfg.vol_stop and h["last"] <= h["entry"] * (1 - h["stop"]):
                pending_sell.add(s); h["why"] = "vol stop"
            elif cfg.exit_ma50 and V is not None and cv[k, j] < ma50v[k, j] and vv[k, j] >= 1.5 * avgvv[k, j]:
                pending_sell.add(s); h["why"] = "50dma break on volume"
            elif cfg.profit_take:
                if cfg.hold8 and age <= 15 and gain >= 0.20:
                    h["hold_until"] = h["k0"] + 40          # book: fast +20% -> hold at least 8 weeks
                if gain >= cfg.profit_take and k >= h.get("hold_until", -1):
                    pending_sell.add(s); h["why"] = "profit take"
        if d in rebal:
            st = mstate.get(d, "CONFIRMED_UPTREND") if mstate is not None else "CONFIRMED_UPTREND"
            bad = st not in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE")   # book: buy only in confirmed uptrends
            row = score.loc[d].dropna().sort_values(ascending=False)
            rank = pd.Series(np.arange(1, len(row) + 1), index=row.index)
            for s, h in pos.items():
                if s in pending_sell or h.get("ride"):
                    continue
                if rank.get(s, 10 ** 9) > cfg.keep_rank:
                    pending_sell.add(s); h["why"] = "rank"
                elif bad and cfg.market == "cash":
                    pending_sell.add(s); h["why"] = "market"
                elif bad and cfg.market_exit == "losers" and h["last"] < h["entry"]:
                    pending_sell.add(s); h["why"] = "market (loser)"
            if not (bad and cfg.market in ("no_new", "cash")):
                keep = [s for s in pos if s not in pending_sell]
                free = cfg.n - len(keep)
                groups = pd.Series([ind.get(s) for s in keep]).value_counts().to_dict()
                for s in row.index:
                    if free <= 0:
                        break
                    if s in pos:
                        continue
                    if entry_ok is not None and not (s in entry_ok.columns and bool(entry_ok.at[d, s])):
                        continue
                    g = ind.get(s)
                    if cfg.max_per_group and g and groups.get(g, 0) >= cfg.max_per_group:
                        continue
                    pending_buy.append(s)
                    groups[g] = groups.get(g, 0) + 1
                    free -= 1
    equity = pd.Series(eq, index=days)
    res = Result(equity, pd.DataFrame(trades), pd.Series(expo, index=days))
    res.stats = stats(equity, res.trades, res.exposure)
    return res


def stats(equity: pd.Series, trades: pd.DataFrame | None = None, exposure=None, rf=0.06) -> dict:
    r = equity.pct_change().dropna()
    yrs = len(r) / 252
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = r.std() * np.sqrt(252)
    dd = (equity / equity.cummax() - 1).min()
    out = {"CAGR %": round(cagr * 100, 1), "vol %": round(vol * 100, 1),
           "Sharpe": round((cagr - rf) / vol, 2) if vol else np.nan,
           "maxDD %": round(dd * 100, 1),
           "Calmar": round(cagr / -dd, 2) if dd < 0 else np.nan}
    if trades is not None and len(trades):
        out.update({"trades/yr": round(len(trades) / yrs, 0),
                    "win %": round((trades.ret > 0).mean() * 100, 0),
                    "avg win %": round(trades.ret[trades.ret > 0].mean() * 100, 1),
                    "avg loss %": round(trades.ret[trades.ret <= 0].mean() * 100, 1)})
    if exposure is not None:
        out["invested %"] = round(exposure.mean() * 100, 0)
    return out


def yearly(equity: pd.Series) -> pd.Series:
    y = equity.resample("YE").last()
    first = equity.iloc[0]
    return (y / y.shift().fillna(first) - 1).mul(100).round(1).set_axis(y.index.year)
