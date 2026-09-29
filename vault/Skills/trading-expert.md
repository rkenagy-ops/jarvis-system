---
type: skill
name: trading-expert
---

# Trading expert loop (hunter + candles + journal)

Three pieces turn the desk into something that finds trades across the whole market,
reads the chart like a tape reader, and gets better from every trade it calls.

```
hunter action=last                         # latest universe pass: top longs, shorts, loading
hunter action=hunt                         # run a full pass now (thousands of names)
candles action=read symbol=NVDA            # candlestick patterns, graded by location + volume
candles action=radar symbol=NVDA           # breakout UP / breakdown DOWN, happening or loading
candles action=teach pattern=hammer        # what a pattern is and how it fails
setups action=scan symbol=NVDA             # named setups (longs, shorts, squeeze) + candle confirmation
setups action=plan symbol=NVDA setup=breakdown_20d risk=500
journal action=insights                    # what is paying, what is bleeding, rules learned
journal action=mistakes                    # recent losses that were avoidable, and why
journal action=daily                       # the end-of-day study session
```

## The loop

1. **Hunt** (bot-28, every 15 min): every liquid US stock ($5+, $20M+ daily dollar
   volume), both directions. Ranked by confidence x reward-to-risk x relative volume x
   breakout-radar agreement x **what the journal has learned**. Intraday it refreshes
   bars every 10 minutes so breakouts are seen while they happen.
2. **Log**: after the close, the top longs and shorts go into `forward_tracker` with
   the conditions they fired under (market regime, extension from the 20-day, relative
   volume, stop width, candle confirmation).
3. **Grade**: `forward_tracker` walks each one forward with the backtest's own engine.
4. **Study** (bot-29): `journal` post-mortems every closed signal. A clean loss is
   *cost of business*. These are named *mistakes*:
   - fought the market, chased an extension (>2 ATR from the 20-day),
   - light-volume breakout, ignored an opposing candle,
   - stop inside the noise (<1 ATR), reward under 1.5R, dead money.
5. **Adapt**: expectancy by setup and by condition becomes ranking multipliers (shrunk
   toward neutral until the sample is real). Conditions that keep losing become rules;
   ones that keep winning become edges. Lessons land in `Markets/Lessons/` and memory.

## Reading candles

A pattern is only as good as where it forms. A hammer at support after a pullback, on
heavy volume, with the 50-day rising, is a strong read. The same hammer mid-range is
noise. Every pattern is scored for location, volume and trend alignment.

## Breakouts, up or down

Real breakouts close outside the 20-day range on 1.5x+ relative volume and hold the next
day. A close back inside the range is a failed breakout - flip bias or stand aside.
Coiled names (Bollinger squeeze, NR7, inside bar) sitting on a 20-day extreme are the
"loading" list, with trigger and stop levels ready.

## Guardrails that do not change

Aggressive means selective and decisive. The risk governor's daily loss limit, the
confirm token on live orders and `IBKR_LIVE` gating are untouched. Nothing here places
an order.

Related: [[market-setups]], [[learning-loop]], [[markets-desk]].
