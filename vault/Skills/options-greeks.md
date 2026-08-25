---
type: skill
name: options-greeks
---

# Options greeks

`place_option()` and marketbeast picked contracts and sent orders without computing a
single greek. Two 1-lots with the same premium can carry wildly different directional
exposure and nothing could tell them apart. A 0.15-delta contract and a 0.85-delta
contract are not the same trade.

```
greeks action=analyze symbol=SPY spot=580 strike=590 days=30 right=C premium=4.20
greeks action=iv      premium=4.20 spot=580 strike=590 days=30
greeks action=size    spot=580 strike=590 days=30 premium=4.20 risk=1000
```

`analyze` gives delta/gamma/vega/theta **per share and per contract**, solves IV from the
premium when you don't supply sigma, and flags low-delta lottery tickets, heavy theta
bleed, near-expiry gamma risk, and a mark that disagrees with the model.

## The number that matters

**`delta_shares`** — the equivalent stock exposure. That's what to size against, not the
contract count. 6 contracts at 0.35 delta is 210 shares of directional risk; the "6"
tells you nothing on its own.

`action=size` turns a dollar risk budget into a contract count and then tells you what
stock exposure it quietly bought.

## Conventions

These differ between sources, so they're pinned here:

| | |
|---|---|
| theta | per calendar **day**, not per year |
| vega | per **1 vol point** (20% → 21%), not per 1.0 |
| rho | per 1 rate point |
| T | years — `days / 365` |
| contract | **100 shares** — the classic sizing error |

## Why no library

The model is ~60 lines of stdlib maths, and a dependency that fails to install on Windows
costs more than it saves. Validated against properties rather than numbers someone typed:
put-call parity, delta parity, IV round-trip across strikes/vols/rights, greek bounds and
signs, and monotonicity in spot and vol. 36 tests.

`marketcalls/opengreeks` (Rust core, 5-180x faster) and `ArturSepp/VanillaOptionPricers`
(Numba, whole-chain) are indexed if you ever need to price a full chain at once.
