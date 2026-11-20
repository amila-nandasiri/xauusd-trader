#!/usr/bin/env python3
"""xau-size: lot size for one XAUUSD trade from your stop-loss and risk %.

  python3 size.py --side sell --entry 2650.40 --sl 2655.40 --tp 2640.40
  python3 size.py --side buy --entry 2650 --sl 2646 --rr 2 --spread 0.25 --write
  python3 size.py --side buy --type limit --entry 2640 --sl 2636 --tp 2652 --balance 480

How XAUUSD is priced (FP Markets and most MT5 brokers, check your symbol
specification): 1.00 lot = 100 troy oz, so a $1.00 move in gold is $100 per
1.00 lot, $1 per 0.01 lot. Minimum 0.01 lot, step 0.01.

  risk $      = balance x risk_per_trade_pct / 100
  loss / lot  = (|entry - stop| + spread) x contract_size
  lots        = risk $ / loss per lot, rounded DOWN to the lot step
  margin      = lots x contract_size x entry / leverage

Writes xau/trade.json (the proposal) with --write. Never places anything.
Standard library only.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys

DEFAULTS = {
    "symbol": "XAUUSD",
    "account_currency": "USD",
    "paper": True,
    "balance": None,
    "contract_size": 100,
    "min_lot": 0.01,
    "lot_step": 0.01,
    "max_lot": 1.0,
    "leverage": 500,
    "risk_per_trade_pct": 1.0,
    "default_spread": 0.0,
}


def load_config(path):
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg


def floor_step(x, step):
    n = math.floor(x / step + 1e-9)
    return round(n * step, 8)


def size(cfg, side, entry, sl, tp=None, rr=None, spread=None, balance=None, risk_pct=None, order_type="market"):
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    balance = float(balance if balance is not None else cfg["balance"] or 0)
    if balance <= 0:
        raise ValueError("no balance: set \"balance\" in xau/config.json or pass --balance")
    risk_pct = float(risk_pct if risk_pct is not None else cfg["risk_per_trade_pct"])
    spread = float(spread if spread is not None else cfg.get("default_spread", 0) or 0)
    entry, sl = float(entry), float(sl)
    sign = 1 if side == "buy" else -1
    if (entry - sl) * sign <= 0:
        raise ValueError("stop-loss is on the wrong side: a %s needs the stop %s the entry"
                         % (side, "below" if side == "buy" else "above"))
    sl_dist = abs(entry - sl)
    if tp is None and rr:
        tp = round(entry + sign * sl_dist * float(rr), 2)
    if tp is not None:
        tp = float(tp)
        if (tp - entry) * sign <= 0:
            raise ValueError("take-profit is on the wrong side of the entry")
    cs = float(cfg["contract_size"])
    risk_usd = balance * risk_pct / 100.0
    loss_per_lot = (sl_dist + spread) * cs
    raw = risk_usd / loss_per_lot
    lots = min(floor_step(raw, cfg["lot_step"]), float(cfg["max_lot"]))
    notes = []
    too_small = lots < cfg["min_lot"] - 1e-9
    if too_small:
        min_risk = cfg["min_lot"] * loss_per_lot
        notes.append("Even the minimum %.2f lot risks $%.2f (%.2f%% of balance), over your $%.2f. "
                     "Use a tighter stop, or skip this trade." % (cfg["min_lot"], min_risk, 100 * min_risk / balance, risk_usd))
    if raw > cfg["max_lot"]:
        notes.append("Capped at max_lot %.2f." % cfg["max_lot"])
    actual_risk = lots * loss_per_lot
    reward = lots * abs(tp - entry) * cs if tp is not None else None
    margin = lots * cs * entry / float(cfg["leverage"])
    return {
        "symbol": cfg["symbol"],
        "side": side,
        "type": order_type,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp": round(tp, 2) if tp is not None else None,
        "lots": 0.0 if too_small else round(lots, 2),
        "sl_distance": round(sl_dist, 2),
        "spread": spread,
        "risk_usd": round(0 if too_small else actual_risk, 2),
        "risk_pct": round(0 if too_small else 100 * actual_risk / balance, 3),
        "risk_budget_usd": round(risk_usd, 2),
        "reward_usd": round(reward, 2) if reward is not None and not too_small else None,
        "rr": round(abs(tp - entry) / sl_dist, 2) if tp is not None else None,
        "usd_per_dollar_move": round(lots * cs, 2),
        "margin_usd": round(margin, 2),
        "balance": balance,
        "paper": bool(cfg.get("paper", True)),
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "ok": not too_small,
        "notes": notes,
    }


def render(t):
    acct = "DEMO" if t["paper"] else "LIVE"
    lines = [
        "%s %s %s, %s account" % (t["side"].upper(), t["symbol"], t["type"], acct),
        "  entry %.2f   stop %.2f (%.2f away)   target %s" % (
            t["entry"], t["sl"], t["sl_distance"], "%.2f" % t["tp"] if t["tp"] is not None else "none"),
        "  lot size     %.2f lot  ($%.2f per $1 move in gold)" % (t["lots"], t["usd_per_dollar_move"]),
        "  risk         $%.2f = %.2f%% of $%.2f (budget $%.2f, spread %.2f included)" % (
            t["risk_usd"], t["risk_pct"], t["balance"], t["risk_budget_usd"], t["spread"]),
    ]
    if t["reward_usd"] is not None:
        lines.append("  reward       $%.2f at target, R:R 1:%.2f" % (t["reward_usd"], t["rr"]))
    lines.append("  margin       about $%.2f" % t["margin_usd"])
    lines += ["  NOTE: " + n for n in t["notes"]]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--side", required=True, choices=["buy", "sell"])
    ap.add_argument("--entry", required=True, type=float)
    ap.add_argument("--sl", required=True, type=float, help="stop-loss price (required, always)")
    ap.add_argument("--tp", type=float, help="take-profit price")
    ap.add_argument("--rr", type=float, help="set the take-profit at this reward:risk instead of --tp")
    ap.add_argument("--type", default="market", choices=["market", "limit", "stop"])
    ap.add_argument("--spread", type=float, help="current spread in $ (MT5 shows it in points: 25 points = 0.25)")
    ap.add_argument("--balance", type=float)
    ap.add_argument("--risk", type=float, help="risk %% for this trade (default from config)")
    ap.add_argument("--setup", default="", help="name of the setup, e.g. '5m pullback'")
    ap.add_argument("--config", default="xau/config.json")
    ap.add_argument("--write", action="store_true", help="write xau/trade.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    try:
        t = size(cfg, a.side, a.entry, a.sl, a.tp, a.rr, a.spread, a.balance, a.risk, a.type)
    except ValueError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    t["setup"] = a.setup
    print(json.dumps(t, indent=2) if a.json else render(t))
    if a.write and t["ok"]:
        os.makedirs(os.path.dirname(a.config) or ".", exist_ok=True)
        path = os.path.join(os.path.dirname(a.config) or ".", "trade.json")
        with open(path, "w") as f:
            json.dump(t, f, indent=2)
        print("Wrote %s. Next: /xau-risk" % path)
    return 0 if t["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
