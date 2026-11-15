"""Offline tests for the experiment harness and the simulator's execution limits (no market data needed).

usage: python -m unittest tests.test_harness -v
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import exp
from canslim import portfolio as pf

DAYS = pd.bdate_range("2016-01-01", "2016-03-31")


def market(prices: dict) -> tuple:
    """Open = close = the given path (one value per day) for each symbol."""
    C = pd.DataFrame(prices, index=DAYS[: len(next(iter(prices.values())))], dtype=float)
    return C.copy(), C


class SimulatorLimits(unittest.TestCase):
    def setUp(self):
        n = 30
        self.O, self.C = market({"A": np.linspace(100, 130, n), "B": np.full(n, 50.0)})
        self.days = self.C.index
        self.score = pd.DataFrame({"A": 1.0, "B": np.nan}, index=self.days[:1])     # buy A on day 0's close
        self.cfg = pf.Config(n=1, stop=None, cost=0.0, cash_yield=0.0, max_per_group=0)

    def sim(self, **kw):
        return pf.simulate(self.score, self.O, self.C, self.cfg, start=self.days[0], end=self.days[-1], **kw)

    def test_no_limits_buys_next_open(self):
        r = self.sim()
        self.assertAlmostEqual(r.exposure.iloc[1], 1.0)              # bought at day 1's open
        self.assertAlmostEqual(r.equity.iloc[-1], 130 / self.O["A"].iloc[1], places=6)

    def test_blocked_buy_is_dropped(self):
        nb = pd.DataFrame(False, index=self.days, columns=["A", "B"])
        nb.loc[self.days[1], "A"] = True                              # locked at the upper circuit on day 1
        r = self.sim(no_buy=nb)
        self.assertEqual(r.exposure.max(), 0.0)                       # no buy; no later rebalance to retry
        self.assertAlmostEqual(r.equity.iloc[-1], 1.0)

    def test_blocked_sell_is_retried(self):
        # rebalance on day 0 (buy A) and day 10 (A no longer ranked -> sell at day 11's open)
        sc = pd.DataFrame({"A": [1.0, np.nan], "B": [np.nan, np.nan]}, index=[self.days[0], self.days[10]])
        ns = pd.DataFrame(False, index=self.days, columns=["A", "B"])
        ns.loc[self.days[11:14], "A"] = True                          # locked at the lower circuit for 3 days
        r = pf.simulate(sc, self.O, self.C, self.cfg, start=self.days[0], end=self.days[-1], no_sell=ns)
        self.assertEqual(len(r.trades), 1)
        self.assertEqual(r.trades.exit_date.iloc[0], self.days[14])   # first open after the lock
        free = pf.simulate(sc, self.O, self.C, self.cfg, start=self.days[0], end=self.days[-1])
        self.assertEqual(free.trades.exit_date.iloc[0], self.days[11])

    def test_all_false_masks_change_nothing(self):
        z = pd.DataFrame(False, index=self.days, columns=["A", "B"])
        self.assertTrue(self.sim().equity.equals(self.sim(no_buy=z, no_sell=z).equity))


class FakeCtx:
    """Stands in for exp.Ctx: experiments that only use curve= variants need no market data."""


def curve(growth):
    def f(ctx, start, end, big):
        days = pd.bdate_range(start, end or "2024-12-31")
        r = np.full(len(days), growth / 252) + np.sin(np.arange(len(days))) * 0.004
        return pd.Series(np.cumprod(1 + r), index=days)
    return f


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self._saved = exp.TUNE_OUT, exp.INSIGHTS, exp.LOG
        exp.TUNE_OUT, exp.INSIGHTS, exp.LOG = t / "tune", t / "insights", t / "tune" / "experiments.csv"

    def tearDown(self):
        exp.TUNE_OUT, exp.INSIGHTS, exp.LOG = self._saved
        self.tmp.cleanup()

    def ex(self):
        return exp.Experiment(slug="demo", title="Demo", question="Q?", tags="test",
                              variants=[exp.Variant("base", curve=curve(0.10)),
                                        exp.Variant("better", curve=curve(0.30)),
                                        exp.Variant("worse", curve=curve(0.02))])

    def test_bar_picks_only_the_better_variant(self):
        out = exp.compare(FakeCtx(), self.ex())
        self.assertEqual(out.decision, "better pass the bar")
        self.assertEqual(out.tested, 2)
        passed = out.table[out.table["passes bar"]]
        self.assertEqual(list(passed.variant), ["better"])
        self.assertTrue((passed.period == "2016-22").all())          # the 2023+ rows are never used to decide

    def test_record_writes_csv_insight_and_log(self):
        e = self.ex()
        out = exp.compare(FakeCtx(), e)
        f = exp.record(e, out)
        self.assertTrue((exp.TUNE_OUT / "demo" / "results.csv").exists())
        text = f.read_text(encoding="utf-8")
        for k in ("title: Demo", "status:", "takeaway:", "source:", "**Decision bar"):
            self.assertIn(k, text)
        exp.record(e, out)                                            # rerun replaces its log row, no duplicate
        self.assertEqual(len(pd.read_csv(exp.LOG)), 1)

    def test_check_without_bar_uses_takeaway_as_decision(self):
        e = exp.Experiment(slug="chk", title="Check", question="Q?", tags="t", bar=None,
                           variants=[exp.Variant("a", curve=curve(0.1)), exp.Variant("b", curve=curve(0.1))],
                           explain=lambda t, p: ("Some numbers. The answer is yes.", ""))
        self.assertEqual(exp.compare(FakeCtx(), e).decision, "The answer is yes")

    def test_discover_finds_the_real_experiments(self):
        found = exp.discover()
        for slug in ("benchmark-funds", "circuit-locks", "error-ranges", "survivorship"):
            self.assertIn(slug, found)


if __name__ == "__main__":
    unittest.main()
