#!/usr/bin/env python3
"""xau-ticket: the MT5 order ticket for a checked trade, your yes, and the journal.

There is no official MT5 connector, so nothing here (and nothing Claude does)
places an order. You place it yourself in MetaTrader 5. This tool:

  python3 ticket.py show                                   # the MT5 ticket, READY or not
  python3 ticket.py approve --reply "yes"                  # records your yes, word for word
  python3 ticket.py placed --mt5 123456789 --fill 4051.35  # after you placed it in MT5
  python3 ticket.py close --id 3 --exit 4061.35 [--pnl 9.62]   # --pnl = MT5's profit incl. commission/swap
  python3 ticket.py cancel --id 3 --note "price ran away"
  python3 ticket.py journal [--days 30]                    # trades, win rate, average R, P&L
  python3 ticket.py stats --by setup

Reads xau/trade.json, xau/state/risk.json, xau/config.json. Writes xau/journal.json.
Standard library only.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys


def load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fingerprint(t):
    keys = ("symbol", "side", "type", "entry", "sl", "tp", "lots")
    s = json.dumps({k: t.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def readiness(trade, risk):
    if not trade:
        return "NO TRADE", "run /xau-size --write first"
    if not risk:
        return "NOT READY", "run /xau-risk first"
    if risk.get("fingerprint") != fingerprint(trade):
        return "NOT READY", "the trade changed after the risk check; run /xau-risk again"
    if risk.get("verdict") != "PASS":
        return "BLOCKED", "; ".join(r["message"] for r in risk.get("results", []) if r["level"] == "BLOCK")
    checked = dt.datetime.fromisoformat(risk["checked_at"])
    if dt.datetime.now(dt.timezone.utc) - checked > dt.timedelta(minutes=15):
        return "NOT READY", "the risk check is over 15 minutes old; gold moves fast, run /xau-risk again"
    return "READY", "xau-risk PASS"


def mt5_ticket(t, cfg):
    kind = {"market": "Market Execution", "limit": "Pending: %s Limit" % t["side"].capitalize(),
            "stop": "Pending: %s Stop" % t["side"].capitalize()}[t["type"]]
    lines = [
        "MT5 ORDER, %s account (%s)" % ("DEMO" if t.get("paper", True) else "LIVE", cfg.get("broker", "FP Markets")),
        "  Symbol       %s" % cfg.get("mt5_symbol", t.get("symbol", "XAUUSD")),
        "  Type         %s" % kind,
        "  Volume       %.2f" % t["lots"],
    ]
    if t["type"] != "market":
        lines.append("  Price        %.2f" % t["entry"])
    lines += [
        "  Stop Loss    %.2f" % t["sl"],
        "  Take Profit  %s" % ("%.2f" % t["tp"] if t.get("tp") is not None else "(none)"),
        "  Then click   %s" % ("%s by Market" % t["side"].capitalize() if t["type"] == "market" else "Place"),
        "  Risk $%.2f (%.2f%%)%s   setup: %s" % (t["risk_usd"], t["risk_pct"],
                                                 ", reward $%.2f, 1:%.2f" % (t["reward_usd"], t["rr"]) if t.get("reward_usd") else "",
                                                 t.get("setup") or "-"),
    ]
    if t["type"] == "market":
        lines.append("  If MT5's price is more than $%.2f from %.2f, stop and resize." % (cfg.get("max_slippage_usd", 0.5), t["entry"]))
    return "\n".join(lines)


YES = re.compile(r"^\s*(yes|y|yes,? place it|yes place it|confirm(ed)?|i placed it|placed)\s*[.!]?\s*$", re.I)


def is_explicit_yes(reply, trade):
    r = reply.strip()
    if YES.match(r):
        return True
    low = r.lower()
    if not low.startswith("yes") or "all" in low.split():
        return False
    # "yes, sell 0.03" style: every side and number it names must match this trade
    if ("buy" in low and trade["side"] != "buy") or ("sell" in low and trade["side"] != "sell"):
        return False
    for n in re.findall(r"\d+(?:\.\d+)?", low):
        if float(n) not in (trade["lots"], trade["entry"], trade["sl"], trade.get("tp")):
            return False
    return True


def journal(d):
    return load(os.path.join(d, "journal.json"), {"trades": []})


def find(j, i):
    for tr in j["trades"]:
        if tr["id"] == i:
            return tr
    raise SystemExit("ERROR: no trade #%d in the journal" % i)


def last_with(j, status):
    for tr in reversed(j["trades"]):
        if tr["status"] == status:
            return tr
    raise SystemExit("ERROR: no %s trade in the journal" % status)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="xau")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p = sub.add_parser("approve")
    p.add_argument("--reply", required=True)
    p = sub.add_parser("placed")
    p.add_argument("--id", type=int)
    p.add_argument("--mt5", help="MT5 position/ticket number")
    p.add_argument("--fill", type=float, help="actual fill price")
    p = sub.add_parser("close")
    p.add_argument("--id", type=int)
    p.add_argument("--exit", type=float, required=True)
    p.add_argument("--pnl", type=float, help="MT5's profit for the trade, after commission and swap")
    p.add_argument("--note", default="")
    p = sub.add_parser("cancel")
    p.add_argument("--id", type=int)
    p.add_argument("--note", default="")
    p = sub.add_parser("journal")
    p.add_argument("--days", type=int, default=30)
    p = sub.add_parser("stats")
    p.add_argument("--by", default="setup", choices=["setup", "side", "session", "weekday"])
    a = ap.parse_args(argv)
    d = a.dir
    cfg = load(os.path.join(d, "config.json"), {})
    trade = load(os.path.join(d, "trade.json"))
    risk = load(os.path.join(d, "state", "risk.json"))
    cs = float(cfg.get("contract_size", 100))

    if a.cmd == "show":
        state, why = readiness(trade, risk)
        if trade:
            print(mt5_ticket(trade, cfg))
        print("%s: %s" % (state, why))
        if state == "READY":
            print("Place this in MT5? Reply yes or no.")
        return 0 if state == "READY" else 1

    j = journal(d)
    if a.cmd == "approve":
        state, why = readiness(trade, risk)
        if state != "READY":
            print("Not recorded: %s (%s)" % (state, why))
            return 1
        if not is_explicit_yes(a.reply, trade):
            print("Not recorded: \"%s\" is not a clear yes for THIS trade. Ask again." % a.reply)
            return 1
        tr = dict(trade)
        tr.update({"id": (max([t["id"] for t in j["trades"]] or [0]) + 1), "status": "approved",
                   "approved_at": now_iso(), "reply": a.reply, "fingerprint": fingerprint(trade)})
        j["trades"].append(tr)
        save(os.path.join(d, "journal.json"), j)
        print("Recorded your yes as trade #%d. Now place it in MT5 exactly as shown, then tell me the fill." % tr["id"])
        return 0

    if a.cmd == "placed":
        tr = find(j, a.id) if a.id else last_with(j, "approved")
        tr.update({"status": "placed", "placed_at": now_iso(), "mt5_ticket": a.mt5,
                   "fill": a.fill if a.fill is not None else tr["entry"]})
        slip = abs(tr["fill"] - tr["entry"])
        save(os.path.join(d, "journal.json"), j)
        print("Trade #%d is open (%s %.2f lot @ %.2f, slippage %.2f)." % (tr["id"], tr["side"], tr["lots"], tr["fill"], slip))
        return 0

    if a.cmd == "close":
        tr = find(j, a.id) if a.id else last_with(j, "placed")
        sign = 1 if tr["side"] == "buy" else -1
        fill = tr.get("fill") or tr["entry"]
        gross = sign * (a.exit - fill) * tr["lots"] * cs
        pnl = a.pnl if a.pnl is not None else gross
        risk_usd = abs(fill - tr["sl"]) * tr["lots"] * cs or 1e-9
        tr.update({"status": "closed", "closed_at": now_iso(), "exit": a.exit, "pnl_usd": round(pnl, 2),
                   "r_multiple": round(pnl / risk_usd, 2), "close_note": a.note})
        save(os.path.join(d, "journal.json"), j)
        print("Trade #%d closed at %.2f: %s$%.2f (%+.2fR)%s" % (
            tr["id"], a.exit, "-" if pnl < 0 else "+", abs(pnl), tr["r_multiple"],
            "" if a.pnl is not None else "  (estimate; pass --pnl with MT5's figure to include commission/swap)"))
        return 0

    if a.cmd == "cancel":
        tr = find(j, a.id) if a.id else last_with(j, "approved")
        tr.update({"status": "cancelled", "close_note": a.note})
        save(os.path.join(d, "journal.json"), j)
        print("Trade #%d cancelled." % tr["id"])
        return 0

    closed = [t for t in j["trades"] if t["status"] == "closed"]
    if a.cmd == "journal":
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)).isoformat()
        rows = [t for t in j["trades"] if (t.get("approved_at") or "") >= cutoff]
        for t in rows:
            print("#%-3d %-9s %-4s %.2f @ %-8s SL %-8s %s %s" % (
                t["id"], t["status"], t["side"], t["lots"], t.get("fill") or t["entry"], t["sl"],
                "%+.2f (%+.2fR)" % (t["pnl_usd"], t["r_multiple"]) if t["status"] == "closed" else "",
                t.get("setup") or ""))
        cl = [t for t in rows if t["status"] == "closed"]
        if cl:
            wins = [t for t in cl if t["pnl_usd"] > 0]
            print("\n%d closed: %d wins (%.0f%%), net $%.2f, average %+.2fR, best %+.2fR, worst %+.2fR" % (
                len(cl), len(wins), 100 * len(wins) / len(cl), sum(t["pnl_usd"] for t in cl),
                sum(t["r_multiple"] for t in cl) / len(cl), max(t["r_multiple"] for t in cl),
                min(t["r_multiple"] for t in cl)))
        else:
            print("No closed trades in the last %d days." % a.days)
        return 0

    if a.cmd == "stats":
        groups = {}
        for t in closed:
            if a.by == "weekday":
                k = dt.datetime.fromisoformat(t["placed_at"]).strftime("%a")
            else:
                k = t.get(a.by) or "-"
            groups.setdefault(k, []).append(t)
        for k, ts in sorted(groups.items()):
            w = sum(1 for t in ts if t["pnl_usd"] > 0)
            print("%-20s %3d trades  %3.0f%% wins  net $%9.2f  avg %+.2fR" % (
                k, len(ts), 100 * w / len(ts), sum(t["pnl_usd"] for t in ts), sum(t["r_multiple"] for t in ts) / len(ts)))
        if not groups:
            print("No closed trades yet.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
