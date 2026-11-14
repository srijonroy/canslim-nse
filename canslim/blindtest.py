"""Blind test: can a strong AI model pick good buy points from a chart alone?

One year (default 2024). For each sampled stock and date the model sees an anonymised daily chart of the year
BEFORE that date (no name, no dates, prices rescaled to 100) and answers BUY / WAIT / AVOID with a confidence.
What happened AFTER the date is kept in a separate key file the model never sees, and is used to score it.

Two samples:
  random    17 random stocks from the liquid universe on the first scan date of each month (~200 charts)
  canslim   every buy the current system made in that year (chart ends on the signal day)

Outcome per chart, from the next day's open: return over the next 63 trading days minus the Nifty 500's, and
whether +20% came before -8% within 126 days.

Bar (fixed before running): the model "reads charts usefully" only if
  1. in the random sample, BUY beats AVOID by >= 3 points of average 63-day excess return, in BOTH half-years, and
  2. in the canslim sample, BUY does no worse than the system's other buys.
A simple rule (uptrend, within 15% of the high, relative strength in the top 20%) is scored on the same random
charts for comparison.

Each year has its own folder: data/tune/blindtest/<year>/ (key.csv, answers_<model>.jsonl, scored_<model>.csv).

usage: python -m canslim.blindtest make [year]             # charts + key (default 2024)
       python -m canslim.blindtest ask [year] [model]      # headless Claude Code reads the charts (default: fable)
       python -m canslim.blindtest score [year] [model]
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "tune" / "blindtest"
OUT = BASE / "2024"                        # set per year in __main__
BARS, FWD, PATH_DAYS, PER_MONTH, BATCH, SEED = 250, 63, 126, 17, 8, 20241114
PROMPT = (
    "The PNG files {files} in the current folder are anonymised daily price charts, one stock each. Each shows about "
    "one year: candles, the 50-day (blue) and 200-day (red) averages, volume with its 50-day average, and a relative "
    "strength line against the market index. Prices are rescaled to start at 100 and there are no dates; the last "
    "bar on the right is today. Open every file with the Read tool and study it in whatever way you find best. "
    "For each chart decide whether today is a good position to BUY the stock for a holding of one to six months: "
    "BUY (buy now), WAIT (interesting but not yet), or AVOID. Use only what is in the chart. Do not ask questions. "
    "Answer with one JSON object per line and nothing else, exactly like: "
    '{{"id": "c0001", "call": "BUY", "conf": 4, "why": "short reason"}} '
    "where conf is 1 (low) to 5 (high).")


def make(year: int):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from canslim import portfolio as pf
    from canslim import tune
    lab = tune.Lab()
    final = json.loads((BASE.parent / "final.json").read_text())
    sc = tune.book_score(lab.S, lab.U, lab.has_f, final["rules"])
    O, H, L, C, V = (lab.P[k] for k in ("open", "high", "low", "close", "volume"))
    days = C.index
    n500 = pd.read_parquet(ROOT / "data" / "prices" / "NSE_NIFTY500-INDEX.parquet")["close"]
    n500.index = pd.to_datetime(n500.index)
    n500 = n500.reindex(days).ffill()
    rng = np.random.default_rng(SEED + year)
    items = []
    U = lab.U.loc[str(year)]
    rsr = lab.S["rs_ibd"].where(lab.U).rank(axis=1, pct=True)
    for m, g in U.groupby(U.index.month):
        d = g.index[0]
        pool = [s for s in g.columns[g.iloc[0].values] if C[s].loc[:d].notna().sum() >= BARS + 20]
        for s in rng.choice(pool, size=min(PER_MONTH, len(pool)), replace=False):
            rule = bool(lab.S["trend"].at[d, s] == 1 and lab.S["prox_high"].at[d, s] >= 0.85 and rsr.at[d, s] >= 0.8)
            items.append({"set": "random", "sym": s, "date": d, "rule": rule})
    res = lab.run(sc, pf.Config(**final["cfg"]), period=(f"{year}-01-01", f"{year}-12-31"))
    for t in res.trades.itertuples():
        d = days[days.get_loc(pd.Timestamp(t.entry_date)) - 1]
        items.append({"set": "canslim", "sym": t.sym, "date": d, "rule": True, "trade_ret": t.ret})
    order = rng.permutation(len(items))
    charts = OUT / "charts"
    shutil.rmtree(charts, ignore_errors=True)
    charts.mkdir(parents=True)
    key = []
    for n, i in enumerate(order, 1):
        it, cid = items[i], f"c{n:04d}"
        s, d = it["sym"], it["date"]
        k = days.get_loc(d)
        sl = slice(max(0, k - BARS + 1), k + 1)
        o, h, l, c, v = (x[s].iloc[sl].values for x in (O, H, L, C, V))
        ok = ~np.isnan(c)
        o, h, l, c, v = o[ok], h[ok], l[ok], c[ok], v[ok]
        f = 100 / c[0]
        full = C[s].iloc[:k + 1]
        ma50 = full.rolling(50).mean().iloc[sl].values[ok] * f
        ma200 = full.rolling(200).mean().iloc[sl].values[ok] * f
        vavg = V[s].iloc[:k + 1].rolling(50).mean().iloc[sl].values[ok]
        rs = (C[s] / n500).iloc[sl].values[ok]
        x = np.arange(len(c))
        fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [5, 1.4, 1.4]})
        up = c >= o
        a1.vlines(x, l * f, h * f, color=np.where(up, "#1a9850", "#d73027"), linewidth=0.8)
        a1.bar(x, (c - o) * f, bottom=o * f, width=0.7, color=np.where(up, "#1a9850", "#d73027"))
        a1.plot(x, ma50, color="#2b6cb0", linewidth=1.1, label="50-day")
        a1.plot(x, ma200, color="#c53030", linewidth=1.1, label="200-day")
        a1.set_yscale("log")
        a1.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.0f"))
        a1.yaxis.set_minor_formatter(matplotlib.ticker.FormatStrFormatter("%.0f"))
        a1.grid(alpha=0.25, which="both")
        a1.legend(loc="upper left", fontsize=8)
        a1.set_title(f"{cid}   (price rescaled: first bar = 100; last bar = today)", fontsize=10)
        a2.bar(x, v, width=0.7, color=np.where(up, "#1a9850", "#d73027"))
        a2.plot(x, vavg, color="black", linewidth=0.9)
        a2.set_ylabel("volume", fontsize=8)
        a2.set_yticks([])
        a3.plot(x, rs / rs[0] * 100, color="#6b46c1", linewidth=1.1)
        a3.set_ylabel("rel. strength", fontsize=8)
        a3.grid(alpha=0.25)
        a3.set_xlabel("trading days (no dates)")
        fig.tight_layout()
        fig.savefig(charts / f"{cid}.png", dpi=85)
        plt.close(fig)
        # what happened next (never shown): entry at the next open
        row = {"id": cid, **{a: b for a, b in it.items()}, "date": f"{d:%Y-%m-%d}"}
        if k + 1 < len(days) and not np.isnan(O[s].iloc[k + 1]):
            e = O[s].iloc[k + 1]
            j = min(k + FWD, len(days) - 1)
            row["fwd"] = C[s].iloc[:j + 1].ffill().iloc[-1] / e - 1
            row["excess"] = row["fwd"] - (n500.iloc[j] / n500.iloc[k] - 1)
            path = C[s].iloc[k + 1:k + 1 + PATH_DAYS].ffill() / e - 1
            hit_up, hit_dn = path[path >= 0.20].index.min(), path[path <= -0.08].index.min()
            row["won"] = bool(pd.notna(hit_up) and (pd.isna(hit_dn) or hit_up < hit_dn))
        key.append(row)
    pd.DataFrame(key).to_csv(OUT / "key.csv", index=False)
    print(f"{len(key)} charts in {charts}; key in {OUT / 'key.csv'} "
          f"(random {sum(r['set'] == 'random' for r in key)}, canslim {sum(r['set'] == 'canslim' for r in key)})")


def ask(model: str):
    from canslim.autobrief import claude_exe
    exe = claude_exe()
    ids = sorted(p.stem for p in (OUT / "charts").glob("c*.png"))
    out_f = OUT / f"answers_{model}.jsonl"
    done = {json.loads(x)["id"] for x in out_f.read_text().splitlines()} if out_f.exists() else set()
    todo = [i for i in ids if i not in done]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"{len(done)} answered, {len(todo)} to go in {len(batches)} batches", flush=True)

    stop = []                                # set once the plan's usage limit is hit: skip the rest

    def one(b):
        if stop:
            return b, [], "skipped (usage limit)"
        # a bare temp folder holding only these charts: the model cannot see the key, the project or the names
        with tempfile.TemporaryDirectory(prefix="charts_") as td:
            for i in b:
                shutil.copy(OUT / "charts" / f"{i}.png", Path(td) / f"{i}.png")
            cmd = [exe, "-p", PROMPT.format(files=", ".join(f"{i}.png" for i in b)), "--model", model,
                   "--allowedTools", "Read", "--output-format", "text"]
            try:
                p = subprocess.run(cmd, cwd=td, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=1200)
                txt = p.stdout or ""
                if "limit" in txt[:200] and "resets" in txt[:200]:
                    stop.append(txt.strip()[:120])
            except subprocess.TimeoutExpired:
                txt = ""
        got = []
        for m in re.finditer(r"\{[^{}]*\}", txt):
            try:
                j = json.loads(m.group(0))
                if j.get("id") in b and str(j.get("call", "")).upper() in ("BUY", "WAIT", "AVOID"):
                    got.append({"id": j["id"], "call": j["call"].upper(), "conf": int(j.get("conf", 0)),
                                "why": str(j.get("why", ""))[:200]})
            except (ValueError, TypeError):
                pass
        return b, got, txt[-200:]

    n = len(done)
    with ThreadPoolExecutor(2) as ex, open(out_f, "a", encoding="utf-8") as f:
        for b, got, tail in ex.map(one, batches):
            for g in got:
                f.write(json.dumps(g) + "\n")
            f.flush()
            n += len(got)
            if tail.startswith("skipped"):
                continue
            print(f"  {n}/{len(ids)} answered" + ("" if len(got) == len(b) else f"  (batch got {len(got)}/{len(b)}: {tail!r})"),
                  flush=True)
    if stop:
        print("STOPPED: " + stop[0] + " -- run the same command again after the reset; answered charts are kept")


def score(model: str):
    key = pd.read_csv(OUT / "key.csv")
    ans = pd.DataFrame([json.loads(x) for x in (OUT / f"answers_{model}.jsonl").read_text().splitlines()])
    t = key.merge(ans.drop_duplicates("id"), on="id").dropna(subset=["excess"])
    t["half"] = np.where(pd.to_datetime(t.date).dt.month <= 6, "H1", "H2")
    pd.set_option("display.width", 200)

    def tab(g, by):
        return g.groupby(by).agg(charts=("id", "count"), avg_excess=("excess", lambda x: round(x.mean() * 100, 1)),
                                 median_excess=("excess", lambda x: round(x.median() * 100, 1)),
                                 avg_return=("fwd", lambda x: round(x.mean() * 100, 1)),
                                 beat_index=("excess", lambda x: round((x > 0).mean() * 100)),
                                 plus20_before_minus8=("won", lambda x: round(x.astype(bool).mean() * 100)))
    r = t[t.set == "random"]
    print(f"model {model}: {len(t)} charts scored ({len(r)} random, {len(t) - len(r)} canslim)\n")
    print("RANDOM sample, by the model's call:\n", tab(r, "call").to_string(), "\n")
    print("RANDOM sample, by half-year and call:\n", tab(r, ["half", "call"]).to_string(), "\n")
    print("RANDOM sample, BUY calls by confidence:\n", tab(r[r.call == "BUY"], "conf").to_string(), "\n")
    print("RANDOM sample, simple rule (uptrend + near high + top-20% RS):\n", tab(r, "rule").to_string(), "\n")
    c = t[t.set == "canslim"]
    print("CANSLIM buys, by the model's call:\n", tab(c, "call").to_string())
    if "trade_ret" in c:
        print("\nCANSLIM buys, the system's actual trade result by call (avg %):\n",
              (c.groupby("call").trade_ret.agg(["count", "mean", "median"]) * [1, 100, 100]).round(1).to_string())
    t.to_csv(OUT / f"scored_{model}.csv", index=False)


if __name__ == "__main__":
    a = sys.argv[1:]
    year = int(a[1]) if len(a) > 1 else 2024
    model = a[2] if len(a) > 2 else "fable"
    OUT = BASE / str(year)
    OUT.mkdir(parents=True, exist_ok=True)
    if a[:1] == ["make"]:
        make(year)
    elif a[:1] == ["ask"]:
        ask(model)
    elif a[:1] == ["score"]:
        score(model)
    else:
        sys.exit(__doc__)
