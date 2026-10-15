"""Other stock-picking frameworks, run alongside CAN SLIM (separate lists, separate app page).

Each framework = a score per stock per date (higher = better; NaN = fails the rules), built only from data known
on that date. The same code makes the daily lists (latest date) and the backtests (weekly, canslim/fwtest.py).
Rules are fixed from the original sources before any test; RULES holds the plain-English version shown in the app.

Data notes (also shown in the app):
  - Market cap on a past date = today's share count (Screener) x that day's split-adjusted close. Ignores shares
    issued or bought back since, so P/E and P/B on old dates are approximate.
  - Yearly sales / profit come from summing 4 quarters (history back to ~2006). ROCE, ROE, balance sheet and
    dividends come from Screener's annual tables, which start in FY2015: on early backtest dates the "every year
    for 10 years" checks on those items use the years available (at least 3). The daily lists have 10+ years.
  - Annual numbers count as known 60 days after the year end; quarterly numbers from the announcement date.
"""
import json

import numpy as np
import pandas as pd

from canslim import data, factors

FIN = {"Financial Services"}                 # no ROCE / EV meaning for banks, NBFCs, insurers
MAGIC_EXCL = FIN | {"Utilities"}

RULES = {
    "coffee": ("Coffee Can",
               "Revenue grew at least 10% in at least 9 of the last 10 years (the original rule is all 10; on NSE the COVID year FY2021 leaves only 1-2 stocks, so one miss is allowed) AND return on capital employed (ROCE) was at "
               "least 15% in every one of the last 10 years. Not banks/financials. Buy and hold; ranked by average ROCE."),
    "magic": ("Magic Formula",
              "Rank every non-financial, non-utility company on return on capital (EBIT / (net fixed assets + net working "
              "capital)) and on earnings yield (EBIT / enterprise value); buy the best combined rank, hold about a year. "
              "Here enterprise value = market cap + debt (cash not subtracted) and working capital = other assets minus "
              "other liabilities from Screener (includes cash), floored at zero."),
    "qglp": ("QGLP-style",
             "Quality: average ROE of the last 5 years at least 15% and debt below equity. Growth: 3-year profit growth at "
             "least 15% a year and 3-year sales growth at least 12%. Longevity: ROE at least 15% in 80%+ of the last 10 "
             "years. Price: PEG (P/E divided by profit growth) at most 1.5. Not financials (their debt is not reported "
             "comparably). Ranked by lowest PEG."),
    "garp": ("GARP (growth at a reasonable price)",
              "Profitable, 3-year profit growth between 15% and 50% a year, PEG at most 1.0, debt at most half of equity. "
              "Not financials. Ranked by lowest PEG."),
    "graham": ("Benjamin Graham (defensive investor, adapted)",
               "Not financials. P/E at most 15 and P/E x P/B at most 22.5; debt at most half of equity; a profit in each of "
               "the last 10 years; a dividend every year; profit up at least a third over 10 years (average of the last "
               "3 years vs the first 3). Ranked by lowest P/E x P/B."),
    "trend": ("Trend template",
                  "Price above the 150- and 200-day averages; 150-day above 200-day; 200-day rising for at least a month; "
                  "50-day above both; price above the 50-day; at least 30% above the 52-week low and within 25% of the "
                  "52-week high; RS rating at least 70. Ranked by RS. (The full SEPA method also needs strong earnings "
                  "and a tight base; this is the published screen.)"),
    "stage": ("Stage analysis",
                  "Stage 2: price above a rising 30-week (150-day) average and Mansfield relative strength vs the Nifty "
                  "500 above zero. New buys only within 4 weeks of a breakout above the prior 6-month high on at least "
                  "twice the average volume, after a flat base (30-week average moved less than 10% in the 6 months "
                  "before). Held while in stage 2; ranked by Mansfield RS."),
}


# ------------------------------------------------------------------ fundamentals (point in time)
def _row(tbl: dict, key: str) -> pd.Series:
    s = {}
    for k, v in (tbl.get(key) or {}).items():
        try:
            s[pd.Timestamp(k) + pd.offsets.MonthEnd(0)] = v
        except Exception:
            pass
    r = pd.Series(s, dtype=float).dropna().sort_index()
    r.index = pd.DatetimeIndex(r.index)
    return r


def _fy_from_quarters(q: pd.DataFrame) -> pd.DataFrame:
    """Fiscal years (to March) summed from 4 quarters; indexed by the date the 4th quarter became known."""
    fy = q.index.year + (q.index.month > 3)
    g = q.assign(fy=fy).groupby("fy")
    t = pd.DataFrame({"sales": g.sales.sum(), "np": g.np.sum(), "n": g.sales.count(), "known": g.known.max()})
    t = t[t.n == 4]
    return t


def _events(sym: str, raw: dict, f: dict, ev: dict) -> pd.DataFrame | None:
    """Per stock: one row per date something new became known, with every metric the frameworks use."""
    if sym not in ev:
        return None
    parts = []
    # long sales / profit record from quarterly sums
    t = _fy_from_quarters(f["q"])
    if len(t) >= 2:
        yr = t.index.to_series()
        span = lambda k: (yr - yr.shift(k)) == k                   # k rows back = exactly k years back (no gaps)
        g = t.sales.pct_change().where(span(1))
        x = pd.DataFrame(index=t.index)
        x["sales_g_min10"] = g.rolling(10, min_periods=10).min()
        x["sales_g_hit10"] = (g >= 0.10).astype(float).where(g.notna()).rolling(10, min_periods=10).sum()
        x["sales_cagr3"] = ((t.sales / t.sales.shift(3)) ** (1 / 3) - 1).where(span(3))
        x["np_pos10"] = (t.np > 0).astype(float).rolling(10, min_periods=10).min().where(span(9))
        avg_last3, avg_first3 = t.np.rolling(3).mean(), t.np.shift(7).rolling(3).mean()
        x["np_up10"] = (avg_last3 / avg_first3 - 1).where((avg_first3 > 0) & span(9))
        x.index = pd.DatetimeIndex(t.known.values)
        parts.append(x)
    # annual tables (known 60 days after the year end)
    a, b, r = raw.get("annual") or {}, raw.get("balance") or {}, raw.get("ratios") or {}
    eq = _row(b, "Equity Capital").add(_row(b, "Reserves"), fill_value=0)
    y = pd.DataFrame({"equity": eq, "debt": _row(b, "Borrowings"), "fa": _row(b, "Fixed Assets"),
                      "oa": _row(b, "Other Assets"), "ol": _row(b, "Other Liabilities"),
                      "op": _row(a, "Operating Profit"), "dep": _row(a, "Depreciation"),
                      "anp": _row(a, "Net Profit"), "payout": _row(a, "Dividend Payout %"),
                      "roce": _row(r, "ROCE %")})
    if len(y):
        y = y.sort_index()
        roe = (y.anp / y.equity * 100).where(y.equity > 0, -100.0).where(y.anp.notna())   # negative equity = a failed year
        z = pd.DataFrame(index=y.index)
        z["roce_min10"] = y.roce.rolling(10, min_periods=3).min()
        z["roce_avg10"] = y.roce.rolling(10, min_periods=3).mean()
        z["roe_avg5"] = roe.rolling(5, min_periods=3).mean()
        z["roe_hit10"] = (roe >= 15).astype(float).where(roe.notna()).rolling(10, min_periods=3).mean()
        z["de"] = (y.debt.fillna(0) / y.equity).where(y.equity > 0)
        z["equity"], z["debt"] = y.equity, y.debt.fillna(0)
        z["ebit"] = y.op - y.dep.fillna(0)
        z["capital"] = y.fa.fillna(0) + (y.oa.fillna(0) - y.ol.fillna(0)).clip(lower=0)
        z["div_every"] = (y.payout.fillna(0) > 0).astype(float).rolling(10, min_periods=3).min()
        z.index = z.index + pd.Timedelta(days=60)
        parts.append(z)
    q = ev[sym][["ttm_np", "ttm_cagr3"]]
    parts.append(q)
    e = pd.concat(parts, axis=1).sort_index()
    e = e[~e.index.duplicated(keep="last")]
    return e.ffill().reindex(columns=FCOLS)


def load(fund: dict | None = None):
    """Returns (events per stock, shares in crore per stock, sector per stock)."""
    fund = fund or data.fundamentals()
    ev = factors.fundamental_events(fund)
    out, shares, sector = {}, {}, {}
    for fp in data.FUND.glob("*.json"):
        sym = fp.stem
        if sym.startswith("_") or sym not in fund:
            continue
        raw = json.loads(fp.read_text(encoding="utf-8"))
        top = raw.get("top") or {}
        mc, px = top.get("Market Cap"), top.get("Current Price")
        if mc and px:
            shares[sym] = mc / px
        sector[sym] = fund[sym]["sector"]
        e = _events(sym, raw, fund[sym], ev)
        if e is not None and len(e):
            out[sym] = e
    return out, pd.Series(shares, dtype=float), pd.Series(sector)


FCOLS = ["sales_g_min10", "sales_g_hit10", "sales_cagr3", "np_pos10", "np_up10", "roce_min10", "roce_avg10", "roe_avg5", "roe_hit10",
         "de", "equity", "debt", "ebit", "capital", "div_every", "ttm_np", "ttm_cagr3"]


# ------------------------------------------------------------------ the frameworks
def compute(P: dict, U: pd.DataFrame, rs_ibd: pd.DataFrame, dates: pd.DatetimeIndex, loaded=None) -> dict:
    """P = daily price panels; U, rs_ibd = universe and RS on (at least) `dates`.
    Returns {name: {"score": dates x stocks, "entry": dates x stocks or None, "inputs": {label: dates x stocks}}}."""
    ev, shares, sector = loaded or load()
    cols = P["close"].columns
    F = factors.fundamental_panel(ev, dates, FCOLS)
    F = {k: v.reindex(columns=cols) for k, v in F.items()}
    c, h, lo, v = (P[k] for k in ("close", "high", "low", "volume"))
    cl = c.reindex(dates)
    Ud = U.reindex(index=dates, columns=cols).fillna(False).astype(bool)
    sec = sector.reindex(cols)
    nonfin = pd.DataFrame(np.repeat((~sec.isin(FIN)).values[None, :], len(dates), 0), index=dates, columns=cols)
    nonmagic = pd.DataFrame(np.repeat((~sec.isin(MAGIC_EXCL) & sec.notna()).values[None, :], len(dates), 0),
                            index=dates, columns=cols)
    mcap = cl * shares.reindex(cols)                                        # Rs crore
    pe = (mcap / F["ttm_np"]).where(F["ttm_np"] > 0)
    pb = (mcap / F["equity"]).where(F["equity"] > 0)
    g3 = F["ttm_cagr3"]                                                      # % a year
    peg = (pe / g3).where(g3 > 0)
    out = {}

    # Coffee Can
    ok = Ud & nonfin & (F["sales_g_hit10"] >= 9) & (F["roce_min10"] >= 15)
    out["coffee"] = {"score": F["roce_avg10"].where(ok), "entry": None,
                     "inputs": {"Years of 10%+ sales growth (of 10)": F["sales_g_hit10"], "Worst year sales growth %": F["sales_g_min10"] * 100,
                                "Min ROCE": F["roce_min10"], "Avg ROCE": F["roce_avg10"], "P/E": pe}}
    # Magic Formula
    ev_ = mcap + F["debt"]
    ok = Ud & nonmagic & (F["ebit"] > 0) & (F["capital"] > 0) & (ev_ > 0)
    roc = (F["ebit"] / F["capital"]).where(ok)
    ey = (F["ebit"] / ev_).where(ok)
    comb = roc.rank(axis=1, ascending=False) + ey.rank(axis=1, ascending=False)
    out["magic"] = {"score": -comb, "entry": None,
                    "inputs": {"Return on capital %": roc * 100, "Earnings yield %": ey * 100, "P/E": pe}}
    # QGLP-style
    ok = (Ud & nonfin & (F["roe_avg5"] >= 15) & (F["de"] < 1) & (g3 >= 15) & (F["sales_cagr3"] >= 0.12)
          & (F["roe_hit10"] >= 0.8) & (peg <= 1.5))
    out["qglp"] = {"score": -peg.where(ok), "entry": None,
                   "inputs": {"Avg ROE 5y": F["roe_avg5"], "Profit growth 3y %": g3,
                              "Sales growth 3y %": F["sales_cagr3"] * 100, "P/E": pe, "PEG": peg}}
    # GARP
    ok = Ud & nonfin & (F["ttm_np"] > 0) & (g3 >= 15) & (g3 <= 50) & (peg <= 1.0) & (F["de"] <= 0.5)
    out["garp"] = {"score": -peg.where(ok), "entry": None,
                    "inputs": {"Profit growth 3y %": g3, "P/E": pe, "PEG": peg, "Debt/equity": F["de"]}}
    # Graham
    ok = (Ud & nonfin & (pe <= 15) & (pe * pb <= 22.5) & (F["de"] <= 0.5) & (F["np_pos10"] == 1)
          & (F["div_every"] == 1) & (F["np_up10"] >= 1 / 3))
    out["graham"] = {"score": -(pe * pb).where(ok), "entry": None,
                     "inputs": {"P/E": pe, "P/B": pb, "P/E x P/B": pe * pb, "Debt/equity": F["de"],
                                "Profit growth 10y %": F["np_up10"] * 100}}
    # Trend template
    ma50, ma150, ma200 = (c.rolling(n, min_periods=int(n * .9)).mean() for n in (50, 150, 200))
    hi52, lo52 = h.rolling(252, min_periods=200).max(), lo.rolling(252, min_periods=200).min()
    tmpl = ((c > ma150) & (c > ma200) & (ma150 > ma200) & (ma200 > ma200.shift(21)) & (ma50 > ma150)
            & (ma50 > ma200) & (c > ma50) & (c >= 1.3 * lo52) & (c >= 0.75 * hi52)).reindex(dates).fillna(False)
    rs = rs_ibd.reindex(index=dates, columns=cols).where(Ud).rank(axis=1, pct=True) * 99
    ok = Ud & tmpl & (rs >= 70)
    out["trend"] = {"score": rs.where(ok), "entry": None,
                        "inputs": {"RS": rs, "% of 52w high": (c / hi52 * 100).reindex(dates),
                                   "% above 52w low": ((c / lo52 - 1) * 100).reindex(dates)}}
    # Stage analysis, stage 2
    idx = data.index_close("NIFTY500").reindex(c.index).ffill()
    rel = c.div(idx, axis=0)
    mansfield = (rel / rel.rolling(260, min_periods=200).mean() - 1) * 100
    stage2 = (c > ma150) & (ma150 > ma150.shift(20)) & (mansfield > 0)
    avgv = v.rolling(50, min_periods=40).mean()
    flat = (ma150.shift(1) / ma150.shift(131) - 1).abs() <= 0.10
    brk = (c > h.rolling(130, min_periods=120).max().shift(1)) & (v >= 2 * avgv.shift(1)) & flat
    recent = brk.astype(float).rolling(20, min_periods=1).max() > 0
    ok = Ud & stage2.reindex(dates).fillna(False)
    out["stage"] = {"score": mansfield.reindex(dates).where(ok), "entry": recent.reindex(dates).fillna(False),
                        "inputs": {"Mansfield RS": mansfield.reindex(dates),
                                   "% above 30-wk avg": ((c / ma150 - 1) * 100).reindex(dates),
                                   "Breakout in last 4 wks": recent.reindex(dates).astype(float)}}
    return out


def daily_lists(P: dict, U: pd.DataFrame, rs_ibd: pd.DataFrame, n: int = 15, fund: dict | None = None) -> dict:
    """Latest-date lists: {name: DataFrame(rank, symbol, close, score, inputs...)}; stage analysis shows new breakouts first."""
    d = P["close"].index[-1]
    res = compute(P, U, rs_ibd, pd.DatetimeIndex([d]), loaded=load(fund))
    lists = {}
    for name, r in res.items():
        s = r["score"].iloc[-1].dropna()
        if r["entry"] is not None:                     # new breakouts first, then the rest of stage 2
            e = r["entry"].iloc[-1].reindex(s.index).fillna(False)
            s = pd.concat([s[e].sort_values(ascending=False), s[~e].sort_values(ascending=False)])
        else:
            s = s.sort_values(ascending=False)
        s = s.head(n)
        df = pd.DataFrame({"symbol": s.index, "close": P["close"].iloc[-1].reindex(s.index).round(2).values})
        for lab, x in r["inputs"].items():
            df[lab] = x.iloc[-1].reindex(s.index).round(2).values
        df.insert(0, "rank", range(1, len(df) + 1))
        lists[name] = df
    return lists
