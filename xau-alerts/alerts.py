#!/usr/bin/env python3
"""xau-alerts: gold session clock and price-level alerts.

  python3 alerts.py clock                        # open/closed, sessions now, next session changes, local time
  python3 alerts.py quote                        # delayed gold price (spot from Stooq, else futures from Yahoo)
  python3 alerts.py add --above 4100 --note "breakout"
  python3 alerts.py add --below 4020
  python3 alerts.py add --pct 1.5                # move of 1.5% from yesterday's close
  python3 alerts.py add --session london         # ring when the London session opens
  python3 alerts.py check [--price 4087.5]       # exit 0 = something rang
  python3 alerts.py list | reset ID | remove ID

Free quotes are delayed and differ from your broker by the spread, and futures
(GC=F) trade a few dollars above spot. For entries and stops, MT5's own price
is the only one that counts. Use these for "come look at the chart" alerts.
Standard library only.
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xautime  # noqa: E402

UA = "Mozilla/5.0 (compatible; xauusd-trader/1.0)"
STOOQ = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=csv"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range=2d&interval=1d"


def load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def parse_stooq(text):
    row = next(csv.DictReader(io.StringIO(text)))
    if not row.get("Close") or row["Close"] in ("N/D", ""):
        raise ValueError("Stooq returned no price")
    return {"price": float(row["Close"]), "open": float(row["Open"]), "source": "stooq spot XAUUSD",
            "as_of": "%sT%s" % (row["Date"], row["Time"]), "prev_close": None}


def parse_yahoo(text):
    meta = json.loads(text)["chart"]["result"][0]["meta"]
    return {"price": float(meta["regularMarketPrice"]), "prev_close": meta.get("chartPreviousClose"),
            "source": "yahoo GC=F futures (runs above spot)",
            "as_of": dt.datetime.fromtimestamp(meta["regularMarketTime"], xautime.UTC).isoformat()}


def quote(source="auto"):
    errors = []
    for name in (["stooq", "yahoo"] if source == "auto" else [source]):
        try:
            return (parse_stooq if name == "stooq" else parse_yahoo)(fetch(STOOQ if name == "stooq" else YAHOO))
        except Exception as e:
            errors.append("%s: %s" % (name, e))
    raise RuntimeError("; ".join(errors))


def cmd_clock(a, cfg):
    now = xautime.parse_when(a.now) if a.now else xautime.now_utc()
    off = cfg.get("local_utc_offset_hours", 5)
    is_open, why = xautime.market_open(now)
    print("Now %s (your time, UTC%+d) = %s New York" % (
        xautime.local(now, off).strftime("%a %d %b %H:%M"), off,
        xautime.city_time(now, "newyork").strftime("%a %H:%M")))
    print("Gold: %s" % ("OPEN" if is_open else "CLOSED, " + why))
    if not is_open:
        nxt = xautime.next_open(now)
        print("Reopens %s your time" % xautime.local(nxt, off).strftime("%a %d %b %H:%M"))
    sess = xautime.sessions_now(now)
    print("Sessions: %s%s" % (", ".join(sess) or "none of the main three",
                              "  (London/New York overlap: usually the busiest gold hours)" if {"london", "newyork"} <= set(sess) else ""))
    # next 24h of session opens/closes, in local time
    print("Next 24 hours, your time:")
    prev = set(sess)
    t = now.replace(second=0, microsecond=0)
    for _ in range(24 * 60):
        t += dt.timedelta(minutes=1)
        cur = set(xautime.sessions_now(t))
        for s in sorted(cur - prev):
            print("  %s  %s opens" % (xautime.local(t, off).strftime("%a %H:%M"), s))
        for s in sorted(prev - cur):
            print("  %s  %s closes" % (xautime.local(t, off).strftime("%a %H:%M"), s))
        prev = cur
    return 0 if is_open else 1


def cmd_quote(a, cfg):
    q = {"price": a.price, "source": "given", "as_of": xautime.now_utc().isoformat(timespec="seconds"),
         "prev_close": None} if a.price else quote(a.source)
    print("XAUUSD %.2f  (%s, as of %s)" % (q["price"], q["source"], q["as_of"]))
    if a.write:
        save(os.path.join(a.dir, "prices.json"), q)
    return 0


def cmd_add(a, cfg):
    path = os.path.join(a.dir, "alerts.json")
    rules = load(path, {"rules": []})
    if a.above is not None:
        r = {"id": "above-%g" % a.above, "type": "above", "price": a.above}
    elif a.below is not None:
        r = {"id": "below-%g" % a.below, "type": "below", "price": a.below}
    elif a.pct is not None:
        r = {"id": "move-%g" % a.pct, "type": "pct_move", "pct": a.pct}
    elif a.session:
        r = {"id": "session-%s" % a.session, "type": "session", "session": a.session}
    else:
        print("Give one of --above, --below, --pct, --session", file=sys.stderr)
        return 2
    r["note"] = a.note or ""
    r["rearm"] = a.rearm
    rules["rules"] = [x for x in rules["rules"] if x["id"] != r["id"]] + [r]
    save(path, rules)
    print("Added %s %s" % (r["id"], "(%s)" % r["note"] if r["note"] else ""))
    return 0


def cmd_list(a, cfg):
    rules = load(os.path.join(a.dir, "alerts.json"), {"rules": []})["rules"]
    st = load(os.path.join(a.dir, "state", "alerts.json"), {"rang": {}})["rang"]
    for r in rules:
        print("  %-18s %-9s %s" % (r["id"], "rang" if r["id"] in st else "armed", r.get("note", "")))
    if not rules:
        print("No alerts. Add one with: alerts.py add --above PRICE")
    return 0


def evaluate(rules, rang, q, now, off):
    out = []
    day = xautime.local(now, off).date().isoformat()
    for r in rules:
        rid, typ = r["id"], r["type"]
        last = rang.get(rid)
        if typ in ("above", "below") and q:
            hit = q["price"] >= r["price"] if typ == "above" else q["price"] <= r["price"]
            if hit and not last:
                out.append((rid, "gold %.2f is %s %.2f %s" % (q["price"], typ, r["price"], r.get("note", ""))))
                rang[rid] = now.isoformat(timespec="seconds")
            elif not hit and last and r.get("rearm"):
                del rang[rid]
        elif typ == "pct_move" and q and q.get("prev_close"):
            move = 100 * (q["price"] - q["prev_close"]) / q["prev_close"]
            if abs(move) >= r["pct"] and (not last or not last.startswith(day)):
                out.append((rid, "gold moved %+.2f%% from %.2f to %.2f" % (move, q["prev_close"], q["price"])))
                rang[rid] = now.isoformat(timespec="seconds")
        elif typ == "session":
            if r["session"] in xautime.sessions_now(now) and (not last or not last.startswith(day)):
                out.append((rid, "%s session is open %s" % (r["session"], r.get("note", ""))))
                rang[rid] = now.isoformat(timespec="seconds")
    return out


def cmd_check(a, cfg):
    rules = load(os.path.join(a.dir, "alerts.json"), {"rules": []})["rules"]
    st_path = os.path.join(a.dir, "state", "alerts.json")
    st = load(st_path, {"rang": {}})
    now = xautime.parse_when(a.now) if a.now else xautime.now_utc()
    q = None
    if any(r["type"] in ("above", "below", "pct_move") for r in rules):
        if a.price is not None:
            q = {"price": a.price, "prev_close": a.prev_close, "source": "given"}
        else:
            try:
                q = quote(a.source)
            except RuntimeError as e:
                print("No quote (%s). Pass --price from MT5." % e, file=sys.stderr)
    rang = evaluate(rules, st["rang"], q, now, cfg.get("local_utc_offset_hours", 5))
    for rid, msg in rang:
        print("ALERT %s: %s" % (rid, msg))
    if not rang:
        print("Nothing hit%s." % (" (gold %.2f, %s)" % (q["price"], q["source"]) if q else ""))
    save(st_path, st)
    return 0 if rang else 1


def cmd_reset(a, cfg, remove=False):
    st_path = os.path.join(a.dir, "state", "alerts.json")
    st = load(st_path, {"rang": {}})
    st["rang"].pop(a.id, None)
    save(st_path, st)
    if remove:
        path = os.path.join(a.dir, "alerts.json")
        rules = load(path, {"rules": []})
        rules["rules"] = [r for r in rules["rules"] if r["id"] != a.id]
        save(path, rules)
    print("%s %s" % ("Removed" if remove else "Re-armed", a.id))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="xau")
    ap.add_argument("--now")
    ap.add_argument("--source", default="auto", choices=["auto", "stooq", "yahoo"])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("clock")
    q = sub.add_parser("quote")
    q.add_argument("--price", type=float)
    q.add_argument("--write", action="store_true")
    ad = sub.add_parser("add")
    ad.add_argument("--above", type=float)
    ad.add_argument("--below", type=float)
    ad.add_argument("--pct", type=float)
    ad.add_argument("--session", choices=list(xautime.SESSIONS))
    ad.add_argument("--note")
    ad.add_argument("--rearm", action="store_true")
    sub.add_parser("list")
    c = sub.add_parser("check")
    c.add_argument("--price", type=float)
    c.add_argument("--prev-close", type=float)
    for name in ("reset", "remove"):
        p = sub.add_parser(name)
        p.add_argument("id")
    a = ap.parse_args(argv)
    cfg = load(os.path.join(a.dir, "config.json"), {})
    if a.cmd == "reset":
        return cmd_reset(a, cfg)
    if a.cmd == "remove":
        return cmd_reset(a, cfg, remove=True)
    try:
        return {"clock": cmd_clock, "quote": cmd_quote, "add": cmd_add, "list": cmd_list, "check": cmd_check}[a.cmd](a, cfg)
    except RuntimeError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
