"""Offline tests: python3 -m unittest discover -s tests -v"""
import datetime as dt
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")


def load(skill, name):
    sys.path.insert(0, os.path.join(ROOT, skill))
    spec = importlib.util.spec_from_file_location("%s_%s" % (skill, name), os.path.join(ROOT, skill, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


size = load("xau-size", "size")
risk = load("xau-risk", "check")
news = load("xau-news", "news")
ticket = load("xau-ticket", "ticket")
alerts = load("xau-alerts", "alerts")
xt = load("xau-alerts", "xautime")
CFG = dict(size.DEFAULTS, balance=500, risk_per_trade_pct=1.0)
RCFG = dict(risk.LIMITS, balance=500)
T = xt.parse_when


class Clock(unittest.TestCase):
    def test_dst(self):
        self.assertEqual(xt.ny_offset(T("2026-07-01T12:00")), -4)
        self.assertEqual(xt.ny_offset(T("2026-11-20T12:00")), -5)
        self.assertEqual(xt.london_offset(T("2026-07-01T12:00")), 1)
        self.assertEqual(xt.london_offset(T("2026-11-20T12:00")), 0)

    def test_market_hours(self):
        self.assertTrue(xt.market_open(T("2026-11-20T14:00"))[0])
        self.assertFalse(xt.market_open(T("2026-11-21T10:00"))[0])       # Saturday
        self.assertFalse(xt.market_open(T("2026-11-23T22:30"))[0])       # 17:30 NY daily break
        self.assertTrue(xt.market_open(T("2026-11-22T23:30"))[0])        # Sunday 18:30 NY
        self.assertEqual(xt.next_open(T("2026-11-21T10:00")), T("2026-11-22T23:00"))

    def test_sessions(self):
        self.assertEqual(xt.sessions_now(T("2026-11-20T14:00")), ["london", "newyork"])
        self.assertEqual(xt.sessions_now(T("2026-11-20T02:00")), ["asia"])


class Size(unittest.TestCase):
    def test_lots_round_down(self):
        t = size.size(CFG, "buy", 4000, 3998, rr=2, balance=1000)  # $10 risk, $200/lot
        self.assertEqual(t["lots"], 0.05)
        self.assertEqual(t["tp"], 4004)
        self.assertEqual(t["risk_usd"], 10.0)

    def test_spread_counts(self):
        t = size.size(CFG, "sell", 4000, 4002, spread=0.5, balance=1000)  # $250/lot -> 0.04
        self.assertEqual(t["lots"], 0.04)

    def test_min_lot_too_big(self):
        t = size.size(CFG, "buy", 4000, 3990, balance=500)
        self.assertFalse(t["ok"])
        self.assertEqual(t["lots"], 0)

    def test_wrong_side(self):
        with self.assertRaises(ValueError):
            size.size(CFG, "buy", 4000, 4005, balance=500)


def trade(**kw):
    t = {"symbol": "XAUUSD", "side": "sell", "type": "market", "entry": 4050.4, "sl": 4052.9,
         "tp": 4045.4, "lots": 0.01, "spread": 0.25, "balance": 500}
    t.update(kw)
    return t


CAL = {"fetched": "2026-11-20T13:00:00+00:00",
       "events": news.parse_calendar(open(os.path.join(FIX, "ff_calendar_thisweek.json"), "rb").read())}
NOW = T("2026-11-20T13:30")


def blocks(res):
    return [r[1] for r in res if r[0] == "BLOCK"]


class Risk(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(blocks(risk.check(trade(), RCFG, {}, CAL, NOW)), [])

    def test_news_blackout(self):
        self.assertIn("news", blocks(risk.check(trade(), RCFG, {}, CAL, T("2026-11-20T14:30"))))

    def test_rules(self):
        self.assertIn("stop-loss", blocks(risk.check(trade(sl=None), RCFG, {}, CAL, NOW)))
        self.assertIn("reward:risk", blocks(risk.check(trade(tp=4049.4), RCFG, {}, CAL, NOW)))
        self.assertIn("reward:risk", blocks(risk.check(trade(tp=None), RCFG, {}, CAL, NOW)))
        self.assertIn("spread", blocks(risk.check(trade(), RCFG, {}, CAL, NOW, spread=0.9)))
        self.assertIn("risk", blocks(risk.check(trade(lots=0.03), RCFG, {}, CAL, NOW)))
        self.assertIn("market hours", blocks(risk.check(trade(), RCFG, {}, CAL, T("2026-11-21T10:00"))))
        self.assertIn("session", blocks(risk.check(trade(), RCFG, {}, CAL, T("2026-11-20T02:00"))))
        self.assertIn("stop distance", blocks(risk.check(trade(sl=4050.9, tp=4049.4), RCFG, {}, CAL, NOW)))

    def test_day_limits(self):
        def closed(i, pnl, when):
            return {"id": i, "status": "closed", "placed_at": when, "closed_at": when, "pnl_usd": pnl}
        j = {"trades": [closed(1, -5, "2026-11-20T09:00:00+00:00"), closed(2, -5, "2026-11-20T10:00:00+00:00")]}
        b = blocks(risk.check(trade(), RCFG, j, CAL, NOW))
        self.assertIn("loss streak", b)
        j = {"trades": [closed(1, -14, "2026-11-20T09:00:00+00:00")]}
        self.assertIn("daily loss", blocks(risk.check(trade(), RCFG, j, CAL, NOW)))
        # yesterday's losses do not count today
        j = {"trades": [closed(1, -14, "2026-11-18T09:00:00+00:00")]}
        self.assertEqual(blocks(risk.check(trade(), RCFG, j, CAL, NOW)), [])


class News(unittest.TestCase):
    def test_calendar(self):
        ev = news.filter_events(CAL["events"], news.DEFAULTS)
        self.assertEqual([e["title"] for e in ev], ["Unemployment Claims", "Flash Manufacturing PMI"])
        self.assertEqual(ev[1]["time"], "2026-11-20T14:45:00+00:00")

    def test_rss(self):
        items = news.parse_rss(open(os.path.join(FIX, "gold_rss.xml"), "rb").read(), "yahoo")
        self.assertEqual(len(items), 4)
        self.assertIn("fed", items[0]["tags"])
        self.assertIn("dollar", items[0]["tags"])


class Ticket(unittest.TestCase):
    def test_yes(self):
        t = trade()
        self.assertTrue(ticket.is_explicit_yes("yes", t))
        self.assertTrue(ticket.is_explicit_yes("Yes, sell 0.01", t))
        self.assertFalse(ticket.is_explicit_yes("yes to all", t))
        self.assertFalse(ticket.is_explicit_yes("yes buy", t))
        self.assertFalse(ticket.is_explicit_yes("yes 0.05", t))
        self.assertFalse(ticket.is_explicit_yes("sure", t))
        self.assertFalse(ticket.is_explicit_yes("ok", t))

    def test_fingerprint_matches_risk(self):
        self.assertEqual(ticket.fingerprint(trade()), risk.fingerprint(trade()))
        self.assertNotEqual(ticket.fingerprint(trade()), ticket.fingerprint(trade(lots=0.02)))

    def test_flow(self):
        with tempfile.TemporaryDirectory() as d:
            json.dump(trade(), open(os.path.join(d, "trade.json"), "w"))
            os.makedirs(os.path.join(d, "state"))
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            json.dump({"verdict": "PASS", "fingerprint": risk.fingerprint(trade()), "checked_at": now},
                      open(os.path.join(d, "state", "risk.json"), "w"))
            self.assertEqual(ticket.main(["--dir", d, "approve", "--reply", "yes"]), 0)
            ticket.main(["--dir", d, "placed", "--fill", "4050.4"])
            ticket.main(["--dir", d, "close", "--exit", "4045.4"])
            tr = json.load(open(os.path.join(d, "journal.json")))["trades"][0]
            self.assertEqual(tr["pnl_usd"], 5.0)
            self.assertEqual(tr["r_multiple"], 2.0)


class Alerts(unittest.TestCase):
    def test_rings_once(self):
        rules = [{"id": "above-4100", "type": "above", "price": 4100}]
        rang = {}
        self.assertEqual(len(alerts.evaluate(rules, rang, {"price": 4101}, NOW, 5)), 1)
        self.assertEqual(len(alerts.evaluate(rules, rang, {"price": 4102}, NOW, 5)), 0)

    def test_parsers(self):
        q = alerts.parse_stooq("Symbol,Date,Time,Open,High,Low,Close,Volume\nXAUUSD,2026-11-20,14:00:00,4040.1,4060.2,4031.0,4050.4,0\n")
        self.assertEqual(q["price"], 4050.4)
        y = json.dumps({"chart": {"result": [{"meta": {"regularMarketPrice": 4061.2, "chartPreviousClose": 4040.0,
                                                       "regularMarketTime": 1795010000}}]}})
        self.assertEqual(alerts.parse_yahoo(y)["prev_close"], 4040.0)


class Repo(unittest.TestCase):
    def test_every_skill_has_frontmatter(self):
        for s in ("xau-size", "xau-risk", "xau-ticket", "xau-alerts", "xau-news"):
            text = open(os.path.join(ROOT, s, "SKILL.md")).read()
            self.assertTrue(text.startswith("---\nname: %s\n" % s), s)
            self.assertIn("description:", text.split("---")[1])


if __name__ == "__main__":
    unittest.main()
