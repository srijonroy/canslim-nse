"""Event tests (descriptive). Each test builds an event list and runs it through canslim.eventstudy.

  earnings   result-day reaction and the drift after it (post-earnings drift)
  insiders   promoter / director open-market buys and promoter sales (SEBI PIT disclosures, 2016+)
  pledges    promoter pledge created / released / invoked (SEBI PIT disclosures, 2016+)
  announcements  buyback, bonus, split, demerger, auditor/CFO resignation, QIP, preferential, exchange
             price/volume queries, rating changes (NSE announcements 2012+)

usage: python -m canslim.eventtests earnings
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from canslim import tune
from canslim.eventstudy import EventStudy, save

EVENTS = Path(__file__).resolve().parent.parent / "data" / "events"
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)


def show(title, t):
    print(f"\n=== {title} ===")
    print(t.to_string())


def earnings(es: EventStudy):
    """Every quarterly result 2016+ (announce date = when the result became known, factors.fundamental_events).
    Reaction = excess return close day -2 -> day +1 (the stamp can be a day late). Buy = close day +2."""
    B = tune.cached_build()
    rows = []
    for sym, df in B["events"].items():
        if "last_ann" not in df:
            continue
        g = df.dropna(subset=["last_ann"]).groupby("last_ann").last()
        for dn, r in g.iterrows():
            d = pd.Timestamp("1970-01-01") + pd.Timedelta(days=int(dn))
            if d >= pd.Timestamp("2015-10-01"):
                rows.append({"sym": sym, "date": d, "np_yoy": r.get("np_yoy"), "sales_yoy": r.get("sales_yoy")})
    ev = pd.DataFrame(rows)
    print(f"{len(ev)} result announcements", flush=True)
    E = es.run(ev, lag=2)
    # reaction around the announcement
    react = []
    for s, d in zip(E.sym, E.day0):
        k0, j = es.idx.get_loc(d), es.cidx[s]
        b = es.bv[k0, j]
        if k0 < 2 or k0 + 1 >= len(es.idx):
            react.append(np.nan)
            continue
        ret = es.Cv[k0 + 1, j] / es.Cv[k0 - 2, j] - 1
        react.append(ret - es._bucket_median(k0 - 2, k0 + 1)[b])
    E["reaction"] = react
    E = E[(E.period != "pre-2016") & E.liquid.eq(True)]
    E["reaction band"] = pd.cut(E.reaction, [-10, -0.10, -0.03, 0.03, 0.10, 0.20, 10],
                                labels=["< -10%", "-10..-3%", "-3..+3%", "+3..+10%", "+10..+20%", "> +20%"])
    E["profit growth"] = pd.cut(E.np_yoy, [-1e9, 0, 25, 1e9], labels=["profit down", "0-25%", "> 25%"])
    E["strong + gap"] = np.where((E.np_yoy > 25) & (E.reaction > 0.05), "profit >25% AND reaction > +5%",
                                 np.where((E.np_yoy > 25) & (E.reaction < -0.03), "profit >25% BUT reaction < -3%",
                                          "other"))
    tabs = {}
    for by in ["reaction band", "profit growth", "strong + gap", "size"]:
        tabs[by] = es.table(E, by)
        show(f"earnings by {by} (excess vs same-size median; buy = close day +2)", tabs[by])
    print("\nsaved to", save(E, tabs, "earnings"))


def load_pit() -> pd.DataFrame:
    import glob
    import json
    rows = []
    for f in sorted(glob.glob(str(EVENTS / "pit" / "*.json"))):
        rows += json.loads(Path(f).read_text(encoding="utf-8"))
    d = pd.DataFrame(rows)
    d["pub"] = pd.to_datetime(d["date"], format="%d-%b-%Y %H:%M", errors="coerce")
    d["value"] = pd.to_numeric(d.secVal, errors="coerce")
    d["promoter"] = d.personCategory.isin(["Promoters", "Promoter Group"])
    d["insider"] = d.personCategory.isin(["Director", "Key Managerial Personnel"])
    d["equity"] = d.secType.str.lower().str.contains("equity|shares", na=False)
    return d[d.pub.notna() & d.equity]


def first_in_window(d: pd.DataFrame, gap_days=90, value_days=30) -> pd.DataFrame:
    """One event per burst: the first disclosure after `gap_days` without one for that symbol.
    'value' = total value disclosed in the burst's first `value_days`."""
    out = []
    for sym, g in d.sort_values("pub").groupby("symbol"):
        last = None
        for r in g.itertuples():
            if last is None or (r.pub - last).days > gap_days:
                start = r.pub
                v = g[(g.pub >= start) & (g.pub <= start + pd.Timedelta(days=value_days))].value.sum()
                out.append({"sym": sym, "date": start.normalize(), "value": v, "txt": getattr(r, "txt", "")})
            last = r.pub
    return pd.DataFrame(out)


def value_band(E):
    pct = E.value / (E.mcap_cr * 1e7)
    return pd.cut(pct, [-1, 0.0005, 0.002, 0.01, 100],
                  labels=["< 0.05% of mcap", "0.05-0.2%", "0.2-1%", "> 1%"])


def insiders(es: EventStudy):
    d = load_pit()
    print(f"{len(d)} insider disclosures", flush=True)
    sets = {
        "promoter market BUY": d[d.promoter & d.acqMode.eq("Market Purchase")],
        "director/KMP market BUY": d[d.insider & d.acqMode.eq("Market Purchase")],
        "promoter market SELL": d[d.promoter & d.acqMode.eq("Market Sale")],
    }
    parts = []
    for name, sub in sets.items():
        ev = first_in_window(sub)
        ev["type"] = name
        parts.append(ev)
        print(f"  {name}: {len(ev)} events", flush=True)
    E = es.run(pd.concat(parts), lag=1)
    E = E[E.period != "pre-2016"]
    E["value band"] = value_band(E)
    E["type x value"] = E["type"] + " / " + E["value band"].astype(str)
    tabs = {"type": es.table(E, "type")}
    show("insider trades by type", tabs["type"])
    b = E[E["type"].eq("promoter market BUY")]
    tabs["promoter buy by value"] = es.table(b, "value band")
    show("promoter market BUY by size of purchase", tabs["promoter buy by value"])
    tabs["promoter buy by size"] = es.table(b, "size")
    show("promoter market BUY by company size", tabs["promoter buy by size"])
    print("\nsaved to", save(E, tabs, "insiders"))


def pledges(es: EventStudy):
    d = load_pit()
    sets = {"pledge created": d[d.promoter & d.tdpTransactionType.eq("Pledge")],
            "pledge released": d[d.promoter & d.tdpTransactionType.eq("Pledge Revoke")],
            "pledge INVOKED (lender took shares)": d[d.tdpTransactionType.eq("Pledge Invoke")]}
    parts = []
    for name, sub in sets.items():
        ev = first_in_window(sub)
        ev["type"] = name
        parts.append(ev)
        print(f"  {name}: {len(ev)} events", flush=True)
    E = es.run(pd.concat(parts), lag=1)
    E = E[E.period != "pre-2016"]
    E["value band"] = value_band(E)
    tabs = {"type": es.table(E, "type")}
    show("pledges by type", tabs["type"])
    tabs["created by value"] = es.table(E[E["type"].eq("pledge created")], "value band")
    show("pledge created, by value pledged", tabs["created by value"])
    print("\nsaved to", save(E, tabs, "pledges"))


def load_ann() -> pd.DataFrame:
    import glob
    import json
    rows = []
    for f in sorted(glob.glob(str(EVENTS / "ann" / "*.json"))):
        rows += json.loads(Path(f).read_text(encoding="utf-8"))
    d = pd.DataFrame(rows)
    d["pub"] = pd.to_datetime(d.an_dt, format="%d-%b-%Y %H:%M:%S", errors="coerce")
    d["cat"] = d["desc"].fillna("").str.strip().str.lower()
    d["txt"] = (d["desc"].fillna("") + " | " + d.attchmntText.fillna("")).str.lower()
    d["value"] = 0.0
    return d[d.pub.notna() & d.symbol.notna()]


# follow-up filings of an issue already announced: these must not start an event
FOLLOW_UP = (r"trading approval|listing approval|in-principle approval|statement of deviation|monitoring agency|"
             r"allotment of|allotted|has allotted|conversion of warrants|utili[sz]ation")

# (name, category regex or None, text regex, words that must NOT appear, quiet days before a new event)
ANN_EVENTS = [
    # exclusions below came from an LLM check of a 20-per-type sample (verify_result.csv): mostly later steps
    ("buyback", None, r"buy[\s-]?back", r"post buy[\s-]?back|extinguish|daily buy[\s-]?back|letter of offer|debenture|"
     r"\bbonds?\b|\bncds?\b|commercial paper|completion|closure|record date|tendered|acceptance|public announcement|"
     r"dispatch|escrow", 180),
    ("bonus issue", None, r"\bbonus\b", r"bonus debenture|record date|allotment of bonus|allotted|credit of|crediting|"
     r"listing|trading approval|ex-date", 180),
    ("stock split", None, r"sub[\s-]?division|split of (?:the )?(?:equity )?shares|stock split",
     r"record date|credit confirmation|credit of|listing|trading approval|ex-date|new isin|corporate action", 180),
    ("demerger", None, r"de[\s-]?merger", r"record date|update on|cost of acquisition|post[\s-]?demerger|allotment|"
     r"listing|trading approval|effective date|nclt|sanction|tribunal|order|credit of|ex-date", 365),
    ("auditor resigns", None, r"resignation of (the )?(statutory |joint statutory )?auditor|auditors?\b.{0,40}resign",
     r"internal auditor|secretarial auditor|cost auditor|subsidiar", 180),
    ("CFO resigns", None, r"resignation of (the )?(chief financial officer|cfo)|(chief financial officer|\bcfo\b).{0,40}resign",
     None, 180),
    ("QIP", None, r"qualified institution(?:al)? placement|\bqip\b", FOLLOW_UP + r"|closure|closing", 180),
    ("preferential issue", None, r"preferential (?:issue|allotment|basis)",
     FOLLOW_UP + r"|esop|esos|withdraw|postal ballot|clarification|scrutini|voting result", 180),
    ("exchange query: price/volume spurt", r"spurt in volume|price movement", r".", None, 90),
    ("credit rating DOWNGRADE", r"credit rating", r"downgrad", None, 180),
    ("credit rating UPGRADE", r"credit rating", r"upgrad", None, 180),
]


# Event types that also appear in NSE corporate actions (with an ex-date). The LLM check showed the text rules
# alone are weak for these (35-58% of event starts right), so an event counts only if a matching corporate
# action followed: event date = first matching announcement 1-150 days before that ex-date.
CA_ANCHOR = {"buyback": r"buy ?back", "bonus issue": r"bonus", "stock split": r"split|sub-division",
             "demerger": r"demerger"}


def load_ca() -> pd.DataFrame:
    import glob
    import json
    rows = []
    for f in glob.glob(str(EVENTS / "ca" / "*.json")):
        rows += json.loads(Path(f).read_text(encoding="utf-8"))
    c = pd.DataFrame(rows)
    c["ex"] = pd.to_datetime(c.exDate, format="%d-%b-%Y", errors="coerce")
    c["subj"] = c.subject.fillna("").str.lower()
    return c.dropna(subset=["ex"])


def anchored(matches: pd.DataFrame, ca: pd.DataFrame, days=150) -> pd.DataFrame:
    out = []
    by_sym = {s: g.sort_values("pub") for s, g in matches.groupby("symbol")}
    for r in ca.drop_duplicates(["symbol", "ex"]).itertuples():
        g = by_sym.get(r.symbol)
        if g is None:
            continue
        w = g[(g.pub < r.ex) & (g.pub >= r.ex - pd.Timedelta(days=days))]
        if len(w):
            first = w.iloc[0]
            out.append({"sym": r.symbol, "date": first.pub.normalize(), "value": 0.0, "txt": first.txt})
    return pd.DataFrame(out).drop_duplicates(["sym", "date"])


def announcements(es: EventStudy):
    import re
    d = load_ann()
    ca = load_ca()
    print(f"{len(d)} announcements {d.pub.min():%Y-%m} .. {d.pub.max():%Y-%m}", flush=True)
    parts, samples = [], []
    for name, cat, txt, neg, gap in ANN_EVENTS:
        m = d.txt.str.contains(txt, regex=True)
        if cat:
            m &= d.cat.str.contains(cat, regex=True)
        if neg:
            m &= ~d.txt.str.contains(neg, regex=True)
        if name in CA_ANCHOR:
            ev = anchored(d[m], ca[ca.subj.str.contains(CA_ANCHOR[name], regex=True)],
                          days=540 if name == "demerger" else 150)   # demergers take 1-1.5 years
        else:
            ev = first_in_window(d[m], gap_days=gap)
        ev["type"] = name
        parts.append(ev)
        # sample of matched announcements for a cheap LLM check of the rule's precision
        # sample of event-STARTING announcements (these set the event dates) for a cheap LLM check
        samples.append(ev.sample(min(20, len(ev)), random_state=1).assign(type=name)[["type", "sym", "date", "txt"]])
        print(f"  {name}: {m.sum()} announcements -> {len(ev)} events", flush=True)
    E = es.run(pd.concat(parts), lag=1)
    E = E[E.period != "pre-2016"]
    tabs = {"type": es.table(E, "type")}
    show("announcement events (buy = close the day after)", tabs["type"])
    E["type x size"] = E["type"] + " / " + E["size"]
    tabs["type x size"] = es.table(E, "type x size", periods=False)
    show("by company size (all years)", tabs["type x size"])
    out = save(E, tabs, "announcements")
    s = pd.concat(samples)
    s["txt"] = s.txt.str.slice(0, 400)
    s.to_csv(out / "verify_sample.csv", index=False)
    print("\nsaved to", out, "(verify_sample.csv = rule check sample)")
    return E


def client_type(name: str) -> str:
    n = (name or "").upper()
    if any(w in n for w in ["MUTUAL FUND", " FUND", "INSURANCE", "PENSION", "ASSURANCE", " TRUST", "FPI",
                            "INVESTMENT MANAGEMENT", "ASSET MANAGEMENT", " PLC", "CAPITAL FUND", "SICAV"]):
        return "fund"
    if any(w in n for w in ["LIMITED", " LTD", "LLP", "PVT", "PRIVATE", "CORPORATION", " INC", "HUF", "SECURITIES",
                            "BROKING", "FINANCE", "VENTURES", "HOLDINGS", "ENTERPRISES", "CAPITAL", "TRADING"]):
        return "company"
    return "individual"


def bulk(es: EventStudy):
    """Bulk deals (>=0.5% of equity in a day). Only clients whose net trade that day is >= 80% of their gross
    (drops intraday traders on both sides). Event = first one-sided deal per stock after 30 quiet days."""
    import glob
    import json
    rows, cut = [], 0
    for f in sorted(glob.glob(str(EVENTS / "bulk" / "*.json"))):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        rows += j["rows"]
        cut += len(j["truncated_days"])
    d = pd.DataFrame(rows)
    print(f"{len(d)} bulk deals, {cut} days cut at 70 rows", flush=True)
    d["day"] = pd.to_datetime(d.BD_DT_DATE, format="%d-%b-%Y", errors="coerce")
    d["q"] = pd.to_numeric(d.BD_QTY_TRD, errors="coerce") * d.BD_BUY_SELL.str.upper().map({"BUY": 1, "SELL": -1})
    g = d.groupby(["BD_SYMBOL", "day", "BD_CLIENT_NAME"]).q.agg(net="sum", gross=lambda x: x.abs().sum()).reset_index()
    g = g[g.net.abs() >= 0.8 * g.gross]
    g["ctype"] = g.BD_CLIENT_NAME.map(client_type)
    g["side"] = np.where(g.net > 0, "BUY", "SELL")
    g["pub"] = g.day + pd.Timedelta(hours=18)          # bulk deals are published after the close
    g = g.rename(columns={"BD_SYMBOL": "symbol"})
    g["value"] = 0.0
    parts = []
    for (side, ct), sub in g.groupby(["side", "ctype"]):
        ev = first_in_window(sub, gap_days=30)
        ev["type"] = f"bulk {side} by {ct}"
        parts.append(ev)
        print(f"  bulk {side} by {ct}: {len(ev)} events", flush=True)
    E = es.run(pd.concat(parts), lag=1)
    E = E[E.period != "pre-2016"]
    tabs = {"type": es.table(E, "type")}
    show("bulk deals (one-sided clients only)", tabs["type"])
    print("\nsaved to", save(E, tabs, "bulk"))


def index_changes(es: EventStudy):
    d = pd.read_csv(EVENTS / "index_changes.csv", parse_dates=["announced", "effective"])
    grp = {"Nifty 50": "Nifty 50 / Next 50 / 100", "Nifty Next 50": "Nifty 50 / Next 50 / 100",
           "Nifty 100": "Nifty 50 / Next 50 / 100", "Nifty 200": "Nifty 200 / 500", "Nifty 500": "Nifty 200 / 500",
           "Nifty Midcap 150": "Midcap", "Nifty Midcap 100": "Midcap", "Nifty Midcap 50": "Midcap",
           "Nifty Smallcap 250": "Smallcap", "Nifty Smallcap 100": "Smallcap", "Nifty Smallcap 50": "Smallcap"}
    d["group"] = d["index"].map(grp)
    d = d.dropna(subset=["group"]).drop_duplicates(["symbol", "announced", "group", "action"])
    print(f"{len(d)} index changes, {d.announced.min():%Y-%m} .. {d.announced.max():%Y-%m}", flush=True)
    a = d.rename(columns={"symbol": "sym", "announced": "date"})[["sym", "date", "group", "action"]].copy()
    a["when"] = "from announcement"
    b = d.dropna(subset=["effective"]).rename(columns={"symbol": "sym", "effective": "date"})[
        ["sym", "date", "group", "action"]].copy()
    b["when"] = "from effective date"
    E = es.run(pd.concat([a, b]), lag=1)
    E = E[E.period != "pre-2016"]
    E["type"] = E.action + " / " + E.group + " / " + E.when
    tabs = {"type": es.table(E, "type", periods=False)}
    show("index inclusion / exclusion (all years)", tabs["type"])
    tabs["action x when"] = es.table(E.assign(k=E.action + " / " + E.when), "k")
    show("by period", tabs["action x when"])
    print("\nsaved to", save(E, tabs, "index"))


TESTS = {"earnings": earnings, "insiders": insiders, "pledges": pledges, "announcements": announcements,
         "bulk": bulk, "index": index_changes}

if __name__ == "__main__":
    es = EventStudy()
    for name in sys.argv[1:]:
        TESTS[name](es)
