# XAUUSD Trader skill

5 Claude skills made only for trading gold (XAUUSD) on MetaTrader 5: they size every
trade from your stop-loss, block anything that breaks your rules or lands on top of
US news, hand you the exact MT5 ticket, and keep an honest journal.

Free, MIT, no signup, no API key, nothing to pip install. Plain Python 3.8+.

**Claude never places a trade.** There is no official MT5 connector, and this pack
does not want one. You place every order yourself in MT5, after the risk check passes
and you reply "yes" to that one trade.

## Install

Paste this into Claude:

```
https://github.com/<your-github-username>/xauusd-trader
install skill
```

Or in Claude Code, as a plugin:

```
/plugin marketplace add <your-github-username>/xauusd-trader
/plugin install xauusd-trader@xauusd-trader
```

Or copy the folders:

```bash
git clone https://github.com/<your-github-username>/xauusd-trader.git
cp -r xauusd-trader/xau-* ~/.claude/skills/
```

## The five

| command | job | what it does |
| --- | --- | --- |
| `/xau-size` | Lot sizer | Entry + stop-loss + risk % → the exact lot size (100 oz contract, 0.01 step, spread included), $ at risk, $ at target, R:R, margin. Tells you when even 0.01 lot is too big. |
| `/xau-risk` | Risk gate | PASS / BLOCK: stop-loss, stop distance, risk %, min R:R, spread, margin, trades per day, open positions, daily loss stop, losing-streak stop, gold hours, sessions, news blackout. |
| `/xau-ticket` | MT5 ticket + journal | The fields to type into MT5's New Order window, your recorded yes, then fill, close, P&L in R, win rate and stats by setup. |
| `/xau-alerts` | Clock + alerts | Is gold open, which session (Asia / London / New York / overlap), next opens in your local time with DST handled; one-shot price, % move and session alerts. |
| `/xau-news` | Calendar + headlines | High-impact USD events (CPI, NFP, FOMC, PCE...) in your time, blackout check, gold headlines tagged Fed / inflation / jobs / dollar / yields / geopolitics. |

## How a trade flows

```
xau-news calendar  (Monday, and each morning)
xau-alerts clock   (is it my session?)
   your chart gives a setup
xau-size  -> xau-risk -> xau-ticket show -> "yes" -> you place it in MT5
xau-ticket placed / close                       -> journal feeds tomorrow's limits
```

Example (prices made up), $500 demo, 1% risk, 5-minute pullback short:

```
$ python3 xau-size/size.py --side sell --entry 4050.40 --sl 4052.90 --rr 2 --spread 0.25 --setup "5m pullback" --write
SELL XAUUSD market, DEMO account
  entry 4050.40   stop 4052.90 (2.50 away)   target 4045.40
  lot size     0.01 lot  ($1.00 per $1 move in gold)
  risk         $2.75 = 0.55% of $500.00 (budget $5.00, spread 0.25 included)
  reward       $5.00 at target, R:R 1:2.00
  margin       about $8.10

$ python3 xau-risk/check.py --spread 0.25          # 25 min before US Flash PMI
BLOCK  SELL 0.01 lot XAUUSD @ 4050.40  SL 4052.90  TP 4045.4
  BLOCK news            USD Flash Manufacturing PMI at 19:45 local (High): inside your 30/30 min blackout
```

The arithmetic you should know by heart: **1.00 lot = 100 oz, so $1 in gold = $100
per lot = $1 per 0.01 lot.** On a small account the stop distance, not your
confidence, decides the size: at $500 and 1% risk, 0.01 lot fits a stop of at most
about $5.

## Your rules

Copy `xau-size/config.example.json` to `xau/config.json` in the folder you trade from
and edit it. Check contract size, min lot, lot step and leverage against MT5
(Market Watch > right-click XAUUSD > Specification). Defaults:

| setting | default |
| --- | --- |
| risk per trade | 1% |
| daily loss stop | 3% |
| trades per day / open at once | 3 / 1 |
| stop after losses in a row | 2 |
| minimum reward:risk | 1:1.5 |
| stop distance | $1 to $15 |
| max spread | $0.50 |
| sessions | London, New York |
| news blackout | 30 min before and after high-impact USD events |
| local time | UTC+5 |

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
