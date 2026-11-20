# XAUUSD Trader skill

6 Claude skills made only for trading gold (XAUUSD) on MetaTrader 5: they size every
trade from your stop-loss, block anything that breaks your rules or lands on top of
US news, hand you the exact MT5 ticket, and keep an honest journal.

Free, MIT, no signup, no API key, nothing to pip install. Plain Python 3.8+.

**Claude never places a trade.** There is no official MT5 connector, and this pack
does not want one. You place every order yourself in MT5, after the risk check passes
and you reply "yes" to that one trade.

## Install

Paste this into Claude:

```
https://github.com/amila-nandasiri/xauusd-trader
install skill
```

Or in Claude Code, as a plugin:

```
/plugin marketplace add amila-nandasiri/xauusd-trader
/plugin install xauusd-trader@xauusd-trader
```

Or copy the folders:

```bash
git clone https://github.com/amila-nandasiri/xauusd-trader.git
cp -r xauusd-trader/xau-* ~/.claude/skills/
```

## The six

| command | job | what it does |
| --- | --- | --- |
| `/xau-pullback` | 5m pullback setup | Reads 5m candles from MT5/TradingView: EMA50/200 trend, pullback to EMA20 that holds the EMA50, trigger candle → entry, stop, lots. Backtests the rules on your history. Ships a matching TradingView indicator with alerts. |
| `/xau-size` | Lot sizer | Entry + stop-loss + $20 risk (or a %) → the exact lot size (100 oz contract, 0.01 step, spread included), $ at risk, $ at target, R:R, margin. Tells you when even 0.01 lot is too big. |
| `/xau-risk` | Risk gate | PASS / BLOCK: stop-loss, stop distance, risk %, min R:R, spread, margin, trades per day, open positions, daily loss stop, losing-streak stop, gold hours, sessions, news blackout. |
| `/xau-ticket` | MT5 ticket + journal | The fields to type into MT5's New Order window, your recorded yes, then fill, close, P&L in R, win rate and stats by setup. |
| `/xau-alerts` | Clock + alerts | Is gold open, which session (Asia / London / New York / overlap), next opens in your local time with DST handled; one-shot price, % move and session alerts. |
| `/xau-news` | Calendar + headlines | High-impact USD events (CPI, NFP, FOMC, PCE...) in your time, blackout check, gold headlines tagged Fed / inflation / jobs / dollar / yields / geopolitics. |

## How a trade flows

```
xau-news calendar  (Monday, and each morning)
xau-alerts clock   (is it my session?)
   TradingView alert (pullback.pine) fires
xau-pullback check  (or xau-size by hand)
          -> xau-risk -> xau-ticket show -> "yes" -> you place it in MT5
xau-ticket placed / close                       -> journal feeds tomorrow's limits
```

Example (prices made up), $20 risk, $40 target:

```
$ python3 xau-size/size.py --side buy --entry 4050 --sl 4046 --spread 0.25 --write
BUY XAUUSD market, DEMO account
  entry 4050.00   stop 4046.00 (4.00 away)   target 4060.00
  lot size     0.04 lot  ($4.00 per $1 move in gold)
  risk         $17.00 = 1.70% of $1000.00 (budget $20.00, spread 0.25 included)
  reward       $40.00 at target, R:R 1:2.50
  margin       about $32.40

$ python3 xau-risk/check.py --spread 0.25          # 25 min before US Flash PMI
BLOCK  BUY 0.04 lot XAUUSD @ 4050.00  SL 4046.00  TP 4060.0
  BLOCK news            USD Flash Manufacturing PMI at 19:45 local (High): inside your 30/30 min blackout
```

The arithmetic you should know by heart: **1.00 lot = 100 oz, so $1 in gold = $100
per lot = $1 per 0.01 lot.** The stop distance, not your confidence, decides the
size: with $20 risk, a $2 stop is 0.09 lot (with spread), a $4 stop 0.04 lot, a $10 stop
0.01 lot. The lot rounds down, so the real risk is usually a little under $20.

With $20 risk and a $40 target you need to win about 1 trade in 3 to break even
before costs. $20 is 2% of a $1,000 account and 4% of a $500 one: set the balance
in the config so the percentage is in front of you.

## Your rules

Copy `xau-size/config.example.json` to `xau/config.json` in the folder you trade from
and edit it. Check contract size, min lot, lot step and leverage against MT5
(Market Watch > right-click XAUUSD > Specification). Defaults:

| setting | default |
| --- | --- |
| risk per trade | $20 (or a % if you prefer) |
| target | where it makes $40 (1:2) |
| daily loss stop | $40 (two losses) |
| trades per day / open at once | 3 / 1 |
| stop after losses in a row | 2 |
| minimum reward:risk | 1:2 |
| stop distance | $1 to $10 |
| max spread | $0.50 |
| sessions | London, New York |
| news blackout | 30 min before and after high-impact USD events |
| local time | UTC+5 |

The 5m pullback rules are under `"pullback"` in the same file (EMA 20/50/200,
8-bar lookback, $0.30 stop buffer, stop no more than 3 x ATR, London + New York).

Everything lives in `xau/`: `config.json`, `trade.json`, `calendar.json`,
`journal.json`, `alerts.json`, `state/`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Offline, on small fixtures. The live feeds (Forex Factory calendar, Stooq, Yahoo,
Google News RSS) are free and unofficial and can change or go down; every tool says
so when one fails, and falls back to you reading the number off MT5.

## Fine print

**Not financial advice.** This is software that does arithmetic and enforces rules
you set. It does not know where gold is going. CFDs on gold are leveraged and most
retail accounts lose money on them. Trade a demo account first.

**Every trade has a stop-loss.** No averaging down, no widening stops, no martingale,
no grid. The pack will not size or pass a trade without a stop.

**Never share your MT5 password** with Claude or anyone else.

## Credit

Structure and the "never trade without your yes" approach are adapted from
[Jakeschincariol/trader-skill](https://github.com/Jakeschincariol/trader-skill) (MIT),
which does the same for US stocks. The gold tools here are written from scratch.

MIT.
