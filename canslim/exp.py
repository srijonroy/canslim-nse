"""Experiment harness: one way to define, run and record every test.

Why: each old test script (weighttest, idletest, ...) repeated the same loading, variant loop, decision bar and
CSV writing. Here that is shared, so a new test is one small file in canslim/experiments/ and every test is
recorded the same way:
  data/tune/<slug>/results.csv            the table
  data/research/insights/<date>_<slug>.md  the Insights page entry (plain English; edit the wording if needed)
  data/tune/experiments.csv               one row per run: date, slug, variants tested, decision
                                           (a running count of how many ideas were tried on the same years)

Adding a test, the common kind (compare variants of the live system against it):

    # canslim/experiments/my_idea.py
    from canslim.exp import Experiment, Variant
    EXPERIMENT = Experiment(
        slug="my-idea", title="...", question="...", tags="...",
        variants=[Variant("current"), Variant("15 slots", cfg={"n": 15})])

  Variant fields: cfg = overrides of the live config (data/tune/final.json); score(ctx) = a different ranking /
  pool; sim(ctx) = extra simulator inputs (entry_ok, hold_ok, no_buy, no_sell); curve(ctx, start, end, big) = an
  equity curve built some other way (an index fund, an overlay). The first variant is the base.
  The decision bar (STANDARD, fixed before running) is applied on 2016-22 only; 2023+ is shown, never used.

  Checks that are not variant comparisons (data audits, error ranges) pass run=function(ctx) -> Outcome.

usage:  python -m canslim.exp list
        python -m canslim.exp run <slug> [<slug> ...]
"""
import datetime as dt
import importlib
import json
import pkgutil
import sys
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Callable

import pandas as pd

from canslim import portfolio as pf
from canslim import tune

ROOT = Path(__file__).resolve().parent.parent
TUNE_OUT = ROOT / "data" / "tune"
INSIGHTS = ROOT / "data" / "research" / "insights"
LOG = TUNE_OUT / "experiments.csv"
PERIODS = {"2016-22": tune.TUNE, "2023+": tune.HOLD}


class Ctx:
    """Shared, lazily loaded inputs. Everything an experiment needs comes from here."""

    @cached_property
    def lab(self) -> tune.Lab:
        print("loading data ...", flush=True)
        return tune.Lab()

    @cached_property
    def final(self) -> dict:
        return json.loads((TUNE_OUT / "final.json").read_text())

    @property
    def rules(self) -> dict:
        return dict(self.final["rules"])

    def cfg(self, **over) -> pf.Config:
        return pf.Config(**{**self.final["cfg"], **over})

    @cached_property
    def score(self) -> pd.DataFrame:
        """The live system's ranked pool (NaN = does not pass the rules)."""
        return tune.book_score(self.lab.S, self.lab.U, self.lab.has_f, self.rules)

    def index(self, name: str) -> pd.Series:
        """NSE index close (price index, no dividends) from data/indices/<name>.parquet."""
        d = pd.read_parquet(ROOT / "data" / "indices" / f"{name}.parquet")
        s = d["close"].astype(float)
        s.index = pd.to_datetime(s.index)
        return s[~s.index.duplicated()].sort_index().dropna()

    def run(self, score=None, cfg=None, period=tune.TUNE, big=False, **sim) -> pf.Result:
        sc = self.score if score is None else score
        if big:
            sc = sc.where(self.lab.big)
        return self.lab.run(sc, cfg or self.cfg(), period=period, **sim)


@dataclass
class Variant:
    name: str
    cfg: dict = field(default_factory=dict)
    score: Callable | None = None          # ctx -> DataFrame
    sim: Callable | None = None            # ctx -> dict of extra simulate() inputs
    curve: Callable | None = None          # (ctx, start, end, big) -> equity Series

    def equity(self, ctx: Ctx, period, big=False):
        """(equity, Result or None)"""
        if self.curve is not None:
            a, b = period
            e = self.curve(ctx, a, b, big)
            return e / e.iloc[0], None
        res = ctx.run(self.score(ctx) if self.score else None, ctx.cfg(**self.cfg), period, big,
                      **(self.sim(ctx) if self.sim else {}))
        return res.equity, res


@dataclass(frozen=True)
class Bar:
    text: str
    test: Callable                         # (row, base_row) -> bool


STANDARD = Bar("Sharpe at least 0.03 higher than the current system in BOTH halves of 2016-22 (2016-19, 2020-22), "
               "worst drop no more than 3 points deeper, and the large-cap-only Sharpe not lower",
               lambda r, b: all(r[f"Sharpe {h}"] >= b[f"Sharpe {h}"] + 0.03 for h in tune.HALVES)
               and r["maxDD %"] >= b["maxDD %"] - 3 and r["big Sharpe"] >= b["big Sharpe"])


@dataclass
class Outcome:
    table: pd.DataFrame
    decision: str                          # one line, plain English
    takeaway: str                          # 2-4 sentences for the Insights page
    body: str = ""                         # extra markdown (method, caveats)
    status: str = "Tested, not adopted"
    tested: int = 0                        # variants tried on the decision years (for the running count)


@dataclass
class Experiment:
    slug: str
    title: str
    question: str
    tags: str
    variants: list = field(default_factory=list)
    bar: Bar | None = STANDARD
    run: Callable | None = None            # ctx -> Outcome (custom checks)
    explain: Callable | None = None        # (table, passed names) -> (takeaway, body) for variant comparisons
    method: str = ""


def measure(ctx: Ctx, v: Variant) -> list[dict]:
    rows = []
    for pname, period in PERIODS.items():
        e, res = v.equity(ctx, period)
        eb, _ = v.equity(ctx, period, big=True)
        st = res.stats if res is not None else pf.stats(e)
        row = {"period": pname, "variant": v.name, "CAGR %": st["CAGR %"], "Sharpe": st["Sharpe"],
               "maxDD %": st["maxDD %"], "invested %": st.get("invested %"), "trades/yr": st.get("trades/yr"),
               "big Sharpe": pf.stats(eb)["Sharpe"]}
        if period == tune.TUNE:
            for h, (a, b) in tune.HALVES.items():
                s2 = pf.stats(e.loc[a:b])
                row[f"Sharpe {h}"], row[f"CAGR {h}"] = s2["Sharpe"], s2["CAGR %"]
        rows.append(row)
    return rows


def compare(ctx: Ctx, ex: Experiment) -> Outcome:
    rows = []
    for v in ex.variants:
        for r in measure(ctx, v):
            rows.append(r)
            extra = (f"(16-19 {r['Sharpe 16-19']:>5} | 20-22 {r['Sharpe 20-22']:>5} | big {r['big Sharpe']:>5})"
                     if r["period"] == "2016-22" else f"(big {r['big Sharpe']:>5})")
            print(f"  {r['period']:<8} {v.name:<34} CAGR {r['CAGR %']:>5}  Sharpe {r['Sharpe']:>5}  "
                  f"maxDD {r['maxDD %']:>6}  {extra}", flush=True)
    t = pd.DataFrame(rows)
    T = t[t.period == "2016-22"].set_index("variant")
    base = T.iloc[0]
    passed = [n for i, (n, r) in enumerate(T.iterrows()) if i > 0 and ex.bar and ex.bar.test(r, base)]
    t["passes bar"] = [r.period == "2016-22" and r.variant in passed for r in t.itertuples()]
    decision = (", ".join(passed) + " pass the bar" if passed else "no variant passes the bar") if ex.bar else ""
    takeaway, body = ex.explain(t, passed) if ex.explain else (decision, "")
    if not ex.bar:                          # a check, not an idea: its takeaway is the decision
        decision = takeaway.split(". ")[-1].rstrip(".")
    body = (body + "\n\n" if body else "") + md_table(t)
    return Outcome(t, decision, takeaway, body, "Passed the bar - needs a decision" if passed else
                   "Tested, not adopted", tested=len(ex.variants) - 1)


def md_table(t: pd.DataFrame) -> str:
    t = t.copy()
    t = t.astype(object).where(t.notna(), "")
    head = "| " + " | ".join(map(str, t.columns)) + " |\n|" + "---|" * len(t.columns) + "\n"
    return head + "\n".join("| " + " | ".join(map(str, r)) + " |" for r in t.values)


def record(ex: Experiment, out: Outcome) -> Path:
    d = TUNE_OUT / ex.slug
    d.mkdir(parents=True, exist_ok=True)
    out.table.to_csv(d / "results.csv", index=False)
    today = dt.date.today().isoformat()
    INSIGHTS.mkdir(parents=True, exist_ok=True)
    f = INSIGHTS / f"{today}_{ex.slug}.md"
    bar = f"**Decision bar (fixed before running).** {ex.bar.text}.\n\n" if ex.bar else ""
    src = f"canslim/experiments/{ex.slug.replace('-', '_')}.py, data/tune/{ex.slug}/results.csv"
    f.write_text("---\n"
                 f"title: {ex.title}\ndate: {today}\nstatus: {out.status}\ntags: {ex.tags}\n"
                 f"takeaway: {' '.join(out.takeaway.split())}\nsource: {src}\n---\n"
                 f"**Question.** {ex.question}\n\n"
                 + (f"**Method.** {ex.method}\n\n" if ex.method else "") + bar
                 + (out.body.strip() + "\n\n" if out.body else "")
                 + f"**Decision.** {out.decision}\n", encoding="utf-8")
    log = pd.DataFrame([{"date": today, "slug": ex.slug, "variants tested": out.tested, "decision": out.decision}])
    old = pd.read_csv(LOG) if LOG.exists() else pd.DataFrame()
    pd.concat([old[old.slug != ex.slug] if len(old) else old, log]).to_csv(LOG, index=False)
    return f


def discover() -> dict:
    import canslim.experiments as pkg
    out = {}
    for m in pkgutil.iter_modules(pkg.__path__):
        try:
            mod = importlib.import_module(f"canslim.experiments.{m.name}")
        except Exception as e:                  # one broken file must not stop the others
            print(f"  ! skipped experiments/{m.name}.py: {type(e).__name__}: {e}", flush=True)
            continue
        ex = getattr(mod, "EXPERIMENT", None)
        if ex is not None:
            out[ex.slug] = ex
    return out


def run(slug: str, ctx: Ctx | None = None) -> Outcome:
    ex = discover()[slug]
    ctx = ctx or Ctx()
    print(f"=== {ex.title}", flush=True)
    out = ex.run(ctx) if ex.run else compare(ctx, ex)
    f = record(ex, out)
    print(f"\nDECISION: {out.decision}\n  -> {f.relative_to(ROOT)}", flush=True)
    return out


def main(argv):
    if not argv or argv[0] == "list":
        for slug, ex in sorted(discover().items()):
            print(f"{slug:<24} {ex.title}")
        if LOG.exists():
            print(f"\nvariants tested through this harness: {int(pd.read_csv(LOG)['variants tested'].sum())} "
                  f"(plus {json.loads((TUNE_OUT / 'final.json').read_text())['trials']} in tune.py and many more in the older "
                  f"*test.py scripts, not counted here)")
        return
    if argv[0] == "run":
        ctx = Ctx()
        for slug in argv[1:]:
            run(slug, ctx)


if __name__ == "__main__":
    main(sys.argv[1:])
