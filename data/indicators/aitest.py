"""Port of 'Brooks Regime & Always-In' + range-filter variants, simulated as stop-and-reverse."""
import sys, numpy as np, pandas as pd
SP = r"C:\Users\srijo\AppData\Local\Temp\claude\c--Project-asd\d43c9577-eff5-48f9-a030-fdb5ab9a2e8e\scratchpad"
COST = 0.4  # points per trade (round trip), Pepperstone US500 spread seen on chart

def ema(x, n):
    a = 2/(n+1); out = np.full(len(x), np.nan); s = np.nan
    for i, v in enumerate(x):
        if i < n-1: continue
        if np.isnan(s): s = np.mean(x[i-n+1:i+1])
        else: s = a*v + (1-a)*s
        out[i] = s
    return out

def rma(x, n):
    out = np.full(len(x), np.nan); s = np.nan
    for i in range(len(x)):
        if i < n-1 or np.isnan(x[i]): continue
        if np.isnan(s): s = np.nanmean(x[i-n+1:i+1])
        else: s = (s*(n-1) + x[i])/n
        out[i] = s
    return out

def indicator(d, emaLen=20, atrLen=14, erLen=14, adxLen=14, slopeLen=5, slopeSens=.3, sideLen=20,
              smoothLen=3, trendThresh=55, bodyFactor=.5):
    o, h, l, c = (d[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    e = ema(c, emaLen)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h-l, np.abs(h-pc), np.abs(l-pc)], axis=1); tr[0] = h[0]-l[0]
    atr = rma(tr, atrLen)
    cs = pd.Series(c)
    er = (cs - cs.shift(erLen)).abs() / cs.diff().abs().rolling(erLen).sum()
    up = np.r_[np.nan, np.diff(h)]; dn = -np.r_[np.nan, np.diff(l)]
    pdm = np.where((up > dn) & (up > 0), up, 0.); mdm = np.where((dn > up) & (dn > 0), dn, 0.)
    trr = rma(tr, adxLen)
    dip = 100*rma(pdm, adxLen)/trr; dim = 100*rma(mdm, adxLen)/trr
    dx = 100*np.abs(dip-dim)/np.where(dip+dim == 0, 1, dip+dim)
    adx = rma(np.nan_to_num(dx, nan=np.nan), adxLen)
    adxN = np.minimum(np.nan_to_num(adx)/40, 1)
    es = pd.Series(e)
    slopeN = np.minimum(((es-es.shift(slopeLen))/slopeLen).abs()/(atr*slopeSens), 1).fillna(0).to_numpy()
    above = pd.Series((c > e).astype(float)).rolling(sideLen).sum()/sideLen
    side = ((above-.5).abs()*2).fillna(0).to_numpy()
    ce = c - e; cross = (np.sign(ce) != np.sign(np.r_[np.nan, ce[:-1]])) & ~np.isnan(ce) & ~np.isnan(np.r_[np.nan, ce[:-1]])
    cc = pd.Series(cross.astype(float)).rolling(sideLen).sum().fillna(0).to_numpy()
    tfc = 1 - np.minimum(cc/(sideLen/2), 1)
    w = dict(er=.3, adx=.25, sl=.2, side=.15, cr=.1); ws = sum(w.values())
    score = (er.fillna(0).to_numpy()*w["er"] + adxN*w["adx"] + slopeN*w["sl"] + side*w["side"] + tfc*w["cr"])/ws
    tp = pd.Series(score*100).ewm(span=smoothLen, adjust=False).mean().to_numpy()
    body = np.abs(c-o)
    ph, pl = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    sbull = (body >= atr*bodyFactor) & (c > e) & (c > ph)
    sbear = (body >= atr*bodyFactor) & (c < e) & (c < pl)
    ai = np.zeros(len(c), int); s = 0
    for i in range(len(c)):
        if sbull[i]: s = 1
        elif sbear[i]: s = -1
        ai[i] = s
    return dict(o=o, h=h, l=l, c=c, ema=e, atr=atr, adx=adx, trendProb=tp, isTrend=tp >= trendThresh,
                crosses=cc, ai=ai, body=body)

def range_filter(x, lookback=20, minCross=4, strongFrac=.6, followThrough=False):
    h, l, c, o, ai = x["h"], x["l"], x["c"], x["o"], x["ai"]
    cc = x["crosses"] if lookback == 20 else None
    inR = cc >= minCross
    hi = pd.Series(h).rolling(lookback).max().shift(1).to_numpy()
    lo = pd.Series(l).rolling(lookback).min().shift(1).to_numpy()
    rng = h - l
    strong = x["body"] >= strongFrac*np.where(rng == 0, np.inf, rng)
    bull = inR & strong & (c > o) & (c > hi)
    bear = inR & strong & (c < o) & (c < lo)
    out = np.zeros(len(c), int); s = 0; pend = 0; lvl = np.nan
    for i in range(1, len(c)):
        if pend:  # follow-through check on the bar after the breakout
            if pend == 1 and c[i] > lvl: s = 1
            if pend == -1 and c[i] < lvl: s = -1
            pend = 0
        if bull[i]:
            if followThrough: pend, lvl = 1, hi[i]
            else: s = 1
        elif bear[i]:
            if followThrough: pend, lvl = -1, lo[i]
            else: s = -1
        elif inR[i]:
            if not inR[i-1]: s = 0          # just entered a range: stand aside
        elif ai[i] != ai[i-1]: s = ai[i]   # trending: take raw flips
        out[i] = s
    return out

def trend_only(x):
    return np.where(x["isTrend"], x["ai"], 0)

def simulate(pos, o, idx):
    """pos[i] decided at close of bar i, filled at open of bar i+1. Returns list of trades."""
    trades = []; cur = 0; entry = None
    for i in range(len(pos)-1):
        tgt = pos[i]
        if tgt != cur:
            px = o[i+1]
            if cur != 0:
                trades.append(dict(entry_t=idx[entry[0]], exit_t=idx[i+1], side=cur, pts=cur*(px-entry[1])-COST))
            cur = tgt; entry = (i+1, px) if tgt else None
    return pd.DataFrame(trades)

def stats(t, name):
    if t.empty: return dict(variant=name, trades=0)
    p = t.pts; eq = p.cumsum(); dd = (eq - eq.cummax()).min()
    w, lo = p[p > 0], p[p <= 0]
    return dict(variant=name, trades=len(t), win=round(100*len(w)/len(t)), avg_win=round(w.mean(), 1),
                avg_loss=round(lo.mean(), 1), total=round(p.sum()), per_trade=round(p.mean(), 2),
                max_dd=round(dd), pf=round(w.sum()/-lo.sum(), 2) if len(lo) else np.inf)

if __name__ == "__main__":
    d = pd.read_parquet(SP + r"\es5m.parquet")
    d.index = d.index.tz_convert("Asia/Kolkata")
    x = indicator(d)
    idx = d.index
    V = {
        "A raw Always In": x["ai"],
        "B raw, flat when own Regime=RANGE": trend_only(x),
        "C range filter (cross>=4)": range_filter(x, minCross=4),
        "C3 range filter (cross>=3)": range_filter(x, minCross=3),
        "C5 range filter (cross>=5)": range_filter(x, minCross=5),
        "D range filter + follow-through": range_filter(x, minCross=4, followThrough=True),
    }
    half = idx[len(idx)//2]
    rows = []
    for k, p in V.items():
        t = simulate(p, x["o"], idx)
        for per, tt in (("all", t), ("1st half", t[t.entry_t < half]), ("2nd half", t[t.entry_t >= half])):
            r = stats(tt, k); r["period"] = per; rows.append(r)
        t.to_csv(SP + rf"\ai\trades_{k.split()[0]}.csv", index=False)
    r = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("bars", len(d), idx[0], "->", idx[-1], "split at", half)
    for per in ("all", "1st half", "2nd half"):
        print("\n==", per); print(r[r.period == per].drop(columns="period").to_string(index=False))
    # today's window
    today = (idx >= "2026-10-07 12:00") & (idx <= "2026-10-07 21:00")
    sub = pd.DataFrame({"c": x["c"], "raw": x["ai"], "C": V["C range filter (cross>=4)"], "D": V["D range filter + follow-through"],
                        "regime": np.where(x["isTrend"], "T", "R"), "cross": x["crosses"]}, index=idx)[today]
    ch = sub[(sub.raw != sub.raw.shift()) | (sub.C != sub.C.shift()) | (sub.D != sub.D.shift())]
    print("\n== today 12:00-21:00 IST, state changes"); print(ch.to_string())
    np.save(SP + r"\ai\x_c.npy", x["c"])
