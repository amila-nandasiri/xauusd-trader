#!/usr/bin/env python3
"""xau-risk: PASS or BLOCK one proposed XAUUSD trade against your rules.

  python3 check.py                       # xau/trade.json + xau/config.json
  python3 check.py --spread 0.32 --now 2026-11-20T13:25
  python3 check.py --no-write --json

Reads   xau/trade.json        the proposal from xau-size
        xau/config.json       your limits
        xau/journal.json      today's trades and results (xau-ticket writes it)
        xau/calendar.json     high-impact news events (xau-news writes it)
Writes  xau/state/risk.json   the verdict + a fingerprint of the exact trade

Exit 0 = PASS, 1 = BLOCK, 2 = error. Never places or edits anything.
Standard library only.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xautime  # noqa: E402

LIMITS = {
    "paper": True,
    "balance": None,
    "contract_size": 100,
    "min_lot": 0.01,
    "lot_step": 0.01,
    "max_lot": 1.0,
    "leverage": 500,
    "risk_per_trade_pct": 1.0,
    "max_risk_per_trade_pct": 1.0,
    "max_daily_loss_pct": 3.0,
    "max_trades_per_day": 3,
    "max_open_positions": 1,
    "max_consecutive_losses": 2,
    "min_rr": 1.5,
    "min_sl_usd": 1.0,
    "max_sl_usd": 15.0,
    "max_spread_usd": 0.50,
    "max_margin_pct": 30,
    "allowed_sessions": ["london", "newyork"],
    "session_rule": "block",
    "news_impacts": ["High"],
    "news_currencies": ["USD"],
    "news_blackout_before_min": 30,
    "news_blackout_after_min": 30,
    "calendar_max_age_hours": 24,
    "local_utc_offset_hours": 5,
    "day_starts": "broker",
}


def load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def fingerprint(t):
    keys = ("symbol", "side", "type", "entry", "sl", "tp", "lots")
    s = json.dumps({k: t.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def trading_day(t, cfg):
    """The trading day an instant belongs to. 'broker': rolls at 17:00 New York
    (the gold daily break, MT5 server midnight at most brokers); 'local': your clock."""
    if cfg.get("day_starts") == "local":
        return xautime.local(t, cfg["local_utc_offset_hours"]).date()
    ny = xautime.city_time(t, "newyork")
    return (ny + dt.timedelta(hours=7)).date()


def today_stats(journal, now, cfg):
    day = trading_day(now, cfg)
    trades = journal.get("trades", []) if journal else []
    todays, realised, open_n = [], 0.0, 0
    for tr in trades:
        if tr.get("status") not in ("placed", "closed"):
            continue
        if tr.get("status") == "placed":
            open_n += 1
        when = tr.get("placed_at")
        if when and trading_day(xautime.parse_when(when), cfg) == day:
            todays.append(tr)
            if tr.get("status") == "closed":
                realised += float(tr.get("pnl_usd") or 0)
    closed = [tr for tr in trades if tr.get("status") == "closed"]
    closed.sort(key=lambda tr: tr.get("closed_at") or "")
    streak = 0
    for tr in reversed(closed):
        if float(tr.get("pnl_usd") or 0) < 0:
            streak += 1
        else:
            break
    streak_today = streak and closed and trading_day(xautime.parse_when(closed[-1]["closed_at"]), cfg) == day
    return {"day": day.isoformat(), "count": len(todays), "realised": realised,
            "open": open_n, "loss_streak": streak, "streak_today": bool(streak_today)}


def news_hits(calendar, now, cfg):
    hits = []
    if not calendar:
        return hits
    before = dt.timedelta(minutes=cfg["news_blackout_before_min"])
    after = dt.timedelta(minutes=cfg["news_blackout_after_min"])
    for ev in calendar.get("events", []):
        if ev.get("impact") not in cfg["news_impacts"] or ev.get("country") not in cfg["news_currencies"]:
            continue
        try:
            t = xautime.parse_when(ev["time"])
        except (KeyError, ValueError):
            continue
        if t - before <= now <= t + after:
            hits.append((t, ev))
    return hits


def check(trade, cfg, journal=None, calendar=None, now=None, spread=None):
    now = now or xautime.now_utc()
    res = []  # (level, rule, message)

    def block(rule, msg):
        res.append(("BLOCK", rule, msg))

    def warn(rule, msg):
        res.append(("WARN", rule, msg))

    side = trade.get("side")
    sign = 1 if side == "buy" else -1
    entry, sl, tp, lots = trade.get("entry"), trade.get("sl"), trade.get("tp"), trade.get("lots")
    balance = float(cfg.get("balance") or trade.get("balance") or 0)

    # format
    if side not in ("buy", "sell"):
        block("format", "side must be buy or sell")
    if trade.get("type") not in ("market", "limit", "stop"):
        block("format", "type must be market, limit or stop")
    if not entry or not lots:
        block("format", "entry and lots are required")
    if not sl:
        block("stop-loss", "no stop-loss. Every gold trade needs one")
    if balance <= 0:
        block("format", "no account balance in xau/config.json")
    if any(r[0] == "BLOCK" for r in res):
        return res
    if trade.get("symbol", "XAUUSD").upper().rstrip(".+-") not in ("XAUUSD", "GOLD"):
        block("symbol", "this pack is for XAUUSD only")
    if (entry - sl) * sign <= 0:
        block("stop-loss", "stop-loss on the wrong side of the entry")
        return res
    if tp is not None and (tp - entry) * sign <= 0:
        block("take-profit", "take-profit on the wrong side of the entry")

    # lot rules
    step = cfg["lot_step"]
    if lots < cfg["min_lot"] - 1e-9 or lots > cfg["max_lot"] + 1e-9:
        block("lots", "%.2f lot is outside %.2f-%.2f" % (lots, cfg["min_lot"], cfg["max_lot"]))
    if abs(round(lots / step) * step - lots) > 1e-6:
        block("lots", "%.4f lot is not a multiple of the %.2f step" % (lots, step))

    # stop distance
    dist = abs(entry - sl)
    if dist < cfg["min_sl_usd"]:
        block("stop distance", "stop only $%.2f away, under your $%.2f minimum (noise will take it)" % (dist, cfg["min_sl_usd"]))
    if dist > cfg["max_sl_usd"]:
        block("stop distance", "stop $%.2f away, over your $%.2f maximum" % (dist, cfg["max_sl_usd"]))

    # risk per trade
    sp = float(spread if spread is not None else trade.get("spread") or 0)
    risk = lots * (dist + sp) * cfg["contract_size"]
    risk_pct = 100 * risk / balance
    if risk_pct > cfg["max_risk_per_trade_pct"] + 1e-9:
        block("risk", "risks $%.2f = %.2f%% of $%.2f, over your %.2f%% limit"
              % (risk, risk_pct, balance, cfg["max_risk_per_trade_pct"]))

    # reward:risk
    if tp is None:
        if cfg["min_rr"]:
            block("reward:risk", "no take-profit, so reward:risk cannot be checked (min 1:%.2f)" % cfg["min_rr"])
    else:
        rr = abs(tp - entry) / dist
        if rr + 1e-9 < cfg["min_rr"]:
            block("reward:risk", "1:%.2f is under your 1:%.2f minimum" % (rr, cfg["min_rr"]))

    # spread
    if spread is None and not trade.get("spread"):
        warn("spread", "spread not given; read it off MT5 and pass --spread (25 points = 0.25)")
    elif sp > cfg["max_spread_usd"]:
        block("spread", "spread $%.2f is over your $%.2f maximum (often a sign of news or thin hours)" % (sp, cfg["max_spread_usd"]))

    # margin
    margin = lots * cfg["contract_size"] * entry / cfg["leverage"]
    if 100 * margin / balance > cfg["max_margin_pct"]:
        block("margin", "needs about $%.2f margin = %.0f%% of balance, over %d%%"
              % (margin, 100 * margin / balance, cfg["max_margin_pct"]))

    # day limits
    st = today_stats(journal or {}, now, cfg)
    if st["count"] >= cfg["max_trades_per_day"]:
        block("daily trades", "%d trades already today, your limit is %d" % (st["count"], cfg["max_trades_per_day"]))
    if st["open"] >= cfg["max_open_positions"]:
        block("open positions", "%d already open, your limit is %d" % (st["open"], cfg["max_open_positions"]))
    max_loss = balance * cfg["max_daily_loss_pct"] / 100
    lost = -min(st["realised"], 0)
    if lost >= max_loss:
        block("daily loss", "down $%.2f today, at your $%.2f daily stop. Done for today" % (lost, max_loss))
    elif lost + risk > max_loss + 1e-9:
        block("daily loss", "down $%.2f today; losing this $%.2f would pass your $%.2f daily stop" % (lost, risk, max_loss))
    if cfg["max_consecutive_losses"] and st["loss_streak"] >= cfg["max_consecutive_losses"] and st["streak_today"]:
        block("loss streak", "%d losses in a row. Stop for today (tilt rule)" % st["loss_streak"])

    # market hours and session (limit/stop orders may be set while closed)
    is_open, why = xautime.market_open(now)
    if not is_open and trade.get("type") == "market":
        block("market hours", "gold is closed: %s" % why)
    sess = xautime.sessions_now(now)
    allowed = cfg.get("allowed_sessions") or []
    if allowed and trade.get("type") == "market" and not set(sess) & set(allowed):
        msg = "now in %s; your rules allow %s" % (", ".join(sess) or "no main session", ", ".join(allowed))
        (block if cfg.get("session_rule") == "block" else warn)("session", msg)

    # news blackout
    if calendar is None:
        warn("news", "no xau/calendar.json; run /xau-news first so news blackouts can be checked")
    else:
        age = now - xautime.parse_when(calendar.get("fetched", "1970-01-01T00:00:00"))
        if age > dt.timedelta(hours=cfg["calendar_max_age_hours"]):
            warn("news", "calendar is %.0f hours old; refresh it with /xau-news" % (age.total_seconds() / 3600))
        for t, ev in news_hits(calendar, now, cfg):
            lt = xautime.local(t, cfg["local_utc_offset_hours"])
            block("news", "%s %s at %s local (%s): inside your %d/%d min blackout"
                  % (ev.get("country"), ev.get("title"), lt.strftime("%H:%M"), ev.get("impact"),
                     cfg["news_blackout_before_min"], cfg["news_blackout_after_min"]))

    if not cfg.get("paper", True):
        warn("account", "LIVE account: real money")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="xau")
    ap.add_argument("--trade")
    ap.add_argument("--spread", type=float, help="spread right now, in $")
    ap.add_argument("--now", help="ISO time, UTC unless it has an offset (for testing)")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = dict(LIMITS)
    cfg.update(load(os.path.join(a.dir, "config.json"), {}))
    trade = load(a.trade or os.path.join(a.dir, "trade.json"))
    if not trade:
        print("ERROR: no trade. Run /xau-size with --write first.", file=sys.stderr)
        return 2
    now = xautime.parse_when(a.now) if a.now else xautime.now_utc()
    res = check(trade, cfg, load(os.path.join(a.dir, "journal.json")),
                load(os.path.join(a.dir, "calendar.json")), now, a.spread)
    verdict = "BLOCK" if any(r[0] == "BLOCK" for r in res) else "PASS"
    out = {"verdict": verdict, "fingerprint": fingerprint(trade), "checked_at": now.isoformat(timespec="seconds"),
           "trading_day": trading_day(now, cfg).isoformat(),
           "results": [{"level": l, "rule": r, "message": m} for l, r, m in res]}
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print("%s  %s %.2f lot %s @ %.2f  SL %.2f  TP %s" % (
            verdict, trade["side"].upper(), trade.get("lots") or 0, trade.get("symbol", "XAUUSD"),
            trade.get("entry") or 0, trade.get("sl") or 0, trade.get("tp")))
        for l, r, m in res:
            print("  %-5s %-15s %s" % (l, r, m))
        if not res:
            print("  every rule passed")
    if not a.no_write:
        os.makedirs(os.path.join(a.dir, "state"), exist_ok=True)
        with open(os.path.join(a.dir, "state", "risk.json"), "w") as f:
            json.dump(out, f, indent=2)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
