---
type: skill
name: market-setups
---

# Setups: detect → understand → size

`market action=advise` gives ENTER/NO-GO. `setups` answers the other question:
**which setup is this, why does it work, and what would a defined-risk trade look like.**

```
setups action=scan  symbol=AAPL                        # what's live right now
setups action=teach setup=trend_pullback               # what it is, how it fails
setups action=plan  symbol=AAPL setup=breakout_20d risk=500
```

`plan` returns entry / stop / target, the R multiple, and a share count sized off
your dollar risk — plus the exact `market action=ibkr mode=bracket ...` line to send it.

| Setup | Needs | Dies when |
|---|---|---|
| `trend_pullback` | above 50d, tagging 20d, RSI 38-58 | close below the 50d |
| `breakout_20d` | close above the 20-day high | close back inside the range |
| `oversold_in_uptrend` | RSI < 35 **and** above the 50d | loses the 50d |
| `momentum_cross` | MACD over signal, above 50d | cross back down |
| `range_fade` | flat averages, price at a range edge | close outside the range |

Every plan carries `invalidation`, `fails_when`, and warnings when reward-to-risk is
under 2R or your risk budget can't afford one share. Levels come from daily bars —
they describe a structure with defined risk, not a prediction.

## Polymarket

```
poly action=explain                                   # the whole primer
poly action=explain topic=kelly
poly action=evaluate price=0.62 p=0.70 bankroll=1000  # work one market
```

The key point the primer makes: `bounce` has no model, and says so. Price *is* the
market's probability, so without your own number there is no edge to size. `evaluate`
is where you supply one — it shows the edge, the Kelly fraction, the stake, and refuses
to size anything inside a 3-point band because that's within your own error bar.

Live fills stay in your own wallet. Jarvis does not custody keys.
