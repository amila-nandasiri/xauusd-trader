---
name: xau-ticket
description: >-
  MT5 order ticket and trade journal for XAUUSD. After xau-risk passes a
  trade, shows it as the exact fields to type into MetaTrader 5's New Order
  window (symbol, Market Execution or pending type, volume, stop loss, take
  profit), records the user's explicit yes, then logs the fill, the close and
  the real P&L in R, and reports win rate, average R and results by setup.
  Use when the user says "give me the ticket", "place it", "I'm in", "I got
  filled at", "closed at", "stopped out", "hit TP", "my journal", "how am I
  doing", "stats".
argument-hint: "[show|approve|placed|close|journal|stats]"
---

# xau-ticket

There is no official MetaTrader 5 connector, so **Claude never places an
order**. The user places it in MT5 by hand. This skill makes that step exact
and keeps the honest record that the risk rules depend on (trades today,
daily loss, losing streak).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --reply "<the user's reply, word for word>"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" placed --mt5 5512345 --fill 4050.30
python3 "${CLAUDE_SKILL_DIR}/ticket.py" close --exit 4052.90 --pnl -2.67
python3 "${CLAUDE_SKILL_DIR}/ticket.py" cancel --note "missed the entry"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" journal --days 30
python3 "${CLAUDE_SKILL_DIR}/ticket.py" stats --by setup      # or side, weekday
```

## Steps

1. `show`. Only a READY ticket goes to the user (xau-risk PASS on this exact
   trade, under 15 minutes old). NOT READY or BLOCKED goes back to `/xau-risk`.
2. Show the ticket and ask: "Place this in MT5? Reply yes or no." One trade per question.
3. `approve --reply "<their words>"`. If it prints "Not recorded" (for
   example "sure", "yes to all", or a yes naming another side or size), ask
   again. Never turn a reply into a yes yourself.
4. The user places it in MT5 (F9 or New Order: Symbol, Type, Volume, Stop
   Loss, Take Profit, then Sell by Market / Buy by Market, or Place for a
   pending order). If MT5's price has moved more than `max_slippage_usd`
   from the planned entry, they stop and resize instead.
5. When they report the fill: `placed --fill PRICE --mt5 TICKET`.
6. When it closes: `close --exit PRICE --pnl X`, with the profit figure
   from MT5's History tab, which includes commission and swap.
7. Weekly or when asked, run `journal` and `stats` and report the numbers
   plainly, including the losing ones.

## Never

- Never claims an order was placed. Only the user can say that.
- Never one yes for several trades, and never from a scheduled task.
- Never edits the journal to hide a loss; a wrong entry is fixed with the user watching.

## Safety

- Education and tooling, not financial advice. Nothing here predicts gold or promises returns. Leveraged CFDs lose money fast.
- Demo first: `"paper": true` means a demo account. Switching to live is the user's own decision, in their own config.
- Nothing in this pack places an order. The user places every trade in MT5 themselves, after xau-risk passes it and they reply an explicit yes for that one trade.
- Every trade has a stop-loss. No averaging down, no moving a stop further away, no martingale, no grid.
- Never ask for, read or repeat MT5 passwords or investor passwords.
