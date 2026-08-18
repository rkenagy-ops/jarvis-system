---
type: skill
name: ibkr-marketbeast
---

# IBKR + MarketBeast

MarketBeast is the HyperTrader scanner in OneDrive (`scanner.py --best`).

1. Log into **TWS or IB Gateway**. Enable API. Trusted IP `127.0.0.1`. Paper port **7497**.
2. HUD **IBKR account** reads net liq / positions.
3. **Best calls** runs the liquid MarketBeast pass (watchlist + mega names).
4. To buy: tell Jarvis the strike/expiry. Paper TWS can send the order. Live TWS (`IBKR_LIVE=true`, port 7496) returns a **confirm token** — no silent live options.

Do not paste IBKR usernames/passwords into Jarvis. Official socket API only.
