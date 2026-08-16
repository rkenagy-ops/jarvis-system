Trading skill

This folder documents how the trading repositories plug into jarvis-system as one optional skill for the Trading Skill Agent defined in orchestrator.py.

Repositories used

ccxt provides a common interface to many crypto exchanges for data and order placement. freqtrade and hummingbot are full trading bot frameworks for strategy execution and market making. nautilus_trader and backtrader provide event-driven backtesting and live trading infrastructure. vectorbt is used for fast vectorized backtesting and research. FinRL and TradingAgents provide reinforcement learning and LLM-native multi-agent trading research frameworks. lumibot offers a simpler strategy and backtesting API. py-clob-client connects to Polymarket's central limit order book.

How it plugs in

The Trading Skill Agent can use these libraries for analysis, backtesting, and generating recommendations. It should default to TRADING_MODE=paper from your .env file for anything resembling live execution.

Safety requirement

This skill must never place a real order, transfer funds, or change exchange account settings without a human explicitly confirming that specific action in the moment. The confirm_action helper in orchestrator.py exists for exactly this purpose; any code path that reaches a live exchange call must go through it, and TRADING_REQUIRE_CONFIRMATION should stay set to true unless you have deliberately decided otherwise and understand the risk.

Suggested first step

Wire up one exchange in paper trading mode through ccxt, have the Trading Skill Agent produce a written recommendation, and manually review several of its recommendations before ever letting it touch a funded account.
