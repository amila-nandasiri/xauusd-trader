---
name: xau-news
description: >-
  Gold news and economic calendar. Pulls this week's economic calendar,
  keeps the high-impact USD events that move XAUUSD (CPI, NFP, FOMC,
  PCE, PPI, GDP, jobless claims, Fed speakers), shows them in the user's
  local time, says whether now is inside a news blackout, writes
  xau/calendar.json for xau-risk, and lists new gold headlines tagged Fed,
  inflation, jobs, dollar, yields, geopolitics or central banks. Use when the
  user says "any news today", "what's on the calendar", "is there news",
  "when is NFP", "when is CPI", "gold news", "morning brief", "can I trade
  now or is there news".
argument-hint: "[calendar|next|now|headlines]"
---

# xau-news

Gold reacts hardest to US data and the Fed, because they move the dollar
and real yields. Spreads widen and stops get skipped around those minutes.
This skill gets the times right so xau-risk can keep the user out.

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py" calendar              # fetch the week -> xau/calendar.json
python3 "${CLAUDE_SKILL_DIR}/news.py" calendar --all-impacts
python3 "${CLAUDE_SKILL_DIR}/news.py" next                  # upcoming, with countdown
python3 "${CLAUDE_SKILL_DIR}/news.py" now                   # exit 0 = inside a blackout
python3 "${CLAUDE_SKILL_DIR}/news.py" headlines --hours 12
```

## Sources

- Calendar: the Forex Factory weekly feed,
  `https://nfs.faireconomy.media/ff_calendar_thisweek.json` (free, unofficial).
  If it fails, say so and point the user to forexfactory.com/calendar with
  the filter set to USD + high impact. Never make up an event or a time.
- Headlines: Yahoo Finance RSS for gold futures (GC=F) and Google News RSS for
  "gold price". Each item is shown once.

## Rules

- **Headlines are leads, not facts.** Before saying something happened, open
  the story. If it is paywalled, say so. Link every item.
- **No predictions.** Report the event, the forecast and the previous number.
  Never say which way gold will go on the release.
- Times are shown in the user's local time (`local_utc_offset_hours`).
  Releases are often at 08:30 New York time, which is 18:30 in the Maldives
  in winter and 17:30 in summer.
- Refresh the calendar each Monday; the feed covers one week.

## Morning brief

`calendar`, then `next`, then `headlines --hours 12`, then one short
paragraph: what is scheduled today and when the blackouts are, the 2-3
headlines that touch gold and which tag, and "nothing notable" when that is
the truth.

## Safety

- Education and tooling, not financial advice. Nothing here predicts gold or promises returns. Leveraged CFDs lose money fast.
- Demo first: `"paper": true` means a demo account. Switching to live is the user's own decision, in their own config.
- Nothing in this pack places an order. The user places every trade in MT5 themselves, after xau-risk passes it and they reply an explicit yes for that one trade.
- Every trade has a stop-loss. No averaging down, no moving a stop further away, no martingale, no grid.
- Never ask for, read or repeat MT5 passwords or investor passwords.
