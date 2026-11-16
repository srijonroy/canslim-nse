"""Buy when a stock touches its 200-day average, cut losers at 7-8%, let winners run (user idea, 2026-11-16).

Separate strategy, not a change to CAN SLIM. Own small simulator here because the live one sells whatever drops
out of the daily ranking, and a touch is a one-day event.

Mechanics (same conventions as the live backtest):
  * signal at the close of a touch day, bought at the NEXT open; 10 equal slots (slot = equity / 10), max 3 per
    industry; when more signals than free slots, highest RS first; idle cash earns 6%/yr; 0.3% cost per side
  * touch = the day's range came within 1% of the 200-day SMA or EMA (as canslim/ma200.py)
  * stop: a close <= entry x (1 - stop) sells at the next open (same as the live simulator / the book)
  * no re-buy of the same stock for 10 sessions after selling it
Entries
  pullback   touch, the close stayed > 3% above the 200-day SMA 5-30 sessions earlier, and the 200-day SMA is
             higher than 20 sessions ago (the classic "buy the first dip to the 200")
  any touch  every touch in the liquid universe
Exits ("let winners run")
  stop only  nothing but the stop; a winner is held to the end of the period
  + trail    stop, and once in profit sell on a close 25% below the highest close since entry
Decision bar (fixed before running): Sharpe above Nifty 500's in BOTH halves of 2016-22. 2023+ is shown only.
"""
import numpy as np
import pandas as pd

from canslim import portfolio as pf
from canslim import tune
from canslim.exp import TUNE_OUT, Experiment, Outcome

N, COST, CASH, MAXG, COOLDOWN = 10, 0.003, 0.06, 3, 10


def signals(P, U, kind):
    c, h, lo = P["close"], P["high"], P["low"]
    sma = c.rolling(200, min_periods=200).mean()
    ema = c.ewm(span=200, adjust=False, min_periods=200).mean()
    hit = lambda m: (lo <= m * 1.01) & (h >= m * 0.99)
    t = (hit(sma) | hit(ema)) & U.reindex_like(c).fillna(False).astype(bool)
    if kind == "pullback":
        rel = c / sma
        above = rel.shift(5).rolling(26, min_periods=26).min() > 1.03          # sessions t-30 .. t-5
        t &= above & (sma > sma.shift(20))
    return t


def simulate(P, sig, rank, ind, start, end, stop, trail=None, mstate=None):
    days = P["close"].loc[start:end].index
    O = P["open"].reindex(days).values
    C = P["close"].reindex(days).values
    S = sig.reindex(days).fillna(False).values
    R = rank.reindex(days).values
    syms = list(P["close"].columns)
    grp = [ind.get(s) for s in syms]
    ms = None if mstate is None else mstate.reindex(days).values
    cash, pos, trades, eq, expo = 1.0, {}, [], [], []
    pend_buy, pend_sell, last_exit = [], set(), {}
    daily_cash = (1 + CASH) ** (1 / 252) - 1
    for k in range(len(days)):
        # 1) fills at the open
        for j in list(pend_sell):
            px = O[k, j]
            if not px == px:
                continue
            h = pos.pop(j)
            cash += h["sh"] * px * (1 - COST)
            trades.append({"symbol": syms[j], "entry_date": days[h["k"]], "exit_date": days[k],
                           "ret": px * (1 - COST) / (h["entry"] * (1 + COST)) - 1, "days": k - h["k"], "why": h["why"]})
            last_exit[j] = k
            pend_sell.discard(j)
        if pend_buy:
            equity = cash + sum(h["sh"] * h["last"] for h in pos.values())
            slot = equity / N
            for j in pend_buy:
                px = O[k, j]
                if len(pos) >= N or j in pos or not px == px or cash < slot * 0.5:
                    continue
                spend = min(slot, cash)
                pos[j] = {"sh": spend * (1 - COST) / px, "entry": px, "peak": px, "last": px, "k": k, "why": ""}
                cash -= spend
            pend_buy = []
        # 2) mark at the close, exits for tomorrow
        for j, h in pos.items():
            if C[k, j] == C[k, j]:
                h["last"] = C[k, j]
                h["peak"] = max(h["peak"], h["last"])
            if j in pend_sell:
                continue
            if h["last"] <= h["entry"] * (1 - stop):
                pend_sell.add(j); h["why"] = "stop"
            elif trail and h["peak"] > h["entry"] and h["last"] <= h["peak"] * (1 - trail):
                pend_sell.add(j); h["why"] = "trail"
        equity = cash + sum(h["sh"] * h["last"] for h in pos.values())
        eq.append(equity)
        expo.append(1 - cash / equity)
        cash *= 1 + daily_cash
        # 3) new signals at the close
        free = N - (len(pos) - len(pend_sell))
        if free > 0 and (ms is None or ms[k] in ("CONFIRMED_UPTREND", "UPTREND_UNDER_PRESSURE")):
            cand = np.flatnonzero(S[k])
            cand = [j for j in cand if j not in pos and k - last_exit.get(j, -999) > COOLDOWN]
            cand.sort(key=lambda j: -(R[k, j] if R[k, j] == R[k, j] else -9))
            gcount = pd.Series([grp[j] for j in pos if j not in pend_sell]).value_counts().to_dict()
            for j in cand:
                if len(pend_buy) >= free:
                    break
                g = grp[j]
                if g is not None and gcount.get(g, 0) >= MAXG:
                    continue
                gcount[g] = gcount.get(g, 0) + 1
                pend_buy.append(j)
    for j, h in pos.items():                                              # still open at the end: marked at the close
        trades.append({"symbol": syms[j], "entry_date": days[h["k"]], "exit_date": None,
                       "ret": h["last"] / (h["entry"] * (1 + COST)) - 1, "days": len(days) - 1 - h["k"], "why": "open"})
    e = pd.Series(eq, index=days)
    T = pd.DataFrame(trades)
    st = pf.stats(e, T, pd.Series(expo, index=days))
    if len(T):
        st["stopped %"] = round((T.why == "stop").mean() * 100, 0)
        st["median days held"] = int(T.days.median())
        st["best trade %"] = round(T.ret.max() * 100, 0)
        st["trades >= +100% "] = int((T.ret >= 1).sum())
    return e, T, st


VARIANTS = [  # name, entry, stop, trail, market filter
    ("pullback, 8% stop only", "pullback", 0.08, None, False),
    ("pullback, 8% stop + 25% trail", "pullback", 0.08, 0.25, False),
    ("pullback, 7% stop + 25% trail", "pullback", 0.07, 0.25, False),
    ("pullback, 8% stop + 25% trail, uptrend only", "pullback", 0.08, 0.25, True),
    ("any touch, 8% stop only", "any", 0.08, None, False),
    ("any touch, 8% stop + 25% trail", "any", 0.08, 0.25, False),
]


def run(ctx) -> Outcome:
    lab = ctx.lab
    P, U, rs = lab.P, lab.U, lab.S["rs_ibd"]
    sig = {k: signals(P, U, k) for k in ("pullback", "any")}
    nifty = ctx.index("NIFTY 500")
    rows, trades_all = [], {}
    periods = {"2016-22": tune.TUNE, "2023+": tune.HOLD}

    def add(name, pname, e, st):
        r = {"period": pname, "variant": name, **{k: st.get(k) for k in
             ("CAGR %", "Sharpe", "maxDD %", "invested %", "trades/yr", "win %", "avg win %", "avg loss %",
              "stopped %", "median days held", "best trade %", "trades >= +100% ")}}
        if pname == "2016-22":
            for hn, (a, b) in tune.HALVES.items():
                s2 = pf.stats(e.loc[a:b])
                r[f"Sharpe {hn}"], r[f"CAGR {hn}"] = s2["Sharpe"], s2["CAGR %"]
        rows.append(r)
        print(f"  {pname:<8} {name:<46} CAGR {r['CAGR %']:>5}  Sharpe {r['Sharpe']:>5}  maxDD {r['maxDD %']:>6}  "
              f"win {r.get('win %')}  stopped {r.get('stopped %')}", flush=True)

    for pname, (a, b) in periods.items():
        n = nifty.loc[a:b]
        add("Nifty 500 (index)", pname, n / n.iloc[0], pf.stats(n))
        live = ctx.run(period=(a, b))
        add("CAN SLIM live system", pname, live.equity, {**live.stats, **pf.stats(live.equity, live.trades)})
        for name, kind, stop, trail, mf in VARIANTS:
            e, T, st = simulate(P, sig[kind], rs, lab.ind, a, b, stop, trail, lab.ms if mf else None)
            add(name, pname, e, st)
            trades_all[(pname, name)] = T
    t = pd.DataFrame(rows)
    T = t[t.period == "2016-22"].set_index("variant")
    nb = T.loc["Nifty 500 (index)"]
    cs = T.loc["CAN SLIM live system"]
    names = [v[0] for v in VARIANTS]
    passed = [n for n in names if all(T.at[n, f"Sharpe {h}"] > nb[f"Sharpe {h}"] for h in tune.HALVES)]
    beat_cs = [n for n in passed if T.at[n, "Sharpe"] > cs["Sharpe"]]
    t["passes bar"] = [r.period == "2016-22" and r.variant in passed for r in t.itertuples()]
    best = T.loc[names].sort_values("Sharpe", ascending=False).iloc[0]
    H = t[t.period == "2023+"].set_index("variant")
    decision = ((", ".join(passed) + " beat Nifty 500 in both halves of 2016-22"
                 + ("; " + ", ".join(beat_cs) + " also beat CAN SLIM" if beat_cs else "; none beats CAN SLIM"))
                if passed else "no variant beats Nifty 500 in both halves of 2016-22")
    takeaway = (f"Best version 2016-22: {best.name} - {best['CAGR %']}%/yr, Sharpe {best['Sharpe']}, worst drop "
                f"{best['maxDD %']}%, {best['win %']}% of trades win, {best['stopped %']}% end at the stop. Nifty 500: "
                f"{nb['CAGR %']}%/yr, Sharpe {nb['Sharpe']}, worst drop {nb['maxDD %']}%; CAN SLIM {cs['CAGR %']}%/yr, "
                f"Sharpe {cs['Sharpe']}, worst drop {cs['maxDD %']}%. 2023+ (shown only): {best.name} "
                f"{H.at[best.name, 'CAGR %']}%/yr vs Nifty 500 {H.at['Nifty 500 (index)', 'CAGR %']}% and CAN SLIM "
                f"{H.at['CAN SLIM live system', 'CAGR %']}%. {decision}.")
    yr = []
    for name in names:
        for pname, (a, b) in periods.items():
            Tt = trades_all[(pname, name)]
            if len(Tt):
                Tt = Tt.assign(year=pd.to_datetime(Tt.entry_date).dt.year)
                yr.append(Tt.groupby("year").agg(trades=("ret", "size"), win=("ret", lambda x: round((x > 0).mean() * 100)),
                                                 avg=("ret", lambda x: round(x.mean() * 100, 1))).assign(variant=name))
    Y = pd.concat(yr).reset_index() if yr else pd.DataFrame()
    if len(Y):
        (TUNE_OUT / "ma200-touch").mkdir(parents=True, exist_ok=True)
        Y.to_csv(TUNE_OUT / "ma200-touch" / "trades_by_year.csv", index=False)
    body = ("Trades by entry year (all variants): data/tune/ma200-touch/trades_by_year.csv.\n\n"
            "Caveats: only stocks listed today (survivorship, ~0.2-1 pt/yr in our earlier check); fills at the "
            "next open with 0.3% cost; the stop is checked on closes, so a gap down can lose more than 8%.")
    return Outcome(t, decision, takeaway, body,
                   "Passed the bar - needs a decision" if passed else "Tested, not adopted", tested=len(VARIANTS))


EXPERIMENT = Experiment(
    slug="ma200-touch", title="Buy the touch of the 200-day average, cut losers at 7-8%, let winners run",
    question="If we buy a stock when it touches its 200-day moving average, sell it if it falls 7-8% below the "
             "buy price and otherwise let it run, how does that do against Nifty 500 and the CAN SLIM system?",
    tags="200-day moving average, pullback, stop loss, trailing stop, separate strategy", bar=None, run=run,
    method=__doc__.split("Mechanics", 1)[1].split("Decision bar")[0].strip())
