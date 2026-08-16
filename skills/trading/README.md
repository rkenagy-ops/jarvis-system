# Trading skill

Live desk is `app/markets.py`, exposed as the `market` tool and `/api/markets*`.

## What is wired

- Quotes and daily history: Yahoo Finance (public), CoinGecko fallback for BTC/ETH/SOL
- Analysis: SMA20/50, RSI14, MACD, 20-day realized vol, 20-day high/low, trend
- Watchlist pulse every 15 minutes via autonomy (`watchlist-scan`)
- Paper broker in SQLite: cash, positions, fills
- Confirm tokens for live mode and large paper tickets (>= $25k)

## Safety

`TRADING_MODE=paper` is the default. Live mode never silently fills a brokerage order. It issues a `confirm_token`. `confirm_trade` still records a **paper** fill until a real broker (Alpaca, etc.) is connected. No path places an exchange order by itself.

`TRADING_REQUIRE_CONFIRMATION` should stay `true`.

## Owner usage

Ask Jarvis: "Analyze NVDA and paper-buy 5 if RSI < 70."  
Or hit `POST /api/markets/trade` then `POST /api/markets/confirm` with the token.

## Optional research stack

The original libraries (ccxt, freqtrade, vectorbt, backtrader, FinRL, lumibot, nautilus_trader) remain optional research tools. They are not auto-imported. Do not attach funded keys until you have reviewed paper results.
