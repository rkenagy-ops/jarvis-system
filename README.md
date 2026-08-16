jarvis-system

Integrated multi-agent, Jarvis-style assistant scaffold. This repo wires together several open-source projects into one system that Claude Code can drive.

Architecture

The brain is the Kimi-K3 model, served via vllm and exposed through litellm as a unified LLM gateway so any agent can call it, or fall back to a hosted model, through one API. Multi-agent orchestration uses CrewAI by default, with autogen-import available as an alternative; agents are defined in orchestrator.py. The tool layer comes from MCP servers in mcp-servers-import, which give Claude Code and the agents standardized access to tools such as browser-use, crawl4ai, filesystem access, and n8n workflows. Memory runs on Supabase, using Postgres plus pgvector for structured facts and semantic RAG memory. Voice I/O comes from whisper-cpp-import for speech to text and piper-tts-import for text to speech. Skills include trading, using ccxt, freqtrade, hummingbot, nautilus_trader, FinRL, lumibot, vectorbt, backtrader, py-clob-client, and TradingAgents, plus calendar via cal.diy, documents via Stirling-PDF, media via jellyfin and immich, social via postiz-app, and automation via n8n.

Directory layout

README.md is this file. docker-compose.yml starts litellm, n8n, the whisper server, and the piper server. requirements.txt lists python dependencies for the orchestrator. .env.example should be copied to .env with your own keys; never commit real secrets. mcp_config.json tells Claude Code which MCP tool servers to load. orchestrator.py holds the CrewAI multi-agent setup, the core Jarvis loop. skills/trading/README.md explains how the trading repos plug in as one skill. launch.sh and launch.bat are one command start scripts.

Prerequisites

You will need Docker and Docker Compose, Python 3.10 or newer, the Claude Code CLI installed and signed in, an Anthropic API key, and optionally your own vllm plus Kimi-K3 deployment if you want a self-hosted brain. Add API keys for any tools you want active, such as n8n or trading exchanges, to your own .env file; never share or commit them.

Setup

Clone this repository to your machine, then copy .env.example to .env and fill in your own keys. Run docker compose up -d to start the supporting services. Install python dependencies with pip install -r requirements.txt. Point Claude Code at mcp_config.json so it can see the MCP tool servers. Finally, run python orchestrator.py to start the agent crew.

Trading skill safety

The trading skill in skills/trading is intentionally stubbed so that it requires explicit manual confirmation before placing any real order. It never executes live trades on its own.

Status

This is a working scaffold, not a finished production system. Review every config file, use paper trading or test accounts first, and only connect real credentials once you understand what each piece does.
