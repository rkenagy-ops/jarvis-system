---
type: skill
name: trust-grants
---

# Standing grants — confirm tokens without the nag

Every live action needs a confirm_token. Right for the first live order, tiresome by
the twentieth — and that's the danger, because reflex-confirming is when the gate
stops protecting anything.

A grant pre-authorizes a **narrow, bounded, expiring** slice. It does not remove the gate.

```
trust action=grant kind=ibkr_stock symbols=SPY,QQQ max_notional=500 max_uses=5 minutes=60
trust action=status                  # what's live right now
trust action=check kind=ibkr_stock   # would this be covered?
trust action=audit                   # every decision, both ways
trust action=revoke all_grants=true  # kill everything, one call
```

## What makes it safe

| Property | How |
|---|---|
| **Bounded** | Hard expiry, use count, order-value cap — clamped in code (`MAX_TTL_SEC` 12h, `MAX_USES` 25, `MAX_NOTIONAL` 25k). Asking for more silently gets the ceiling. |
| **Narrow** | One `kind` per grant. No wildcard. An `ibkr_stock` grant does nothing for options. |
| **Audited** | Every decision hits `trust_audit` — auto-approved, fell through to confirm, or denied. An auto-approved live order leaves the same trail as a confirmed one. |
| **Revocable** | `all_grants=true` kills everything instantly. |

**Default is zero grants** — byte-for-byte the old behaviour. Trust is switched on
deliberately, for a while, on purpose.

## Deliberate exclusions

- **`oss_install` can never carry a grant.** It runs fetched setup code beside your
  brokerage credentials. Always confirms.
- **Money grants always get a value cap.** Ask for an `ibkr_*` grant with no
  `max_notional` and you get 500.
- **Unpriceable orders never auto-approve.** A market order has no price, so the cap
  can't be applied — unpriceable is not the same as within budget, so it goes to a human.
- **Option notional counts the ×100 multiplier.** A 3.00 contract is 300 of exposure.
- **`trust` is gated to jarvis and trader.** It mints authorizations for live orders;
  it isn't a tool every specialist should reach.
