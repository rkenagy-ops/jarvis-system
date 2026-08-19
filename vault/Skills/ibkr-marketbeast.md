---
type: skill
name: ibkr-marketbeast
---

# IBKR + MarketBeast

MarketBeast is the HyperTrader scanner in OneDrive (`scanner.py --best`).

1. Log into **TWS or IB Gateway**. Enable API. Trusted IP `127.0.0.1`. Paper port **7497**.
2. HUD **IBKR account** reads net liq / positions.
3. **Best calls** runs the liquid v9 pass **in parallel**, then grades A/B/C/WATCH (spread, OI, delta). TWS overlays live mids when open.
4. Only **A/B** are `buyable`. Paper-ticket those, or send **live** via TWS 7496.
5. Live: KEYS `IBKR_LIVE=true`, log into **live** TWS port **7496**. Jarvis keeps a **persistent TWS session** (`app/ibkr.py`, adapter `persistent-tws-2026`). Returns a `confirm_token` — say **confirm**. It will not silently fill.

Do not paste IBKR usernames/passwords into Jarvis. Official socket API only.
