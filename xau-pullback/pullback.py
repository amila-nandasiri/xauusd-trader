#!/usr/bin/env python3
"""xau-pullback: the 5-minute EMA trend-pullback setup for XAUUSD.

  python3 pullback.py check candles.csv            # is the LAST closed bar a signal? -> trade plan
  python3 pullback.py check candles.csv --write    # ...and write xau/trade.json for /xau-risk
  python3 pullback.py backtest candles.csv         # every signal in the file, $20 risk / $40 target
  python3 pullback.py rules                        # print the rules in force

Candles: 5-minute XAUUSD, oldest first, at least 250 bars. Accepted CSVs:
  - MT5 export (View > Symbols > Bars, or right-click chart in MT5 > ... > export):
    <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> ... (tab or comma separated)
  - TradingView "Export chart data": time,open,high,low,close,...  (unix or ISO time)
Times are read as UTC plus --tz-offset hours (MT5 server time at FP Markets is
usually UTC+2, UTC+3 in northern summer; TradingView exports what the chart shows).

THE RULES (long; short is the mirror image). Every number is in xau/config.json > "pullback".
  1 Trend     EMA50 above EMA200, close above EMA200, EMA50 higher than 10 bars ago
  2 Pullback  within the last 8 bars a low touched the EMA20 (low <= EMA20),
              and no bar closed below the EMA50 (the pullback stayed shallow)
  3 Trigger   the signal bar is green, closes above the EMA20 and above the previous bar's high
  4 Stop      lowest low of the pullback, minus a $0.30 buffer
  5 Filters   stop distance between min_sl_usd and max_sl_usd, and no more than 3 x ATR(14);
              session and news are checked afterwards by /xau-risk
  6 Size      $20 risk (risk_per_trade_usd), target where it makes $40 (tp_usd)
Standard library only.
"""
import argparse
import csv
import datetime as dt
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UTC = dt.timezone.utc

RULES = {
    "ema_fast": 20,
    "ema_mid": 50,
    "ema_slow": 200,
    "slope_bars": 10,
    "lookback": 8,
    "sl_buffer_usd": 0.30,
    "atr_period": 14,
    "max_sl_atr": 3.0,
    "sessions": ["london", "newyork"],
}


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sibling(skill, file):
    """Use the sizing / clock code from the sibling skill folders (same pack)."""
    for base in (os.path.dirname(HERE), os.path.expanduser("~/.claude/skills")):
        p = os.path.join(base, skill, file)
        if os.path.exists(p):
            return _load_module(skill.replace("-", "_") + "_" + file[:-3], p)
    return None


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


# ---------- candles ----------

def _num(x):
    return float(str(x).strip().replace(",", ""))


def _parse_time(row, keys, tz):
    if "<date>" in keys:
        s = "%s %s" % (row[keys["<date>"]].strip(), row[keys["<time>"]].strip() if "<time>" in keys else "00:00:00")
        t = dt.datetime.strptime(s.replace(".", "-"), "%Y-%m-%d %H:%M:%S" if s.count(":") == 2 else "%Y-%m-%d %H:%M")
        return (t - dt.timedelta(hours=tz)).replace(tzinfo=UTC)
    v = row[keys.get("time", keys.get("datetime", keys.get("date")))].strip()
    if v.replace(".", "").isdigit():
        return dt.datetime.fromtimestamp(float(v), UTC)
    t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    return t.astimezone(UTC) if t.tzinfo else (t - dt.timedelta(hours=tz)).replace(tzinfo=UTC)


def read_candles(text, tz=0.0):
    first = text.splitlines()[0]
    delim = "\t" if "\t" in first else ("," if "," in first else ";")
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    head = [h.strip().lower() for h in rows[0]]
    keys = {h: i for i, h in enumerate(head)}
    for want in ("open", "high", "low", "close"):
        if want not in keys and "<%s>" % want in keys:
            keys[want] = keys["<%s>" % want]
    if not all(k in keys for k in ("open", "high", "low", "close")):
        raise ValueError("no open/high/low/close columns in the header: %s" % head)
    out = []
    for r in rows[1:]:
        if not r or not "".join(r).strip():
            continue
        out.append({"time": _parse_time(r, keys, tz), "open": _num(r[keys["open"]]), "high": _num(r[keys["high"]]),
                    "low": _num(r[keys["low"]]), "close": _num(r[keys["close"]])})
    out.sort(key=lambda c: c["time"])
    return out


# ---------- indicators ----------

def ema(values, n):
    k, out, e = 2.0 / (n + 1), [], None
    for i, v in enumerate(values):
        if i < n - 1:
            out.append(None)
            continue
        e = sum(values[:n]) / n if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def atr(c, n):
    trs = [c[0]["high"] - c[0]["low"]] + [max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]),
                                              abs(c[i]["low"] - c[i - 1]["close"])) for i in range(1, len(c))]
    out, a = [], None
    for i, tr in enumerate(trs):
        if i < n - 1:
            out.append(None)
            continue
        a = sum(trs[:n]) / n if a is None else (a * (n - 1) + tr) / n
        out.append(a)
    return out


def indicators(c, r):
    closes = [x["close"] for x in c]
    return {"f": ema(closes, r["ema_fast"]), "m": ema(closes, r["ema_mid"]), "s": ema(closes, r["ema_slow"]),
            "atr": atr(c, r["atr_period"])}


# ---------- the setup ----------

def signal_at(c, ind, i, r, lim):
    """A signal on closed bar i, or (None, reason). lim has min_sl_usd / max_sl_usd."""
    need = max(r["ema_slow"], r["slope_bars"] + r["ema_mid"]) + r["lookback"]
    if i < need:
        return None, "not enough bars (need %d)" % need
    f, m, s, a = ind["f"], ind["m"], ind["s"], ind["atr"]
    bar, prev = c[i], c[i - 1]
    win = range(i - r["lookback"], i)
    up = m[i] > s[i] and bar["close"] > s[i] and m[i] > m[i - r["slope_bars"]]
    down = m[i] < s[i] and bar["close"] < s[i] and m[i] < m[i - r["slope_bars"]]
    if not (up or down):
        return None, "no trend (EMA%d/EMA%d not lined up)" % (r["ema_mid"], r["ema_slow"])
    if up:
        touched = [j for j in win if c[j]["low"] <= f[j]]
        if not touched:
            return None, "uptrend, but no pullback to the EMA%d in the last %d bars" % (r["ema_fast"], r["lookback"])
        if any(c[j]["close"] < m[j] for j in range(touched[0], i)):
            return None, "pullback too deep (closed below EMA%d)" % r["ema_mid"]
        if not (bar["close"] > bar["open"] and bar["close"] > f[i] and bar["close"] > prev["high"]):
            return None, "uptrend pullback in place, waiting for a green close above EMA%d and the previous high" % r["ema_fast"]
        side, sl = "buy", min(c[j]["low"] for j in range(touched[0], i + 1)) - r["sl_buffer_usd"]
    else:
        touched = [j for j in win if c[j]["high"] >= f[j]]
        if not touched:
            return None, "downtrend, but no pullback to the EMA%d in the last %d bars" % (r["ema_fast"], r["lookback"])
        if any(c[j]["close"] > m[j] for j in range(touched[0], i)):
            return None, "pullback too deep (closed above EMA%d)" % r["ema_mid"]
        if not (bar["close"] < bar["open"] and bar["close"] < f[i] and bar["close"] < prev["low"]):
            return None, "downtrend pullback in place, waiting for a red close below EMA%d and the previous low" % r["ema_fast"]
        side, sl = "sell", max(c[j]["high"] for j in range(touched[0], i + 1)) + r["sl_buffer_usd"]
    entry = bar["close"]
    dist = abs(entry - sl)
    if dist < lim["min_sl_usd"]:
        return None, "%s signal, but stop only $%.2f away (min $%.2f)" % (side, dist, lim["min_sl_usd"])
    if dist > lim["max_sl_usd"]:
        return None, "%s signal, but stop $%.2f away (max $%.2f)" % (side, dist, lim["max_sl_usd"])
    if a[i] and dist > r["max_sl_atr"] * a[i]:
        return None, "%s signal, but stop $%.2f is over %.1f x ATR ($%.2f)" % (side, dist, r["max_sl_atr"], a[i])
    return {"side": side, "entry": round(entry, 2), "sl": round(sl, 2), "time": bar["time"].isoformat(),
            "ema_fast": round(f[i], 2), "ema_mid": round(m[i], 2), "ema_slow": round(s[i], 2),
            "atr": round(a[i], 2) if a[i] else None}, "signal"


def settings(cfg):
    r = dict(RULES)
    r.update(cfg.get("pullback", {}))
    lim = {"min_sl_usd": cfg.get("min_sl_usd", 1.0), "max_sl_usd": cfg.get("max_sl_usd", 10.0)}
    return r, lim


def size_cfg(cfg):
    sz = _sibling("xau-size", "size.py")
    if not sz:
        raise SystemExit("ERROR: xau-size is not installed next to xau-pullback")
    full = dict(sz.DEFAULTS)
    full.update(cfg)
    if not full.get("balance"):
        full["balance"] = 1e9 if full.get("risk_per_trade_usd") else None
    return sz, full


# ---------- commands ----------

def cmd_check(a, cfg):
    c = read_candles(open(a.csv).read(), a.tz_offset)
    r, lim = settings(cfg)
    ind = indicators(c, r)
    # exports from MT5 and TradingView include the bar that is still forming: skip it
    i = len(c) - 1 if a.last_closed else len(c) - 2
    sig, why = signal_at(c, ind, i, r, lim)
    last = c[i]
    print("Last closed bar %s UTC  O %.2f H %.2f L %.2f C %.2f" % (last["time"].strftime("%a %d %b %H:%M"),
                                                                  last["open"], last["high"], last["low"], last["close"]))
    if ind["s"][i]:
        print("EMA%d %.2f  EMA%d %.2f  EMA%d %.2f  ATR %.2f" % (r["ema_fast"], ind["f"][i], r["ema_mid"], ind["m"][i],
                                                              r["ema_slow"], ind["s"][i], ind["atr"][i] or 0))
    if not sig:
        print("NO SIGNAL: %s" % why)
        return 1
    sz, full = size_cfg(cfg)
    t = sz.size(full, sig["side"], sig["entry"], sig["sl"], spread=a.spread)
    t["setup"] = "5m pullback"
    t["signal"] = sig
    print("SIGNAL: 5m pullback %s" % sig["side"].upper())
    print(sz.render(t))
    print("Check the chart: MT5's price now may differ from this close. Re-size if it has moved.")
    if a.write and t["ok"]:
        os.makedirs(a.dir, exist_ok=True)
        with open(os.path.join(a.dir, "trade.json"), "w") as f:
            json.dump(t, f, indent=2)
        print("Wrote %s/trade.json. Next: /xau-risk" % a.dir)
    return 0 if t["ok"] else 1


def simulate(c, ind, r, lim, sz, full, spread, sessions_fn=None):
    trades, i, n = [], 0, len(c)
    while i < n - 1:
        sig, _ = signal_at(c, ind, i, r, lim)
        if not sig or (sessions_fn and r["sessions"] and not set(sessions_fn(c[i]["time"])) & set(r["sessions"])):
            i += 1
            continue
        t = sz.size(full, sig["side"], sig["entry"], sig["sl"], spread=spread)
        if not t["ok"]:
            i += 1
            continue
        long_ = sig["side"] == "buy"
        result, j = None, i + 1
        while j < n:
            b = c[j]
            hit_sl = b["low"] <= t["sl"] if long_ else b["high"] >= t["sl"]
            hit_tp = b["high"] >= t["tp"] if long_ else b["low"] <= t["tp"]
            if hit_sl:                       # both in one bar counts as a loss (conservative)
                result = ("loss", -t["risk_usd"])
                break
            if hit_tp:
                result = ("win", round(t["reward_usd"] - t["lots"] * spread * full["contract_size"], 2))
                break
            j += 1
        if not result:
            break                            # still open at the end of the data
        trades.append({"time": sig["time"], "side": sig["side"], "entry": t["entry"], "sl": t["sl"], "tp": t["tp"],
                       "lots": t["lots"], "result": result[0], "pnl": result[1], "bars": j - i})
        i = j + 1                            # one trade at a time
    return trades


def cmd_backtest(a, cfg):
    c = read_candles(open(a.csv).read(), a.tz_offset)
    r, lim = settings(cfg)
    if a.all_sessions:
        r["sessions"] = []
    ind = indicators(c, r)
    sz, full = size_cfg(cfg)
    clock = _sibling("xau-alerts", "xautime.py")
    trades = simulate(c, ind, r, lim, sz, full, a.spread, clock.sessions_now if clock else None)
    for t in trades[-a.show:]:
        print("%s  %-4s %.2f lot  in %.2f  SL %.2f  TP %.2f  %-4s %+7.2f  (%d bars)" % (
            t["time"][:16].replace("T", " "), t["side"], t["lots"], t["entry"], t["sl"], t["tp"], t["result"], t["pnl"], t["bars"]))
    if not trades:
        print("No completed signals in %d bars (%s to %s)." % (len(c), c[0]["time"].date(), c[-1]["time"].date()))
        return 1
    wins = [t for t in trades if t["result"] == "win"]
    net = sum(t["pnl"] for t in trades)
    peak = eq = dd = 0.0
    streak = worst_streak = 0
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        streak = streak + 1 if t["pnl"] < 0 else 0
        worst_streak = max(worst_streak, streak)
    days = max((c[-1]["time"] - c[0]["time"]).days, 1)
    print("\n%d trades over %d days (%s to %s, sessions: %s)" % (len(trades), days, c[0]["time"].date(), c[-1]["time"].date(),
                                                           ", ".join(r["sessions"]) or "all"))
    print("wins %d (%.0f%%)   net $%.2f   avg $%.2f per trade   max drawdown $%.2f   worst losing run %d" % (
        len(wins), 100 * len(wins) / len(trades), net, net / len(trades), -dd, worst_streak))
    rk, tg = full.get("risk_per_trade_usd") or 1, full.get("tp_usd") or 2 * (full.get("risk_per_trade_usd") or 1)
    print("Break-even win rate at $%g risk / $%g target is about %.0f%% (before costs)." % (rk, tg, 100 * rk / (rk + tg)))
    print("Past candles, no slippage, no news filter: a sanity check, not a promise.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="xau")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "backtest"):
        p = sub.add_parser(name)
        p.add_argument("csv")
        p.add_argument("--tz-offset", type=float, default=0.0, help="hours the CSV times are ahead of UTC (MT5 server: 2 or 3)")
        p.add_argument("--spread", type=float, default=0.25)
        if name == "check":
            p.add_argument("--write", action="store_true")
            p.add_argument("--last-closed", action="store_true",
                           help="the last row is already closed (default: last row is the forming bar, skip it)")
        else:
            p.add_argument("--show", type=int, default=20, help="how many of the last trades to list")
            p.add_argument("--all-sessions", action="store_true")
    sub.add_parser("rules")
    a = ap.parse_args(argv)
    cfg = load_json(os.path.join(a.dir, "config.json"), {})
    if a.cmd == "rules":
        r, lim = settings(cfg)
        print(json.dumps(dict(r, **lim, risk_per_trade_usd=cfg.get("risk_per_trade_usd"), tp_usd=cfg.get("tp_usd")), indent=2))
        return 0
    try:
        return cmd_check(a, cfg) if a.cmd == "check" else cmd_backtest(a, cfg)
    except (OSError, ValueError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
