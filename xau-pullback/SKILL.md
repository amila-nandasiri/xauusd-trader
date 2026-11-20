---
name: xau-pullback
description: >-
  The 5-minute EMA trend-pullback setup for XAUUSD. Reads 5m gold candles
  exported from MT5 or TradingView, checks whether the last closed bar is a
  pullback signal (EMA50/EMA200 trend, pullback to the EMA20 that holds the
  EMA50, a trigger candle closing back in trend), puts the stop under/over the
  pullback, sizes it at $20 risk with the target at $40, and writes
  xau/trade.json for xau-risk. Also backtests the rules on the user's own
  history (win rate, net, drawdown, losing runs) and ships a matching
  TradingView indicator with alerts. Use when the user says "5m pullback",
  "pullback setup", "is this a signal", "my TradingView alert fired",
  "backtest my strategy", "check this chart export".
argument-hint: "[check|backtest|rules] candles.csv"
---

# xau-pullback

One setup, written down so it is the same every time. The rules are a
standard EMA trend pullback, the starting point the user chose; every number
is in `xau/config.json` under `"pullback"` and they can change it.

```bash
python3 "${CLAUDE_SKILL_DIR}/pullback.py" rules
python3 "${CLAUDE_SKILL_DIR}/pullback.py" check XAUUSD_M5.csv --tz-offset 2 --spread 0.25 --write
python3 "${CLAUDE_SKILL_DIR}/pullback.py" backtest XAUUSD_M5.csv --tz-offset 2 --spread 0.25
```

## The rules (long; short is the mirror)

1. **Trend**: EMA50 above EMA200, price above EMA200, EMA50 higher than 10 bars ago.
2. **Pullback**: in the last 8 bars a low touched the EMA20, and no bar closed below the EMA50.
3. **Trigger**: the bar closes green, above the EMA20 and above the previous bar's high.
4. **Stop**: lowest low of the pullback minus $0.30.
5. **Filters**: stop $1-$10 away and no more than 3 x ATR(14). Session and news: `/xau-risk`.
6. **Size**: $20 risk (`risk_per_trade_usd`), target where it makes $40 (`tp_usd`), so 1:2.
   The lot rounds down to 0.01, so the real risk is usually a little under $20.

## Getting candles

- **MT5**: View > Symbols (Ctrl+U) > Bars tab > XAUUSD, M5, a date range > Request > Export Bars.
  Times are MT5 server time: `--tz-offset 2` (FP Markets winter) or `3` (summer).
  Check: Market Watch time vs. UTC.
- **TradingView**: chart > ... > Export chart data (paid plans). Time is usually unix: no offset needed.
- The newest row is usually the bar still forming; `check` skips it unless `--last-closed`.

## Steps, live

1. The TradingView alert fires (`pullback.pine`), or the user asks "is this a signal?".
2. Ask for a fresh export (or the CSV path) and the MT5 spread. Run `check --write`.
3. NO SIGNAL: say why in one line (it prints the reason). Do not argue the chart into a signal.
4. SIGNAL: show the plan, remind them MT5's price now may differ from that close, then
   `/xau-news now` and `/xau-risk`, then `/xau-ticket`. Same gates as every trade.

## Backtest, honestly

`backtest` walks the candles one trade at a time: the next bar that touches
the stop or the target decides it, and a bar that touches both counts as a
loss. It applies the session filter but **not** the news filter, slippage or
swap. At $20 / $40 the break-even win rate is about 33%. Report win rate,
net, max drawdown and the worst losing run, and say plainly when the sample is
small (under ~100 trades is noise). Never present a backtest as what will
happen next.

## TradingView

`pullback.pine` (this folder) draws the same signals with lot/SL/TP labels.
Pine Editor > paste > Add to chart, then Create Alert > "Pullback BUY" or
"Pullback SELL" > Once per bar close. Compare a few of its arrows with
`backtest` output before trusting either.

## Safety

- Education and tooling, not financial advice. Nothing here predicts gold or promises returns. Leveraged CFDs lose money fast.
- Demo first: `"paper": true` means a demo account. Switching to live is the user's own decision, in their own config.
- Nothing in this pack places an order. The user places every trade in MT5 themselves, after xau-risk passes it and they reply an explicit yes for that one trade.
- Every trade has a stop-loss. No averaging down, no moving a stop further away, no martingale, no grid.
- Never ask for, read or repeat MT5 passwords or investor passwords.
