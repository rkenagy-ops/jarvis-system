---
type: skill
name: ibkr-marketbeast
---

# IBKR + MarketBeast

MarketBeast is the HyperTrader scanner in OneDrive (`scanner.py --best`).

1. **TWS must be logged in**, not sitting on the Login window. The API socket does not exist until TWS is fully loaded.
2. Enable API: Edit → Global Configuration → API → Settings → Enable ActiveX and Socket Clients. Socket port **7496 live / 7497 paper**. Trusted IP `127.0.0.1`.
3. HUD pill **IBKR LOGIN** = finish username/password/2FA. **IBKR API OFF** = TWS running but socket closed. **IBKR LIVE** = port 7496 is listening.
5. HUD **IBKR account** then reads net liq / positions.
6. **Best calls** runs the liquid v9 pass **in parallel**, then grades A/B/C/WATCH (spread, OI, delta). TWS overlays live mids when open.
7. Only **A/B** are `buyable`. Paper-ticket those, or send **live** via TWS 7496.
8. Live: KEYS `IBKR_LIVE=true`, log into **live** TWS port **7496**. Jarvis keeps a **persistent TWS session** (`app/ibkr.py`, adapter `persistent-tws-2026`). Returns a `confirm_token` — say **confirm**. It will not silently fill.

Do not paste IBKR usernames/passwords into Jarvis. Official socket API only.

Desk: `market action=advise` is the analyst briefing (tape, sectors, VIX, news, graded calls, IBKR permissions). Live tickets: `market action=ibkr mode=option|order|ticket` then `confirm`. HUD **Desk advise** does not send an order.
