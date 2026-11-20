---
name: xau-alerts
description: >-
  Gold market clock and price alerts for XAUUSD. Says whether gold is open
  (Sunday 18:00 to Friday 17:00 New York time, daily break 17:00-18:00),
  which sessions are live (Asia, London, New York and the London/New York
  overlap) and when the next ones open, all in the user's local time with
  daylight saving handled, and rings once on price levels, percent moves
  and session opens from free delayed quotes. Use when the user says "is gold
  open", "when does London open", "what session is it", "alert me if gold
  hits", "gold price now", "watch 4100".
argument-hint: "[clock|quote|add|check]"
---

# xau-alerts

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --above 4100 --note "breakout of range high"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --below 4020 --rearm
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --pct 1.5
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --session london
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check           # exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list | reset ID | remove ID
```

## Prices, honestly

- `stooq` spot XAUUSD first, then `yahoo` GC=F futures. Both are free,
  unofficial and delayed, and **futures trade a few dollars above spot**.
- They are good for "come and look at the chart". For entries, stops and
  exact levels, the user's MT5 price is the only one that counts, and MT5's
  own alerts (right-click chart > Trading > Alert) or TradingView alerts are
  more precise. Say so when setting a level alert.
- If both sources fail, ask the user for the MT5 price and pass `--price`.

## Sessions

Each session in its own city's time, converted with daylight saving:
Asia (Tokyo 09:00-18:00), London 08:00-17:00, New York 08:00-17:00. The
London/New York overlap is usually the most liquid stretch for gold. Brokers
can differ by minutes; the MT5 symbol specification has the real hours.

## Steps

1. Put the user's level in their words, confirm it back, add it.
2. Run `check` now, and on a schedule only if they ask (a scheduled task
   every 15 minutes during the sessions they trade is plenty).
3. Report what rang in one line each. An alert is information, never a
   trade: if they want to act, the path is xau-size, xau-risk, xau-ticket.

## Safety

- Education and tooling, not financial advice. Nothing here predicts gold or promises returns. Leveraged CFDs lose money fast.
- Demo first: `"paper": true` means a demo account. Switching to live is the user's own decision, in their own config.
- Nothing in this pack places an order. The user places every trade in MT5 themselves, after xau-risk passes it and they reply an explicit yes for that one trade.
- Every trade has a stop-loss. No averaging down, no moving a stop further away, no martingale, no grid.
- Never ask for, read or repeat MT5 passwords or investor passwords.
