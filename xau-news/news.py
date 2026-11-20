#!/usr/bin/env python3
"""xau-news: the economic calendar and headlines that move gold.

  python3 news.py calendar                 # fetch this week, write xau/calendar.json, list what's next
  python3 news.py calendar --all-impacts   # medium and low too
  python3 news.py next                     # upcoming high-impact USD events, local time
  python3 news.py now                      # are we inside a news blackout right now?
  python3 news.py headlines --hours 12     # gold headlines, new since last check

Sources (free, no key, unofficial, so they can change):
  calendar   https://nfs.faireconomy.media/ff_calendar_thisweek.json
             (the Forex Factory weekly calendar feed: title, country, date, impact, forecast, previous)
  headlines  Yahoo Finance headline RSS for gold futures (GC=F) and Google News RSS "gold price"

Standard library only.
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xautime  # noqa: E402

CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FEEDS = {
    "yahoo": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US",
    "google": "https://news.google.com/rss/search?q=gold+price+OR+XAUUSD+when:2d&hl=en-US&gl=US&ceid=US:en",
}
UA = "Mozilla/5.0 (compatible; xauusd-trader/1.0)"

# What each kind of headline usually means for gold, for the brief. Tags only, no predictions.
TAGS = [
    ("fed", r"\b(fed|fomc|powell|rate cut|rate hike|interest rate|dot plot)\b"),
    ("inflation", r"\b(cpi|pce|ppi|inflation)\b"),
    ("jobs", r"\b(nfp|non-?farm|payrolls|jobless|unemployment|jobs report|jolts)\b"),
    ("dollar", r"\b(dollar|dxy|greenback)\b"),
    ("yields", r"\b(yield|treasur(y|ies)|bond)\b"),
    ("geopolitics", r"\b(war|attack|missile|sanction|tariff|conflict|ceasefire|election)\b"),
    ("central banks", r"\b(central bank|pboc|reserve buying|etf (in|out)flows?)\b"),
    ("levels", r"\b(record|all-time high|support|resistance|\$\d[\d,]*)\b"),
]

DEFAULTS = {"news_impacts": ["High"], "news_currencies": ["USD"], "local_utc_offset_hours": 5,
            "news_blackout_before_min": 30, "news_blackout_after_min": 30}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def parse_calendar(raw):
    events = []
    for e in json.loads(raw):
        try:
            t = xautime.parse_when(e["date"]).astimezone(xautime.UTC)
        except (KeyError, ValueError):
            continue
        events.append({"title": e.get("title", "").strip(), "country": e.get("country", ""),
                       "impact": e.get("impact", ""), "time": t.isoformat(),
                       "forecast": e.get("forecast", ""), "previous": e.get("previous", "")})
    events.sort(key=lambda e: e["time"])
    return events


def filter_events(events, cfg, all_impacts=False):
    return [e for e in events if e["country"] in cfg["news_currencies"]
            and (all_impacts or e["impact"] in cfg["news_impacts"])]


def fmt_event(e, off):
    t = xautime.local(xautime.parse_when(e["time"]), off)
    extra = ", ".join(x for x in ("forecast %s" % e["forecast"] if e["forecast"] else "",
                                  "previous %s" % e["previous"] if e["previous"] else "") if x)
    return "%s  %-6s %-4s %s%s" % (t.strftime("%a %d %b %H:%M"), e["impact"], e["country"], e["title"],
                                   "  (%s)" % extra if extra else "")


def blackout(events, cfg, now):
    b = dt.timedelta(minutes=cfg["news_blackout_before_min"])
    a = dt.timedelta(minutes=cfg["news_blackout_after_min"])
    return [e for e in filter_events(events, cfg) if xautime.parse_when(e["time"]) - b <= now <= xautime.parse_when(e["time"]) + a]


def parse_rss(raw, source):
    items = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            t = email.utils.parsedate_to_datetime(pub).astimezone(xautime.UTC) if pub else None
        except (TypeError, ValueError):
            t = None
        tags = [name for name, rx in TAGS if re.search(rx, title, re.I)]
        items.append({"title": title, "link": link, "time": t.isoformat() if t else None,
                      "source": source, "tags": tags})
    return items


def cmd_calendar(a, cfg):
    raw = open(a.file, "rb").read() if a.file else fetch(CAL_URL)
    events = parse_calendar(raw)
    now = xautime.parse_when(a.now) if a.now else xautime.now_utc()
    save(os.path.join(a.dir, "calendar.json"),
         {"fetched": now.isoformat(timespec="seconds"), "source": a.file or CAL_URL, "events": events})
    shown = [e for e in filter_events(events, cfg, a.all_impacts) if xautime.parse_when(e["time"]) >= now - dt.timedelta(hours=1)]
    print("Calendar saved (%d events this week). %s %s events from now, your time (UTC%+d):"
          % (len(events), "/".join(cfg["news_currencies"]), "all" if a.all_impacts else "/".join(cfg["news_impacts"]),
             cfg["local_utc_offset_hours"]))
    for e in shown:
        print("  " + fmt_event(e, cfg["local_utc_offset_hours"]))
    if not shown:
        print("  none left this week")
    return 0


def cmd_next(a, cfg):
    cal = load(os.path.join(a.dir, "calendar.json"))
    if not cal:
        print("No xau/calendar.json yet. Run: news.py calendar", file=sys.stderr)
        return 2
    now = xautime.parse_when(a.now) if a.now else xautime.now_utc()
    up = [e for e in filter_events(cal["events"], cfg) if xautime.parse_when(e["time"]) >= now][: a.limit]
    for e in up:
        mins = int((xautime.parse_when(e["time"]) - now).total_seconds() // 60)
        print("  %s   in %dh%02dm" % (fmt_event(e, cfg["local_utc_offset_hours"]), mins // 60, mins % 60))
    if not up:
        print("No more high-impact events in the saved week. Refresh after the weekend.")
    return 0


def cmd_now(a, cfg):
    cal = load(os.path.join(a.dir, "calendar.json"))
    if not cal:
        print("No xau/calendar.json yet. Run: news.py calendar", file=sys.stderr)
        return 2
    now = xautime.parse_when(a.now) if a.now else xautime.now_utc()
    hits = blackout(cal["events"], cfg, now)
    if hits:
        print("NEWS BLACKOUT. Do not open trades:")
        for e in hits:
            print("  " + fmt_event(e, cfg["local_utc_offset_hours"]))
        return 0
    print("Clear: no %s high-impact event within %d min before / %d min after now."
          % ("/".join(cfg["news_currencies"]), cfg["news_blackout_before_min"], cfg["news_blackout_after_min"]))
    return 1


def cmd_headlines(a, cfg):
    state_path = os.path.join(a.dir, "state", "news.json")
    state = load(state_path, {"seen": {}})
    now = xautime.parse_when(a.now) if a.now else xautime.now_utc()
    items = []
    for name in a.sources:
        try:
            raw = open(a.file, "rb").read() if a.file else fetch(FEEDS[name])
            items += parse_rss(raw, name)
        except Exception as e:  # one feed down should not stop the other
            print("(%s feed failed: %s)" % (name, e), file=sys.stderr)
    cutoff = now - dt.timedelta(hours=a.hours)
    seen = state["seen"]
    fresh, dup_titles = [], set()
    for it in sorted(items, key=lambda i: i["time"] or "", reverse=True):
        key = re.sub(r"\W+", " ", it["title"].lower()).strip()[:90]
        if key in dup_titles or (it["time"] and xautime.parse_when(it["time"]) < cutoff):
            continue
        if key in seen and not a.all:
            continue
        dup_titles.add(key)
        fresh.append(it)
    for it in fresh:
        t = xautime.local(xautime.parse_when(it["time"]), cfg["local_utc_offset_hours"]).strftime("%d %b %H:%M") if it["time"] else "     ?     "
        print("%s  [%s] %s%s\n      %s" % (t, it["source"], it["title"],
                                         "  #" + " #".join(it["tags"]) if it["tags"] else "", it["link"]))
    if not fresh:
        print("Nothing new on gold in the last %d hours." % a.hours)
    if not a.dry_run:
        for it in fresh:
            seen[re.sub(r"\W+", " ", it["title"].lower()).strip()[:90]] = now.isoformat(timespec="seconds")
        keep = now - dt.timedelta(days=14)
        state["seen"] = {k: v for k, v in seen.items() if xautime.parse_when(v) >= keep}
        save(state_path, state)
    return 0 if fresh else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="xau")
    ap.add_argument("--now", help="ISO time for testing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calendar")
    c.add_argument("--file", help="read a saved feed instead of downloading")
    c.add_argument("--all-impacts", action="store_true")
    n = sub.add_parser("next")
    n.add_argument("--limit", type=int, default=8)
    sub.add_parser("now")
    h = sub.add_parser("headlines")
    h.add_argument("--hours", type=int, default=24)
    h.add_argument("--sources", nargs="+", default=["yahoo", "google"], choices=list(FEEDS))
    h.add_argument("--file", help="read a saved RSS file instead of downloading")
    h.add_argument("--all", action="store_true", help="include items already shown")
    h.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cfg = dict(DEFAULTS)
    cfg.update(load(os.path.join(a.dir, "config.json"), {}))
    try:
        return {"calendar": cmd_calendar, "next": cmd_next, "now": cmd_now, "headlines": cmd_headlines}[a.cmd](a, cfg)
    except OSError as e:
        print("ERROR: could not reach the source (%s). Check the calendar on forexfactory.com by hand." % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
