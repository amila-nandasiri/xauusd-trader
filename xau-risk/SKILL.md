---
name: xau-risk
description: >-
  XAUUSD risk gate. Checks the proposed gold trade in xau/trade.json against
  the user's rules and prints PASS or BLOCK with the reason: stop-loss present
  and on the right side, stop distance, risk % per trade with spread, minimum
  reward:risk, spread, margin, max trades per day, open positions, daily loss
  stop, losing streak (tilt) stop, gold market hours and daily break, allowed
  sessions, and a news blackout around high-impact USD events (CPI, NFP, FOMC).
  Use before every trade, and when the user says "can I take this", "check my
  trade", "is it safe", "risk check", "am I allowed to trade now".
argument-hint: "[--spread 0.25]"
---

# xau-risk

The gate between an idea and MT5. A BLOCK is final for that trade: it is not
shown as a ticket and the user is not asked for a yes. A PASS only means the
trade follows the user's own rules. It is not a signal.

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py" --spread 0.25     # xau/trade.json; writes xau/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --json --no-write
```

## Reads

| file | from |
| --- | --- |
| `xau/trade.json` | xau-size |
| `xau/config.json` | the user's limits (xau-size ships `config.example.json`) |
| `xau/journal.json` | xau-ticket: trades today, open positions, P&L, losing streak |
| `xau/calendar.json` | xau-news: high-impact events for the blackout |

## Checks

| rule | blocks when |
| --- | --- |
| stop-loss | missing, or on the wrong side |
| stop distance | under `min_sl_usd` (noise) or over `max_sl_usd` |
| risk | lots x (stop + spread) x 100 is over `max_risk_per_trade_pct` of balance |
| reward:risk | no target, or under `min_rr` |
| spread | over `max_spread_usd` (wide spreads usually mean news or thin hours) |
| lots / margin | outside min/max/step, or margin over `max_margin_pct` of balance |
| daily trades / open positions | at `max_trades_per_day` / `max_open_positions` |
| daily loss | realised loss today, plus this trade's risk, would pass `max_daily_loss_pct` |
| loss streak | `max_consecutive_losses` losses in a row today: done for the day |
| market hours | market order while gold is closed (weekend, or the 17:00-18:00 New York break) |
| session | market order outside `allowed_sessions` (block or warn, `session_rule`) |
| news | a high-impact USD event within the blackout window |

The trading day rolls at 17:00 New York (MT5 server midnight at most brokers),
or at the user's local midnight with `"day_starts": "local"`.

## Steps

1. If `xau/calendar.json` is missing or over a day old, run `/xau-news` calendar first.
2. Get the spread from MT5 and run `check.py --spread X`.
3. Say the verdict in plain words. For a BLOCK, give the reason and the honest
   fixes (wait until after the news, a tighter stop with a smaller size, skip it).
   **Never change a limit yourself**, and never re-run with different numbers to
   get a PASS the user did not ask for.
4. Any change to the trade means a new check. A check over 15 minutes old is
   stale for xau-ticket.

## Safety

- Education and tooling, not financial advice. Nothing here predicts gold or promises returns. Leveraged CFDs lose money fast.
- Demo first: `"paper": true` means a demo account. Switching to live is the user's own decision, in their own config.
- Nothing in this pack places an order. The user places every trade in MT5 themselves, after xau-risk passes it and they reply an explicit yes for that one trade.
- Every trade has a stop-loss. No averaging down, no moving a stop further away, no martingale, no grid.
- Never ask for, read or repeat MT5 passwords or investor passwords.
