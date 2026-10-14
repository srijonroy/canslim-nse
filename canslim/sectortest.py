"""Test: sector (industry-group) signals from the literature, and combining them with CAN SLIM.

Literature review: data/research/insights/2026-10-14_picking-sectors-research.md

Groups = Screener basic industry (lab.ind), members = stocks in the liquid universe U on the date, >= 5 members.
Group return = equal-weight mean of members, minus the equal-weight universe mean (excess).

Part A, group level (sampled every 4 weeks, ~21 trading days). Signals fixed before running:
  base_grs     current group_rs: mean RS percentile of members                  (baseline to beat)
  mom_12_1     mean member return 12m->1m                                         (Moskowitz-Grinblatt)
  mom_12_7     mean member return 12m->6m (label kept; Novy-Marx uses 12->7)       (Novy-Marx)
  prox_high    mean member price / 52-week high                                   (George-Hwang, industry)
  br_high      share of members within 10% of their 52-week high                  (breadth, untested in literature)
  br_200       share of members above their 200-day average                       (breadth, untested)
  grs_chg      group_rs now minus 63 days ago                                     ("emerging": rising fast)
  earn_br      share of members with profit growth >= 25% AND net margin up      (industry earnings news)
  rev_3y       mean member 3-year return; expected NEGATIVE                       (Wu-Mazouz long-term reversal)
  composite    mean percentile of mom_12_7, prox_high, br_high, earn_br           (defined before running)
  lead_lag     top-3 members by turnover: last-month return minus the rest's; target = the REST's forward return (Hou 2007)
Metric: Spearman IC vs forward 63d / 126d excess group return; top-minus-bottom quintile of groups.
Periods: discovery 2016-22 (two halves), check 2023-26 (reported, not used for decisions).
t-stats are adjusted for overlapping windows (divided by sqrt(horizon/21)).

Part B, CAN SLIM + sectors (same decision bar as booktest.py, 2016-22):
  base             current system
  tilt_grs         score = RS pct + 0.5 x group_rs pct      (plain group strength as a ranking tilt)
  tilt_comp        score = RS pct + 0.5 x composite pct
  tilt_comp_1      score = RS pct + 1.0 x composite pct
  sector_leaders   separate list: stocks in top-20% composite groups with trend, within 15% of high, RS >= 70, profit growth > 0;
                   ranked by RS, max 2 per group (reported against base, not a replacement)

usage: python -m canslim.sectortest   (writes data/tune/sectortest/)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune

OUT = Path(__file__).resolve().parent.parent / "data" / "tune" / "sectortest"
LEVEL3 = "--level3" in sys.argv          # broader Screener industry level (58 groups) instead of basic industry (185)
if LEVEL3:
    OUT = OUT / "level3"
STEP, MINM = 21, 5          # STEP = trading days per sample; S/U panels are weekly, so we take every 4th week
WEEKS = 4
PERIODS = {"16-19": ("2016-01-01", "2019-12-31"), "20-22": ("2020-01-01", "2022-12-31"),
           "23-26 check": ("2023-01-01", "2026-12-31")}


def log(msg):
    print(msg, flush=True)


def grp_mean(X, mask, ind):
    """dates x stocks -> dates x groups (mean over members in mask; NaN if < MINM members)."""
    Xm = X.where(mask)
    g = Xm.T.groupby(ind).mean().T
    n = mask.T.groupby(ind).sum().T
    return g.where(n >= MINM)


def signals(lab, dates):
    S, U, c = lab.S, lab.U, lab.P["close"]
    ind = pd.Series(lab.ind).reindex(c.columns)
    keep = ind.dropna().index
    ind = ind[keep]
    sub = lambda X: X.reindex(index=dates, columns=keep)
    Ud = sub(U).fillna(False).astype(bool)
    ret = lambda a, b: c.shift(a) / c.shift(b) - 1
    rs_pct = S["rs_ibd"].where(U).rank(axis=1, pct=True)
    ma200 = c.rolling(200, min_periods=180).mean()
    stock = {
        "base_grs": rs_pct, "mom_12_1": ret(21, 252), "mom_12_7": ret(126, 252), "prox_high": S["prox_high"],
        "br_high": (S["prox_high"] >= 0.9).astype(float).where(S["prox_high"].notna()),
        "br_200": (c > ma200).astype(float).where(ma200.notna()),
        "earn_br": ((S["np_yoy"] >= 25) & (S["npm_chg"] > 0)).astype(float).where(S["np_yoy"].notna()),
        "rev_3y": ret(0, 756),
    }
    G = {k: grp_mean(sub(v), Ud, ind) for k, v in stock.items()}
    log(f"  group signals built: {len(G)} signals, {G['base_grs'].notna().sum(axis=1).median():.0f} groups/date (median)")
    # rising fast: group_rs now minus 63 trading days earlier, same membership as now
    prev = rs_pct.shift(13)                     # S is weekly: 13 weeks = ~63 trading days
    G["grs_chg"] = G["base_grs"] - grp_mean(sub(prev), Ud, ind)
    pct = {k: G[k].rank(axis=1, pct=True) for k in ("mom_12_7", "prox_high", "br_high", "earn_br")}
    G["composite"] = sum(pct.values()) / len(pct)
    # forward excess returns
    fwd = {}
    for h in (21, 63, 126, 189, 252):
        f = sub(c.shift(-h) / c - 1).where(Ud)
        f = f.sub(f.mean(axis=1), axis=0)
        fwd[h] = (f, grp_mean(f, Ud, ind))
    return G, fwd, Ud, ind, sub


def lead_lag(lab, dates, Ud, ind, sub, fwd):
    """Leaders (top 3 by turnover) last 21d return minus the rest's; target = rest's forward excess return."""
    c = lab.P["close"]
    r21 = sub(c / c.shift(21) - 1)
    to = sub(lab.S["turnover"])
    sig = pd.DataFrame(index=dates, columns=sorted(ind.unique()), dtype=float)
    tgt = {h: sig.copy() for h in (63, 126)}
    for d in dates:
        m = Ud.loc[d]
        members = ind[m[m].index]
        for g, mem in members.groupby(members):
            if len(mem) < MINM + 3:
                continue
            t = to.loc[d, mem.index].sort_values(ascending=False)
            lead, rest = t.index[:3], t.index[3:]
            sig.loc[d, g] = r21.loc[d, lead].mean() - r21.loc[d, rest].mean()
            for h in tgt:
                tgt[h].loc[d, g] = fwd[h][0].loc[d, rest].mean()
    return sig, tgt


def ic_table(G, fwd, extra=None):
    rows = []
    items = [(k, v, {h: fwd[h][1] for h in (63, 126)}) for k, v in G.items()]
    if extra:
        items.append(extra)
    for name, sig, targets in items:
        for h, tg in targets.items():
            ic = sig.rank(axis=1).corrwith(tg.rank(axis=1), axis=1).dropna()
            row = {"signal": name, "horizon": h}
            for p, (a, b) in PERIODS.items():
                x = ic.loc[a:b]
                adj = np.sqrt(h / STEP)
                row[f"IC {p}"] = round(x.mean(), 3)
                row[f"t {p}"] = round(x.mean() / x.std() * np.sqrt(len(x)) / adj, 1) if len(x) > 2 else np.nan
                # top-minus-bottom quintile of groups, average excess return per period
                q = sig.loc[a:b].rank(axis=1, pct=True)
                t_ = tg.loc[a:b]
                row[f"Q5-Q1 {p}"] = round(100 * (t_.where(q > 0.8).mean(axis=1) - t_.where(q <= 0.2).mean(axis=1)).mean(), 1)
            rows.append(row)
    return pd.DataFrame(rows)


def rising_events(G, fwd):
    """'Emerging' groups: now in the top 20% by group_rs, having been in the bottom half 63 days ago."""
    p = G["base_grs"].rank(axis=1, pct=True)
    was = p.shift(3)                                  # 3 samples x 21 days = 63 days earlier
    f = fwd[126][1]
    rows = []
    for name, m in {"rose from bottom half into top 20%": (p > 0.8) & (was <= 0.5),
                    "already top 20% (was top half)": (p > 0.8) & (was > 0.5),
                    "all groups": p.notna()}.items():
        for per, (a, b) in PERIODS.items():
            x = f.where(m).loc[a:b].stack().dropna()
            rows.append({"group type": name, "period": per, "events": len(x),
                         "median 6m excess %": round(100 * x.median(), 1), "beat universe %": round(100 * (x > 0).mean())})
    return pd.DataFrame(rows)


def persistence(G, fwd, key):
    """How long a group stays strong (top 20% by `key`), and how long its outperformance lasts after entry / exit."""
    p = G[key].rank(axis=1, pct=True)
    top = (p > 0.8).where(p.notna())
    spells = []
    for g in top.columns:
        s = top[g]
        run, start = 0, None
        for d, v in s.items():
            if v == 1:
                run, start = run + 1, start or d
            else:
                if run and pd.notna(v):                      # spell ended (ignore spells cut by missing data)
                    spells.append({"group": g, "start": start, "months": run, "ongoing": False})
                run, start = 0, None
        if run:                                              # still in the top 20% at the end of the data
            spells.append({"group": g, "start": start, "months": run, "ongoing": True})
    sp = pd.DataFrame(spells)
    srow = []
    for per, (a, b) in PERIODS.items():
        x = sp[(sp.start >= a) & (sp.start <= b)].months
        ong = int(sp[(sp.start >= a) & (sp.start <= b)].ongoing.sum())
        srow.append({"spells started in": per, "spells": len(x), "still running": ong, "median months": x.median(),
                     "25-75% months": f"{x.quantile(.25):.0f}-{x.quantile(.75):.0f}",
                     ">=3m %": round(100 * (x >= 3).mean()), ">=6m %": round(100 * (x >= 6).mean()),
                     ">=12m %": round(100 * (x >= 12).mean())})
    entry = (top == 1) & (top.shift(1) == 0)
    exit_ = (top == 0) & (top.shift(1) == 1)
    crow = []
    for name, ev in {"entered top 20%": entry, "dropped out of top 20%": exit_}.items():
        for per in ("16-19", "20-22", "23-26 check"):
            a, b = PERIODS[per]
            r = {"event": name, "period": per, "events": int(ev.loc[a:b].sum().sum())}
            for h, lab in ((21, "1m"), (63, "3m"), (126, "6m"), (189, "9m"), (252, "12m")):
                x = fwd[h][1].where(ev).loc[a:b].stack().dropna()
                r[f"{lab} excess %"] = round(100 * x.median(), 1)
            crow.append(r)
    return pd.DataFrame(srow), pd.DataFrame(crow)


def part_b(lab, G, sub):
    final = json.loads((tune.OUT / "final.json").read_text())
    rules, cfg = final["rules"], pf.Config(**final["cfg"])
    S, U = lab.S, lab.U
    base = tune.book_score(S, U, lab.has_f, rules)
    idx, cols = base.index, base.columns
    ind = pd.Series(lab.ind).reindex(cols)

    def to_stock(Gx):                    # group panel (sampled dates) -> daily stock panel (ffill, no look-ahead)
        Gd = Gx.reindex(idx).ffill(limit=WEEKS)
        out = pd.DataFrame(np.nan, index=idx, columns=cols)
        for g in Gd.columns:
            m = ind[ind == g].index
            out[m] = np.repeat(Gd[g].values[:, None], len(m), axis=1)
        return out

    grs_p = to_stock(G["base_grs"].rank(axis=1, pct=True))
    comp_p = to_stock(G["composite"].rank(axis=1, pct=True))
    variants = {"base (current)": base,
                "tilt_grs (RS + 0.5 x group strength)": base + 0.5 * grs_p.fillna(0.5),
                "tilt_comp (RS + 0.5 x sector score)": base + 0.5 * comp_p.fillna(0.5),
                "tilt_comp_1 (RS + 1.0 x sector score)": base + 1.0 * comp_p.fillna(0.5)}
    rs = S["rs_ibd"].where(U).rank(axis=1, pct=True)
    lead_ok = U & (comp_p > 0.8) & (S["trend"] == 1) & (S["prox_high"] >= 0.85) & (rs >= 0.7) & (S["np_yoy"] > 0)
    lead = rs.where(lead_ok)
    lead = lead.where(lead.T.groupby(ind).rank(ascending=False).T <= 2)     # max 2 per group
    variants["sector_leaders (separate list)"] = lead

    rows = []
    for name, sc in variants.items():
        res = lab.run(sc, cfg)
        big = lab.run(sc.where(lab.big), cfg)
        chk = lab.run(sc, cfg, period=("2023-01-01", None))
        row = {"variant": name, **res.stats, "big Sharpe": big.stats["Sharpe"],
               "pool median": float(sc.loc[tune.TUNE[0]:tune.TUNE[1]].notna().sum(axis=1).median()),
               "check 23-26 Sharpe": chk.stats["Sharpe"], "check 23-26 CAGR": chk.stats["CAGR %"]}
        for h, (a, b) in tune.HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"] = st["Sharpe"]
        rows.append(row)
        log(f"  {name:<40} CAGR {row['CAGR %']:>5}  Sharpe {row['Sharpe']:>5} (16-19 {row['Sharpe 16-19']:>5} | "
            f"20-22 {row['Sharpe 20-22']:>5} | big {row['big Sharpe']:>5})  maxDD {row['maxDD %']:>6}  "
            f"pool {row['pool median']:.0f}  | check 23-26 Sharpe {row['check 23-26 Sharpe']}")
    t = pd.DataFrame(rows).set_index("variant")
    b = t.loc["base (current)"]
    t["passes bar"] = [n != "base (current)"
                       and all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
                       and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"]
                       and r["pool median"] >= 3
                       for n, r in t.iterrows()]
    return t


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    log("loading data ...")
    lab = tune.Lab()
    if LEVEL3:
        fd = Path(__file__).resolve().parent.parent / "data" / "fundamentals"
        paths = {f.stem: (json.loads(f.read_text(encoding="utf-8")).get("industry") or []) for f in fd.glob("*.json")}
        lab.ind = {k: (v[2] if len(v) > 2 else None) for k, v in paths.items()}
        log(f"  level-3 industries: {len(set(x for x in lab.ind.values() if x))} groups")
    c = lab.P["close"]
    dates = lab.U.index[lab.U.index >= "2015-06-01"][::WEEKS]
    log(f"part A: {len(dates)} sample dates {dates[0].date()} -> {dates[-1].date()}")
    G, fwd, Ud, ind, sub = signals(lab, dates)
    log("  lead-lag signal ...")
    ll_sig, ll_tgt = lead_lag(lab, dates, Ud, ind, sub, fwd)
    ic = ic_table(G, fwd, extra=("lead_lag (target: non-leaders)", ll_sig, ll_tgt))
    ic.to_csv(OUT / "ic.csv", index=False)
    ev = rising_events(G, fwd)
    ev.to_csv(OUT / "rising_groups.csv", index=False)
    show = ["signal", "horizon"] + [f"{m} {p}" for p in PERIODS for m in ("IC", "t", "Q5-Q1")]
    log("\n=== A. group signals: IC with next 3m/6m excess group return (Q5-Q1 = top 20% groups minus bottom 20%, %)\n"
        + ic[show].to_string(index=False))
    log("\n=== A2. groups rising fast vs groups already strong (next 6 months, excess vs universe)\n" + ev.to_string(index=False))
    for key in ("base_grs", "composite"):
        sp, cv = persistence(G, fwd, key)
        sp.to_csv(OUT / f"spells_{key}.csv", index=False)
        cv.to_csv(OUT / f"decay_{key}.csv", index=False)
        log(f"\n=== A3. how long a group stays in the top 20% by {key} (months, sampled monthly)\n" + sp.to_string(index=False))
        log(f"\n=== A4. median excess return of the group after it enters / leaves the top 20% by {key}\n"
            + cv.to_string(index=False))

    if "--a-only" in sys.argv:
        return
    log("\npart B: CAN SLIM + sector score (2016-22 decision, 2023-26 shown as check) ...")
    t = part_b(lab, G, sub)
    t.to_csv(OUT / "portfolio.csv")
    cols = ["CAGR %", "Sharpe", "maxDD %", "Sharpe 16-19", "Sharpe 20-22", "big Sharpe", "pool median",
            "check 23-26 Sharpe", "check 23-26 CAGR", "passes bar"]
    log("\n=== B. 2016-2022\n" + t[cols].to_string())
    win = t[t["passes bar"]]
    log("\nDECISION: " + (", ".join(win.index) + " pass the bar" if len(win) else "nothing passes the bar"))


if __name__ == "__main__":
    main()
