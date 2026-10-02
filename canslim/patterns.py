"""Chart bases from the book (Ch. 2): find the current base, classify it, locate the
pivot, and flag the faulty-pattern rules.

Detected: cup with handle, cup without handle, flat base, double bottom,
high tight flag. (Saucer/ascending/base-on-base/square box are reported under
the nearest of these; the ranking does not depend on the label.)

Everything uses daily OHLCV up to the analysis date (no look-ahead).
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BUY_ZONE = 0.05          # book: buy within 5% above the pivot
BREAKOUT_VOL = 1.4       # book: breakout volume >= 40-50% above average


@dataclass
class Base:
    kind: str = "none"
    weeks: float = 0
    depth: float = 0            # % from left-side high to base low
    pivot: float = np.nan
    dist: float = np.nan        # % of close vs pivot (+ = above)
    status: str = ""            # forming | near pivot | breakout | extended | none
    stage: int = 0              # base count since the last major low
    handle_depth: float = np.nan
    faults: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def summary(self) -> str:
        if self.kind == "none":
            return self.notes[0] if self.notes else "no sound base"
        s = f"{self.kind} ({self.weeks:.0f}w, -{self.depth:.0f}%, stage {self.stage}) pivot {self.pivot:.2f}, " \
            f"{self.dist:+.1f}% -> {self.status}"
        if self.faults:
            s += " | faults: " + ", ".join(self.faults)
        return s


def _stage(close: pd.Series) -> int:
    """Count bases (>=5-week, >=8% consolidations that were later broken out of)
    since the lowest close of the last 2 years."""
    c = close.iloc[-500:]
    start = int(np.argmin(c.values))
    x = c.iloc[start:].values
    n, i = 0, 0
    run_hi, hi_i = x[0], 0
    while i < len(x):
        if x[i] > run_hi:
            if i - hi_i >= 25 and (run_hi - x[hi_i:i].min()) / run_hi >= 0.12:
                n += 1
            run_hi, hi_i = x[i], i
        i += 1
    # the base being formed now counts as the next one
    return n + 1


def detect(df: pd.DataFrame, index_close: pd.Series | None = None) -> Base:
    df = df.dropna(subset=["close"])
    if len(df) < 120:
        return Base()
    h, l, c, v = (df[k].values for k in ("high", "low", "close", "volume"))
    n = len(c)
    avgv50 = pd.Series(v).rolling(50, min_periods=30).mean().values
    ma50 = pd.Series(c).rolling(50, min_periods=40).mean().values
    b = Base()

    # --- high tight flag: +90% within <=40 days, then a <=25% flag of 3-5 weeks
    for flag_len in range(10, 26):
        pole_end = n - 1 - flag_len
        if pole_end < 45:
            break
        pole_lo = l[pole_end - 40:pole_end].min()
        pole_hi = h[pole_end - 5:pole_end + 1].max()
        flag = slice(pole_end + 1, n)
        if pole_hi / pole_lo >= 1.9 and (pole_hi - l[flag].min()) / pole_hi <= 0.25:
            b.kind, b.weeks = "high tight flag", flag_len / 5
            b.depth = (pole_hi - l[flag].min()) / pole_hi * 100
            b.pivot = max(pole_hi, h[flag].max())
            break

    if b.kind == "none":
        # --- left-side high: highest high of the last 65 weeks that is >= 5 weeks old
        look = min(n - 1, 325)
        seg = h[n - 1 - look:n - 5]
        if len(seg) < 25:
            return b
        if h[n - 5:].max() > seg.max():           # new high in the last week: no base under it now
            b.notes.append("at a new high, no base yet" if c[-1] >= h[n - 5:].max() * 0.97
                           else "new high last week, now pulling back")
            return b
        lip_i = n - 1 - look + int(np.argmax(seg))
        base_len = n - 1 - lip_i
        lip = h[lip_i]
        if base_len < 25:
            b.notes.append(f"{base_len}-day pullback of {(lip - l[lip_i:].min()) / lip * 100:.0f}% "
                           f"from the high: too young to be a base")
            return b
        low_i = lip_i + int(np.argmin(l[lip_i:]))
        low = l[low_i]
        depth = (lip - low) / lip * 100
        b.weeks, b.depth = base_len / 5, depth
        # prior uptrend into the base (book: >= 30%)
        pre = c[max(0, lip_i - 120):lip_i + 1]
        prior_up = (lip / pre.min() - 1) * 100 if len(pre) else 0
        if prior_up < 30:
            b.faults.append(f"weak prior uptrend (+{prior_up:.0f}%)")
        if depth <= 15:
            b.kind, b.pivot = "flat base", lip
        else:
            # double bottom: two troughs, the second undercutting the first, with a middle peak
            body = l[lip_i:]
            k = len(body)
            first_i = int(np.argmin(body[: k // 2 + 1])) if k > 20 else None
            db = False
            if first_i is not None and k - first_i > 15:
                mid_seg = h[lip_i + first_i + 1:]
                later_low_i = first_i + 1 + int(np.argmin(body[first_i + 1:]))
                if later_low_i - first_i >= 10:
                    mid_i = lip_i + first_i + 1 + int(np.argmax(h[lip_i + first_i + 1:lip_i + later_low_i]))
                    mid = h[mid_i]
                    lo1, lo2 = body[first_i], body[later_low_i]
                    if lo2 <= lo1 * 1.01 and lo2 >= lo1 * 0.9 and (mid - lo1) / mid >= 0.07:
                        b.kind, b.pivot, db = "double bottom", mid, True
            if not db:
                # cup: the low sits away from the right edge (not a V) and price recovered the right side
                right = c[low_i:]
                recovered = (c[-1] - low) / (lip - low) if lip > low else 0
                # handle: pullback from the right-side high within the last 5-15 days
                rs_hi_i = low_i + int(np.argmax(h[low_i:]))
                handle_len = n - 1 - rs_hi_i
                hd = (h[rs_hi_i] - l[rs_hi_i:].min()) / h[rs_hi_i] * 100 if handle_len > 0 else 0
                if 5 <= handle_len <= 15 and 3 <= hd <= 15 and h[rs_hi_i] >= lip * 0.85:
                    b.kind, b.pivot, b.handle_depth = "cup with handle", h[rs_hi_i] + 0.1, hd
                    if l[rs_hi_i:].min() < (lip + low) / 2:
                        b.faults.append("handle in lower half")
                    if not np.isnan(ma50[-1]) and l[rs_hi_i:].min() < ma50[-1]:
                        b.faults.append("handle below 50-day MA")
                    hl = l[rs_hi_i:]
                    if len(hl) >= 6 and np.polyfit(range(len(hl)), hl, 1)[0] > 0:
                        b.faults.append("wedging handle")
                    if np.nanmean(v[rs_hi_i:]) > avgv50[-1]:
                        b.notes.append("no volume dry-up in handle")
                else:
                    b.kind, b.pivot = "cup", lip + 0.1
                # V-shape: the low is in the last quarter of the base or recovered too fast
                if (n - 1 - low_i) < base_len * 0.2 and recovered > 0.8:
                    b.faults.append("V-shaped (no time in the base)")
                if base_len < 35:
                    b.faults.append("base under 7 weeks")
        if depth > 50:
            b.faults.append(f"too deep ({depth:.0f}%)")
        if index_close is not None:
            ic = index_close.reindex(df.index).ffill().values
            rs_line = c / ic
            if n > 60 and rs_line[-1] < rs_line[-50]:
                b.notes.append("RS line lower than 10 weeks ago")

    if b.kind == "none":
        return b
    b.stage = _stage(df["close"])
    if b.stage >= 3:
        b.faults.append(f"late-stage base (#{b.stage})")
    b.dist = (c[-1] / b.pivot - 1) * 100
    vol_ok = v[-5:].max() >= BREAKOUT_VOL * avgv50[-1] if not np.isnan(avgv50[-1]) else False
    if b.dist < -5:
        b.status = "forming"
    elif b.dist < 0:
        b.status = "near pivot"
    elif b.dist <= BUY_ZONE * 100:
        b.status = "breakout" if vol_ok else "breakout (light volume)"
    else:
        b.status = "extended"
    return b
