---
type: skill
name: markets-desk
---

# News + markets desk + brokerage

Public Yahoo + RSS: indices, sectors, mega-caps, FX, metals/energy, large crypto. Not every dark pool.

Live fills:
- Official **Alpaca** (stocks) — keys in HUD. `ALPACA_LIVE=false` is paper.
- Official **IBKR** via TWS/IB Gateway on `127.0.0.1` (paper 7497 / live 7496). `IBKR_LIVE=true` + confirm token for real cash. No silent live money.

Call ideas: MarketBeast = HyperTrader `scanner.py` at `MARKETBEAST_ROOT`. HUD **Best calls** runs the liquid (up-to-the-minute) pass. `universe=full` is the 250-name scan (~2–3 min). Signals only until you confirm an IBKR order.
