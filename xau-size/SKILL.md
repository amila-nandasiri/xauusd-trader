---
name: xau-size
description: >-
  XAUUSD lot-size calculator. Turns a gold trade idea (buy or sell, entry,
  stop-loss, target or reward:risk) into the exact MT5 lot size for the
  user's balance and risk %, counting the spread, rounding down to the 0.01
  lot step, and showing dollars at risk, dollars at target, R:R and margin.
  Says plainly when even 0.01 lot is too big for the stop. Writes the
  proposal to xau/trade.json. Use when the user says "how many lots",
  "size this trade", "lot size for gold", "I want to sell XAUUSD at ...",
  "risk 1%", "set up my rules", or has a setup from their chart.
argument-hint: "buy|sell entry stop [target]"
---

# xau-size

Gold on MT5 is priced in lots of 100 troy ounces (check: right-click XAUUSD
in Market Watch > Specification > Contract size). So a $1.00 move in gold is
$100 per 1.00 lot and **$1 per 0.01 lot**. The stop distance decides the lot
size, never the other way round.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --side sell --entry 4050.40 --sl 4052.90 --rr 2 --spread 0.25
python3 "${CLAUDE_SKILL_DIR}/size.py" --side buy --entry 4031 --sl 4027.5 --tp 4038 --setup "5m pullback" --write
python3 "${CLAUDE_SKILL_DIR}/size.py" --side buy --type limit --entry 4020 --sl 4016 --rr 2 --write
```

## Step 1: rules, once

If `xau/config.json` does not exist, copy `config.example.json` from this
folder to `xau/config.json` and go through it with the user in plain words:
balance (only money they can afford to lose), risk per trade as fixed
dollars (`risk_per_trade_usd`, set to $20, with `tp_usd` $40 for 1:2) or as a
percent (`risk_per_trade_pct`; a fixed $20 is 4% of a $500 account, so say what
percent it is of their balance), daily loss stop ($40 = two losses), max trades
per day, minimum R:R, max spread, allowed sessions, news blackout, their UTC
offset (Maldives is +5). Ask them to confirm contract size, min lot, lot step
and leverage from their MT5 symbol specification, not from memory.

## Step 2: size it

Ask for: buy or sell, entry (or "market"), the stop-loss **price** (where
the setup is wrong, from the chart), and target price or R:R. Ask for the
spread shown in MT5 (MT5 shows points: 25 points = $0.25 on a 2-digit gold
quote; on a 3-digit quote 250 points = $0.25). Run `size.py --write`.

The maths: risk $ = `risk_per_trade_usd` ($20), or balance x risk%; loss
per lot = (stop distance + spread) x 100; lots = risk $ / loss per lot,
**rounded down** to 0.01; target = where it makes `tp_usd` ($40) unless
`--tp` or `--rr` is given. If
that is under 0.01 lot, it says how much 0.01 lot would risk and writes
nothing: the answer is a tighter stop or no trade, never a bigger risk.

## Step 3: show it, then hand over

Show the block it prints. Then `/xau-risk`. Never skip the risk check.

## Rules

- Never guess a price, a spread or a stop. They come from the user's MT5 chart.
- Never raise the risk % to make a trade fit.
- No projections of what the account will be worth.

## Safety

- Education and tooling, not financial advice. Nothing here predicts gold or promises returns. Leveraged CFDs lose money fast.
- Demo first: `"paper": true` means a demo account. Switching to live is the user's own decision, in their own config.
- Nothing in this pack places an order. The user places every trade in MT5 themselves, after xau-risk passes it and they reply an explicit yes for that one trade.
- Every trade has a stop-loss. No averaging down, no moving a stop further away, no martingale, no grid.
- Never ask for, read or repeat MT5 passwords or investor passwords.
