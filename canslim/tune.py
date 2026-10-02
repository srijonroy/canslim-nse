"""Disciplined tuning of the book system.

Protocol (fixed before looking at any result):
  * TUNE on 2016-2022 only; judge every variant on both halves (2016-19, 2020-22)
    and on a large-cap-only version. 2023-now is the HOLD-OUT, run exactly once at the end.
  * Stage 1  filter ablation: drop a rule only if dropping it keeps Sharpe within 0.03
             of the base in BOTH halves AND in large caps, and maxDD is not >3 pts worse.
  * Stage 2  thresholds, one at a time: switch from the book value only if the new value
             beats it by >= 0.05 Sharpe on average across halves AND is not worse in either half.
  * Stage 3  exits (book sell rules): keep an exit only if it improves Sharpe by >= 0.03
             in both halves and does not reduce it in large caps.
  * Stage 4  entry timing (base/pivot), Stage 5 position count: same rule as stage 3.
  * Finally: hold-out comparison of plain book vs tuned, plus random picks from the tuned pool.
Every trial is counted and logged (data/tune/trials.csv).

usage: python -m canslim.tune
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import patterns
from canslim import portfolio as pf
from canslim.data import CACHE
from canslim.research import build
from canslim.system import benchmarks, market_state

OUT = Path(__file__).resolve().parent.parent / "data" / "tune"
TUNE = ("2016-01-01", "2022-12-31")
HALVES = {"16-19": ("2016-01-01", "2019-12-31"), "20-22": ("2020-01-01", "2022-12-31")}
HOLD = ("2023-01-01", None)
BOOK = {"trend": True, "prox": 0.85, "np_pos": True, "np_yoy": 25, "sales": 20, "cagr3": 15, "roe": 15, "rs": 80}
GRID = {"prox": [0.75, 0.80, 0.90], "np_yoy": [15, 20, 30, 40], "sales": [10, 15, 25, 30],
        "cagr3": [10, 20, 25], "roe": [10, 12, 20], "rs": [70, 75, 85, 90]}
TRIALS = []


def cached_build():
    f = CACHE / "build.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    B = build()
    f.write_bytes(pickle.dumps(B, protocol=pickle.HIGHEST_PROTOCOL))
    return B


def book_score(S, U, has_f, r: dict) -> pd.DataFrame:
    base = U & has_f
    rs = S["rs_ibd"].where(base).rank(axis=1, pct=True)
    ok = base.copy()
    if r.get("trend"):
        ok &= S["trend"] == 1
    if r.get("prox") is not None:
        ok &= S["prox_high"] >= r["prox"]
    if r.get("np_pos"):
        ok &= S["np_pos"] == 1
    if r.get("np_yoy") is not None:
        ok &= S["np_yoy"] >= r["np_yoy"]
    if r.get("sales") is not None:
        ok &= (S["sales_yoy"] >= r["sales"]) | (S["streak"] >= 2)
    if r.get("cagr3") is not None:
        ok &= S["ttm_cagr3"] >= r["cagr3"]
    if r.get("roe") is not None:
        ok &= S["roe"] >= r["roe"]
    if r.get("rs") is not None:
        ok &= rs >= r["rs"] / 100
    if r.get("npm_up"):                         # book rule 6, adopted 2026-10-02 (canslim/booktest.py)
        ok &= S["npm_chg"] > 0
    return rs.where(ok)


class Lab:
    def __init__(self):
        B = cached_build()
        self.S, self.U, self.has_f, self.P = B["S"], B["U"], B["has_f"], B["P"]
        self.ind = {k: f["industry"] for k, f in B["fund"].items()}
        self.ms = market_state(self.P).reindex(self.P["close"].index).ffill()
        self.big = self.S["turnover"] >= 25e7

    def run(self, score, cfg: pf.Config, period=TUNE, entry_ok=None):
        a, b = period
        return pf.simulate(score.loc[a:b], self.P["open"], self.P["close"], cfg, self.ms, self.ind,
                           start=a, end=b, entry_ok=entry_ok, V=self.P["volume"])

    def evaluate(self, name, rules, cfg=None, entry_ok=None, stage=""):
        cfg = cfg or pf.Config(market="no_new", stop=None)
        sc = book_score(self.S, self.U, self.has_f, rules)
        res = self.run(sc, cfg, entry_ok=entry_ok)
        big = self.run(sc.where(self.big), cfg, entry_ok=entry_ok)
        row = {"stage": stage, "variant": name, **res.stats,
               "pool_median": float(sc.loc[TUNE[0]:TUNE[1]].notna().sum(axis=1).median()),
               "big_Sharpe": big.stats["Sharpe"], "big_CAGR": big.stats["CAGR %"]}
        for h, (a, b) in HALVES.items():
            st = pf.stats(res.equity.loc[a:b])
            row[f"Sharpe {h}"], row[f"CAGR {h}"] = st["Sharpe"], st["CAGR %"]
        row["rules"], row["cfg"] = json.dumps(rules), json.dumps(cfg.__dict__)
        TRIALS.append(row)
        print(f"[trial {len(TRIALS):>3}] {stage:<8} {name:<34} Sharpe {row['Sharpe']:>5} "
              f"(16-19 {row['Sharpe 16-19']:>5} | 20-22 {row['Sharpe 20-22']:>5} | big {row['big_Sharpe']:>5}) "
              f"CAGR {row['CAGR %']:>5}  maxDD {row['maxDD %']:>6}  pool {row['pool_median']:.0f}", flush=True)
        pd.DataFrame(TRIALS).to_csv(OUT / "trials.csv", index=False)
        return row


def better(new, base, margin):
    return all(new[f"Sharpe {h}"] >= base[f"Sharpe {h}"] + margin for h in HALVES)


def pattern_mask(lab, score) -> pd.DataFrame:
    """Entry allowed only near a sound base's pivot (-5%..+5%), or at a fresh new high out of a base."""
    idx = pd.read_parquet(Path(__file__).resolve().parent.parent / "data" / "prices" / "NSE_NIFTY500-INDEX.parquet")["close"]
    ok = pd.DataFrame(False, index=score.index, columns=score.columns)
    P = lab.P
    cand = score.notna()
    n = 0
    for d in score.index:
        syms = cand.columns[cand.loc[d].values]
        for s in syms:
            df = pd.DataFrame({k: P[k][s].loc[:d] for k in ("open", "high", "low", "close", "volume")}).dropna()
            b = patterns.detect(df.iloc[-400:], idx)
            bad = any(f.startswith(("too deep", "V-shaped")) for f in b.faults)
            ok.at[d, s] = b.kind != "none" and -5 <= b.dist <= 5 and not bad
            n += 1
        if d.month == 1 and d.day <= 7:
            print(f"  pattern scan {d.date()} ({n} checks)", flush=True)
    return ok


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lab = Lab()
    base_cfg = pf.Config(market="no_new", stop=None)
    rules = dict(BOOK)
    base = lab.evaluate("book (baseline)", rules, stage="base")

    # ---- stage 1: ablation
    drop = []
    for k in BOOK:
        r = dict(rules)
        r[k] = None if not isinstance(BOOK[k], bool) else False
        row = lab.evaluate(f"drop {k}", r, stage="ablate")
        if (better(row, base, -0.03) and row["big_Sharpe"] >= base["big_Sharpe"] - 0.03
                and row["maxDD %"] >= base["maxDD %"] - 3):
            drop.append(k)
    if drop:
        r = dict(rules)
        for k in drop:
            r[k] = None if not isinstance(BOOK[k], bool) else False
        row = lab.evaluate("drop " + "+".join(drop), r, stage="ablate")
        if better(row, base, -0.03) and row["big_Sharpe"] >= base["big_Sharpe"] - 0.03:
            rules, base = r, row
        else:
            print("  combined drop failed the test; keeping all rules")
            drop = []
    print(f"STAGE 1 decision: drop {drop or 'nothing'}", flush=True)

    # ---- stage 2: thresholds, one at a time around the current rules
    for k, values in GRID.items():
        if rules.get(k) is None:
            continue
        best = None
        for v in values:
            r = dict(rules); r[k] = v
            row = lab.evaluate(f"{k}={v}", r, stage="thresh")
            avg_gain = np.mean([row[f"Sharpe {h}"] - base[f"Sharpe {h}"] for h in HALVES])
            if avg_gain >= 0.05 and better(row, base, 0) and (best is None or avg_gain > best[0]):
                best = (avg_gain, v, row)
        if best:
            rules = dict(rules); rules[k] = best[1]; base = best[2]
            print(f"  -> {k} changed to {best[1]}", flush=True)
    print(f"STAGE 2 rules: {rules}", flush=True)

    # ---- stage 3: exits
    exits = {"50dma break on volume": {"exit_ma50": True},
             "profit take 25% + 8-week rule": {"profit_take": 0.25, "hold8": True},
             "vol stop 2.0 sigma": {"vol_stop": 2.0}, "vol stop 3.0 sigma": {"vol_stop": 3.0},
             "sell losers in correction": {"market_exit": "losers"},
             "8% hard stop": {"stop": 0.08}}
    kept = {}
    for name, kw in exits.items():
        row = lab.evaluate(name, rules, pf.Config(**{**base_cfg.__dict__, **kw}), stage="exit")
        if better(row, base, 0.03) and row["big_Sharpe"] >= base["big_Sharpe"]:
            kept[name] = kw
    cfg = base_cfg
    if kept:
        merged = {k: v for kw in kept.values() for k, v in kw.items()}
        cfg_try = pf.Config(**{**base_cfg.__dict__, **merged})
        row = lab.evaluate("exits: " + " + ".join(kept), rules, cfg_try, stage="exit")
        if better(row, base, 0.03):
            cfg, base = cfg_try, row
        else:
            best_name = max(kept, key=lambda n: next(t["Sharpe"] for t in TRIALS if t["variant"] == n))
            cfg = pf.Config(**{**base_cfg.__dict__, **kept[best_name]})
            base = next(t for t in TRIALS if t["variant"] == best_name)
            kept = {best_name: kept[best_name]}
    print(f"STAGE 3 exits kept: {list(kept) or 'none'}", flush=True)

    # ---- stage 4: entry timing on bases / pivots
    sc = book_score(lab.S, lab.U, lab.has_f, rules)
    em = pattern_mask(lab, sc.loc[TUNE[0]:])
    em.to_parquet(OUT / "pattern_mask.parquet")
    row = lab.evaluate("entry: near a sound base's pivot", rules, cfg, entry_ok=em.loc[:TUNE[1]], stage="entry")
    use_pattern = better(row, base, 0.03) and row["big_Sharpe"] >= base["big_Sharpe"]
    if use_pattern:
        base = row
    ext = (lab.S["ext50"] <= 0.25).reindex(columns=sc.columns).fillna(False)
    row = lab.evaluate("entry: not >25% above 50-day", rules, cfg, entry_ok=ext.loc[:TUNE[1]], stage="entry")
    use_ext = (not use_pattern) and better(row, base, 0.03) and row["big_Sharpe"] >= base["big_Sharpe"]
    if use_ext:
        base = row
    entry = em if use_pattern else (ext if use_ext else None)
    print(f"STAGE 4 entry filter: {'pattern' if use_pattern else 'extension' if use_ext else 'none'}", flush=True)

    # ---- stage 5: number of positions
    for n in (15, 20):
        c2 = pf.Config(**{**cfg.__dict__, "n": n, "keep_rank": n * 3})
        row = lab.evaluate(f"n={n}", rules, c2, entry_ok=None if entry is None else entry.loc[:TUNE[1]], stage="size")
        if better(row, base, 0.03):
            cfg, base = c2, row
    print(f"STAGE 5 positions: {cfg.n}", flush=True)

    final = {"rules": rules, "cfg": cfg.__dict__, "entry": "pattern" if use_pattern else "ext" if use_ext else "none",
             "trials": len(TRIALS)}
    (OUT / "final.json").write_text(json.dumps(final, indent=1))
    print("\nFINAL (chosen on 2016-2022 only):", json.dumps(final), flush=True)

    # ---- hold-out: run ONCE
    print("\n=== HOLD-OUT 2023 -> now (never used for any decision above)", flush=True)
    hold_rows, curves = [], {}
    book_sc = book_score(lab.S, lab.U, lab.has_f, BOOK)
    tuned_sc = book_score(lab.S, lab.U, lab.has_f, rules)
    if use_pattern:
        em2 = pattern_mask(lab, tuned_sc.loc[HOLD[0]:])
        entry_h = em2
    elif use_ext:
        entry_h = ext
    else:
        entry_h = None
    for name, sc_, c_, e_ in [("plain book (n=10)", book_sc, base_cfg, None),
                              ("plain book (n=20)", book_sc, pf.Config(**{**base_cfg.__dict__, "n": 20, "keep_rank": 60}), None),
                              ("TUNED", tuned_sc, cfg, entry_h)]:
        res = lab.run(sc_, c_, period=HOLD, entry_ok=e_)
        curves[name] = res.equity
        hold_rows.append({"system": name, **res.stats})
    rng = np.random.default_rng(11)
    rnd = [lab.run(pd.DataFrame(rng.random(tuned_sc.shape), index=tuned_sc.index, columns=tuned_sc.columns)
                   .where(tuned_sc.notna()), cfg, period=HOLD, entry_ok=entry_h).stats for _ in range(10)]
    rnd = pd.DataFrame(rnd)
    hold_rows.append({"system": "random picks from tuned pool (median of 10)", **rnd.median().round(2).to_dict()})
    for k, v in benchmarks(lab.P, lab.U, HOLD[0], lab.P["close"].index[-1]).items():
        curves[k] = v
        hold_rows.append({"system": k, **pf.stats(v)})
    ht = pd.DataFrame(hold_rows).set_index("system")
    ht.to_csv(OUT / "holdout.csv")
    pd.DataFrame(curves).to_parquet(OUT / "holdout_curves.parquet")
    pd.set_option("display.width", 250)
    print(ht.to_string())
    print(f"\nrandom-pool CAGR range: {rnd['CAGR %'].min()} .. {rnd['CAGR %'].max()} | total trials run: {len(TRIALS)}")


if __name__ == "__main__":
    main()
