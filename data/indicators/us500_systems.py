"""Published S&P 500 systems, tested on 16 years of US500 5m data (HistData SPXUSD, NY time).

1 NOISE  Intraday momentum, Zarattini/Aziz/Barbon 2024 "Beat the Market". Band = average |move from the
         open| at that time of day over the last 14 days, around max/min(open, prev close). Checked every
         30 min from 10:00 ET: above band -> long, below -> short; exit if price falls back inside the band
         or crosses the session's average price (VWAP stand-in: HistData has no volume); flat at 16:00.
2 TOD    Time-of-day momentum, Gao/Han/Li/Zhou 2018: sign of prev close -> 10:00 return, held 15:30 -> 16:00.
3 RSI2   Connors: close > 200-day average and RSI(2) < 10 -> buy next open; sell next open after close > 5-day avg.
B&H      Buy and hold the CFD (pays financing every night).

Costs: spread 0.4 pt per round trip at a 6700 index level, scaled with price. CFD long financing 7%/yr
per calendar night (Pepperstone ~ benchmark rate + 2.5%); shorts pay nothing in this model.
Fills at the next 5m bar's open after a decision. Returns are % of position value at 1x.
Usage: python us500_systems.py <5m parquet>
"""
import sys, numpy as np, pandas as pd

SPLIT = "2019-01-01"
FIN = 0.07 / 365

d = pd.read_parquet(sys.argv[1])
d.index = d.index.tz_convert("America/New_York")
d = d[d.index.dayofweek < 5]
t = d.index.hour * 60 + d.index.minute
cash = d[(t >= 570) & (t < 960)].copy()                      # 09:30 .. 15:55 bar starts
cash["date"] = cash.index.normalize().tz_localize(None)
cash["slot"] = ((cash.index.hour * 60 + cash.index.minute) - 570) // 5   # 0..77
O = cash.pivot_table(index="date", columns="slot", values="Open").reindex(columns=range(78))
C = cash.pivot_table(index="date", columns="slot", values="Close").reindex(columns=range(78))
good = O.notna().sum(axis=1) >= 70                          # skip half days / broken days
O, C = O[good].ffill(axis=1).bfill(axis=1), C[good].ffill(axis=1).bfill(axis=1)
days = O.index
dopen, dclose = O[0].to_numpy(), C[77].to_numpy()
prevc = np.r_[np.nan, dclose[:-1]]
cost = 0.4 / 6700                                            # fraction of price per round trip
o, c = O.to_numpy(), C.to_numpy()

# ---------- 1 NOISE ----------
move = np.abs(c / dopen[:, None] - 1)
sigma = pd.DataFrame(move).rolling(14).mean().shift(1).to_numpy()     # previous 14 days only
up = np.maximum(dopen, prevc)[:, None] * (1 + sigma)
dn = np.minimum(dopen, prevc)[:, None] * (1 - sigma)
avgp = np.cumsum(c, axis=1) / np.arange(1, 79)               # running average price since open
checks = list(range(5, 77, 6))                               # bars ending 10:00, 10:30 ... 15:30
noise = np.full(len(days), np.nan); ntr = np.zeros(len(days))
for k in range(len(days)):
    if np.isnan(sigma[k, 0]) or np.isnan(prevc[k]): continue
    pos, entry, pnl, n = 0, 0.0, 0.0, 0
    for s in checks:
        px = c[k, s]
        if pos == 1 and px < max(up[k, s], avgp[k, s]) or pos == -1 and px > min(dn[k, s], avgp[k, s]):
            pnl += pos * (o[k, s + 1] / entry - 1) - cost; pos = 0
        if pos == 0:
            new = 1 if px > up[k, s] else -1 if px < dn[k, s] else 0
            if new: pos, entry, n = new, o[k, s + 1], n + 1
    if pos: pnl += pos * (c[k, 77] / entry - 1) - cost
    noise[k], ntr[k] = pnl, n

# ---------- 2 TOD ----------
first = c[:, 5] / prevc - 1                                  # prev close -> 10:00
tod = np.sign(first) * (c[:, 77] / o[:, 72] - 1) - np.where(first != 0, cost, 0)

# ---------- 3 RSI2 (daily) ----------
cl = pd.Series(dclose, days)
ma200, ma5 = cl.rolling(200).mean(), cl.rolling(5).mean()
chg = cl.diff(); g = chg.clip(lower=0).ewm(alpha=1/2, adjust=False).mean(); l = (-chg.clip(upper=0)).ewm(alpha=1/2, adjust=False).mean()
rsi = 100 - 100 / (1 + g / l)
rsi2 = np.zeros(len(days)); inpos = False
for k in range(1, len(days)):                                # P&L of day k, decisions made at close k-1
    if inpos:
        ref = dopen[k] if enter_today else dclose[k - 1]
        rsi2[k] += dclose[k] / ref - 1 - FIN * (days[k] - days[k - 1]).days
        enter_today = False
        if cl.iloc[k] > ma5.iloc[k]:                         # exit at next open
            if k + 1 < len(days): rsi2[k + 1] += dopen[k + 1] / dclose[k] - 1 - cost
            inpos = False; continue
    if not inpos and cl.iloc[k] > ma200.iloc[k] and rsi.iloc[k] < 10 and k + 1 < len(days):
        inpos, enter_today = True, True
        rsi2[k + 1] -= 0                                     # entry handled on day k+1 (open -> close)
rsi2 = pd.Series(rsi2, days)

# ---------- B&H ----------
bh = cl.pct_change().fillna(0) - FIN * pd.Series(days, days).diff().dt.days.fillna(0)

R = pd.DataFrame({"NOISE intraday momentum": noise, "TOD last half hour": tod,
                  "RSI2 dip buying": rsi2.to_numpy(), "Buy & hold CFD": bh.to_numpy()}, index=days).fillna(0)
R = R[R.index >= "2011-09-01"]                               # after 200 days of history

def stats(r):
    yrs = len(r) / 252; eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (1 / yrs) - 1; vol = r.std() * np.sqrt(252)
    dd = (eq / eq.cummax() - 1).min(); act = (r != 0).mean()
    return dict(CAGR=f"{100*cagr:.1f}%", vol=f"{100*vol:.1f}%", Sharpe=round(r.mean() / r.std() * np.sqrt(252), 2) if r.std() else 0,
                maxDD=f"{100*dd:.0f}%", days_in=f"{100*act:.0f}%")

print(f"US500 5m, {len(R)} trading days {R.index[0]:%Y-%m-%d} -> {R.index[-1]:%Y-%m-%d}; 1x exposure, after costs")
for name, part in (("DESIGN 2011-2018", R[R.index < SPLIT]), ("HOLD-OUT 2019-2026", R[R.index >= SPLIT]), ("ALL", R)):
    print(f"\n== {name}"); print(pd.DataFrame({k: stats(part[k]) for k in R}).T.to_string())
yr = R.groupby(R.index.year).apply(lambda q: (1 + q).prod() - 1).mul(100).round(1)
yr.loc["years > 0"] = (yr > 0).sum()
print("\n== return per year, %"); print(yr.to_string())
print(f"\nNOISE: avg {ntr[ntr > 0].mean():.2f} trades on days it trades, trades on {100*(ntr > 0).mean():.0f}% of days")
R.to_parquet(r"c:\Project\asd\data\us500\systems_daily.parquet")
