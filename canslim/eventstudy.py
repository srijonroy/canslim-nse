"""Shared event-study engine: what does a stock do before and after an event, vs same-size peers?

An event = (sym, date): the day the news became public. The "buy" is the close `lag` trading days after
it (default 1, because many filings come after market hours). Returns are compared with the median return
of all stocks in the same market-cap bucket (sizetest buckets) over the same window.

  before:  close day -64 -> day -1         after: buy close -> +21 / +63 / +126 / +252 trading days

usage (from a test script):
    es = EventStudy()
    E = es.run(events_df)            # events_df: sym, date, plus any grouping columns
    print(es.table(E, "group col"))
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import tune
from canslim.sizetest import BUCKETS, bucket, share_counts

H = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
PRE = 63
PERIODS = {"2016-22": ("2016-01-01", "2022-12-31"), "2023-26": ("2023-01-01", "2026-12-31")}


class EventStudy:
    def __init__(self):
        B = tune.cached_build()
        self.C = B["P"]["close"]
        self.U = B["U"].reindex(self.C.index, method="ffill").reindex(columns=self.C.columns).fillna(False)
        sh = share_counts(self.C.columns)
        self.mcap = (self.C[sh.index] * sh).reindex(columns=self.C.columns)
        rank = self.mcap.rank(axis=1, ascending=False).reindex(columns=self.C.columns)
        self.bnum = pd.DataFrame(np.select([rank <= a[1] for a in BUCKETS], range(len(BUCKETS)), -1),
                                 index=self.C.index, columns=self.C.columns)
        self.bnum[rank.isna()] = -1
        self.Cv, self.bv = self.C.values, self.bnum.values
        self.idx, self.cidx = self.C.index, {s: i for i, s in enumerate(self.C.columns)}
        self._med = {}

    def _bucket_median(self, k_from, k_to):
        """median return per bucket from row k_from to k_to (vectorised over all event rows at once)."""
        key = (k_from, k_to)
        if key not in self._med:
            r = self.Cv[k_to] / self.Cv[k_from] - 1
            b = self.bv[k_from]
            self._med[key] = [np.nanmedian(r[b == i]) if (b == i).any() else np.nan for i in range(len(BUCKETS))]
        return self._med[key]

    def run(self, ev: pd.DataFrame, lag: int = 1) -> pd.DataFrame:
        ev = ev[ev.sym.isin(self.cidx)].copy()
        ev["date"] = pd.to_datetime(ev.date)
        n = len(self.idx)
        out = []
        for e in ev.itertuples(index=False):
            k0 = self.idx.searchsorted(e.date)
            kb = k0 + lag
            if kb >= n:
                continue
            j = self.cidx[e.sym]
            b = self.bv[k0, j]
            if b < 0 or np.isnan(self.Cv[kb, j]):
                continue
            r = e._asdict()
            r.update({"day0": self.idx[k0], "size": BUCKETS[b][2], "mcap_cr": self.mcap.iat[k0, j],
                      "liquid": bool(self.U.iat[k0, j])})
            if k0 > PRE:
                ret = self.Cv[k0 - 1, j] / self.Cv[k0 - 1 - PRE, j] - 1
                r["before"] = ret - self._bucket_median(k0 - 1 - PRE, k0 - 1)[b]
            for name, h in H.items():
                if kb + h < n:
                    ret = self.Cv[kb + h, j] / self.Cv[kb, j] - 1
                    r[name] = ret
                    r[f"{name} x"] = ret - self._bucket_median(kb, kb + h)[b]
            out.append(r)
        E = pd.DataFrame(out)
        E["period"] = np.where(E.day0 <= pd.Timestamp(PERIODS["2016-22"][1]), "2016-22",
                               np.where(E.day0 >= pd.Timestamp(PERIODS["2023-26"][0]), "2023-26", "pre-2016"))
        return E

    @staticmethod
    def table(E: pd.DataFrame, by: str, periods=True) -> pd.DataFrame:
        keys = [by, "period"] if periods else [by]
        g = E.groupby(keys, observed=True)
        t = pd.DataFrame({"n": g.size()})
        t["before 3m %"] = g["before"].median() * 100
        for name in H:
            col = f"{name} x"
            if col not in E:
                continue
            t[f"{name} %"] = g[col].median() * 100
            t[f"{name} beat %"] = g[col].apply(lambda x: (x.dropna() > 0).mean() * 100)
        if "12m x" in E:
            t["12m n"] = g["12m x"].count()
            t["12m mean %"] = g["12m x"].mean() * 100
        return t.round(1)


def save(E: pd.DataFrame, tables: dict, name: str):
    out = Path(__file__).resolve().parent.parent / "data" / "research" / "events" / name
    out.mkdir(parents=True, exist_ok=True)
    E.to_csv(out / "events.csv", index=False)
    for k, t in tables.items():
        t.to_csv(out / f"{k}.csv")
    return out
