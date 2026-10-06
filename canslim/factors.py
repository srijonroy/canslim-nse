"""Factor library. Every factor is known at the close of its date (no look-ahead).

Book (O'Neil) factors and the research that independently backs them:
  C  earnings: np_yoy, accel, sales_yoy, sue, streak    (PEAD / earnings momentum:
                                                          Bernard & Thomas 1989; Chan, Jegadeesh & Lakonishok 1996)
  A  annual:   ttm_cagr3, roe                            (profitability: Novy-Marx 2013)
  N  new high: prox_high, new_high                       (52-week-high effect: George & Hwang 2004)
  S  demand:   ud_vol, vol_surge                         (IBD accumulation/distribution)
  L  leader:   rs_ibd, mom_12_1, ram                     (momentum: Jegadeesh & Titman 1993;
                                                          vol-scaled: Barroso & Santa-Clara 2015)
  I  sponsor:  inst_chg                                   (FII+DII holding change)
  Group:       group_rs                                  (industry momentum: Moskowitz & Grinblatt 1999)
  Hazards:     vol60, max_ret21, ext50                    (lottery/MAX effect: Bali et al. 2011;
                                                          book: don't chase >5-10% past pivot)
"""
import numpy as np
import pandas as pd

MIN_PRICE = 20
MIN_TURNOVER = 3e7        # Rs 3 Cr median daily value (was 5 Cr until 2026-10-06; user choice)


def price_factors(P: dict) -> dict:
    c, h, v = P["close"], P["high"], P["volume"]
    r = c.pct_change(fill_method=None)
    F = {}
    ret = lambda a, b: c.shift(a) / c.shift(b) - 1
    F["rs_ibd"] = 0.4 * ret(0, 63) + 0.2 * ret(63, 126) + 0.2 * ret(126, 189) + 0.2 * ret(189, 252)
    F["mom_12_1"] = ret(21, 252)
    F["mom_6_1"] = ret(21, 126)
    vol1y = r.rolling(252, min_periods=200).std()
    F["ram"] = ret(0, 252) / (vol1y * np.sqrt(252))
    hi252 = h.rolling(252, min_periods=200).max()
    F["prox_high"] = c / hi252
    F["new_high"] = (h.rolling(10).max() >= hi252).astype(float).where(hi252.notna())
    ma50, ma150, ma200 = (c.rolling(n, min_periods=int(n * .9)).mean() for n in (50, 150, 200))
    F["trend"] = ((c > ma50) & (ma50 > ma150) & (ma150 > ma200) & (ma200 > ma200.shift(21))).astype(float) \
        .where(ma200.notna())
    up = v.where(r > 0, 0).rolling(50, min_periods=40).sum()
    dn = v.where(r < 0, 0).rolling(50, min_periods=40).sum()
    F["ud_vol"] = np.log((up + 1) / (dn + 1))
    avgv = v.rolling(50, min_periods=40).mean()
    F["vol_surge"] = (v / avgv).rolling(5).max()
    F["vol60"] = r.rolling(60, min_periods=50).std()
    F["max_ret21"] = r.rolling(21).max()
    F["ext50"] = c / ma50 - 1
    F["tight"] = -(c.rolling(15).std() / c)                    # higher = tighter recent action
    F["turnover"] = (c * v).rolling(50, min_periods=40).median()
    return F


def universe_mask(P: dict, F: dict) -> pd.DataFrame:
    c = P["close"]
    hist = c.notna().rolling(252, min_periods=1).sum() >= 200
    return (c >= MIN_PRICE) & (F["turnover"] >= MIN_TURNOVER) & hist


def _cap(g, lo=-100, hi=300):
    return g.clip(lo, hi)


def fundamental_events(fund: dict) -> dict:
    """Per symbol: DataFrame indexed by the date results became known, with the
    earnings metrics as of that announcement."""
    ev = {}
    for sym, f in fund.items():
        q = f["q"].copy()
        if len(q) < 6:
            continue
        np4 = q.np.shift(4)
        g = np.where(np4 > 0, (q.np / np4 - 1) * 100, np.where(q.np > 0, 100.0, np.nan))
        q["np_yoy"] = _cap(pd.Series(g, index=q.index))
        s4 = q.sales.shift(4)
        q["sales_yoy"] = _cap((q.sales / s4 - 1) * 100).where(s4 > 0)
        q["accel"] = q.np_yoy - q.np_yoy.shift(1)
        d = q.np - np4
        q["sue"] = d / d.rolling(8, min_periods=4).std().shift(1)
        q["streak"] = (q.np_yoy >= 20).astype(int).groupby((q.np_yoy < 20).cumsum()).cumsum()
        ttm = q.np.rolling(4).sum()
        ttm12 = ttm.shift(12)
        q["ttm_cagr3"] = (((ttm / ttm12) ** (1 / 3) - 1) * 100).where((ttm12 > 0) & (ttm > 0))
        q["npm_chg"] = q.npm - q.npm.shift(4)
        q["np_pos"] = (q.np > 0).astype(float)
        q["ttm_np"] = ttm
        e = q.set_index("known")[["np_yoy", "sales_yoy", "accel", "sue", "streak", "ttm_cagr3",
                                   "npm_chg", "np_pos", "ttm_np"]]
        e = e[~e.index.duplicated(keep="last")].sort_index()
        # ROE: latest annual profit over equity, known 60 days after FY end
        roe = (f["a_np"] / f["equity"]).dropna() * 100
        roe.index = roe.index + pd.Timedelta(days=60)
        e = e.join(roe.rename("roe"), how="outer").sort_index()
        e["roe"] = e["roe"].ffill()
        inst = f["inst"].diff().dropna()
        inst.index = inst.index + pd.Timedelta(days=21)
        e = e.join(inst.rename("inst_chg"), how="outer").sort_index()
        e[e.columns.drop(["roe", "inst_chg"])] = e[e.columns.drop(["roe", "inst_chg"])].ffill()
        e = e[~e.index.duplicated(keep="last")]
        ann = pd.Series(q["known"].values, index=q["known"].values)
        ann = ann[~ann.index.duplicated()]
        # announcement date as a day number, so it survives in float panels
        e["last_ann"] = (ann.reindex(e.index).ffill().astype("datetime64[ns]").astype("int64") // 86_400_000_000_000)             .where(ann.reindex(e.index).ffill().notna())
        ev[sym] = e
    return ev


def fundamental_panel(events: dict, dates: pd.DatetimeIndex, cols) -> dict:
    """Wide panels (date x symbol) of fundamental metrics as known on each date."""
    out = {k: {} for k in cols}
    for sym, e in events.items():
        e = e[~e.index.duplicated(keep="last")]
        x = e.reindex(e.index.union(dates)).ffill().reindex(dates)
        for k in cols:
            out[k][sym] = x[k]
    return {k: pd.DataFrame(v, index=dates) for k, v in out.items()}


def group_rs(rs_rank: pd.DataFrame, industry: dict) -> pd.DataFrame:
    """Industry-group strength: mean RS percentile of the group's members (>=3 members)."""
    ind = pd.Series(industry).reindex(rs_rank.columns)
    out = pd.DataFrame(index=rs_rank.index, columns=rs_rank.columns, dtype=float)
    for g, members in ind.dropna().groupby(ind.dropna()):
        m = list(members.index)
        if len(m) < 3:
            continue
        gm = rs_rank[m].mean(axis=1).where(rs_rank[m].notna().sum(axis=1) >= 3)
        out[m] = np.repeat(gm.values[:, None], len(m), axis=1)
    return out
