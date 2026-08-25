"""Curated index of repos worth pulling — the discovery source that needs no credentials.

learning.cycle() used to depend entirely on GitHub's search API, which requires an
authenticated token. With no token every topic failed and the cycle reported "nothing
new to learn" — indistinguishable from actually being up to date. This index is the
primary source now; search is optional enrichment on top.

Two kinds of entry:

  HUBS      awesome-lists — indexes of indexes. Pull these first: they are small, and
            they point at far more than we could hand-curate here.
  INDEX     specific repos, each with what capability it actually adds to Jarvis.

Fetching only needs codeload.github.com, which is unauthenticated — so everything
here works with zero keys configured.
"""

from __future__ import annotations

from typing import Any

# Awesome-lists: cheap to ingest, and each one is a map of its whole field.
HUBS: list[dict[str, str]] = [
    {"repo": "wilsonfreitas/awesome-quant", "why": "The quant finance index — libraries, data sources, backtesters."},
    {"repo": "paperswithbacktest/awesome-systematic-trading", "why": "Systematic trading: backtest engines, live frameworks, papers with code."},
    {"repo": "wangzhe3224/awesome-systematic-trading", "why": "Second systematic-trading index; overlaps the above but catches different tools."},
    {"repo": "public-apis/public-apis", "why": "Free public APIs by category — the fastest way to find a data source."},
    {"repo": "e2b-dev/awesome-ai-agents", "why": "Agent frameworks, tooling and infrastructure."},
    {"repo": "sindresorhus/awesome", "why": "Root index of every other awesome-list."},
    {"repo": "punkpeye/awesome-mcp-servers", "why": "MCP servers by category — mcp_config.json only wires three."},
]

# repo -> what it actually buys Jarvis. priority 1 = pull first.
INDEX: list[dict[str, Any]] = [
    # --- brokerage / execution -------------------------------------------------
    {
        "repo": "ib-api-reloaded/ib_async",
        "category": "trading",
        "priority": 1,
        "why": "The maintained IBKR client. ib_insync — which app/ibkr.py imports — is archived; this is its successor and the same API surface.",
    },
    {
        "repo": "alpacahq/alpaca-py",
        "category": "trading",
        "priority": 2,
        "why": "Official Alpaca SDK. app/broker.py already talks to Alpaca by hand.",
    },
    {
        "repo": "Polymarket/py-clob-client",
        "category": "prediction_markets",
        "priority": 2,
        "why": "Official Polymarket CLOB client — the reference for order mechanics poly.py currently only reasons about.",
    },
    {
        "repo": "ccxt/ccxt",
        "category": "trading",
        "priority": 3,
        "why": "Unified interface across 100+ crypto exchanges. The canonical example of normalising many broker APIs into one.",
    },
    # --- market data / research ------------------------------------------------
    {
        "repo": "OpenBB-finance/OpenBB",
        "category": "market_data",
        "priority": 1,
        "why": "Broadest open financial data toolkit — equities, options, macro, and a clean provider abstraction worth copying.",
    },
    {
        "repo": "ranaroussi/yfinance",
        "category": "market_data",
        "priority": 1,
        "why": "Already a dependency. markets.py hand-rolls Yahoo chart parsing that this handles.",
    },
    {
        "repo": "bukosabino/ta",
        "category": "market_data",
        "priority": 2,
        "why": "Technical indicators on pandas. setups.py hand-computes ATR/RSI/MACD — this is the reference implementation.",
    },
    {
        "repo": "xgboosted/pandas-ta-classic",
        "category": "market_data",
        "priority": 3,
        "why": "250+ indicators, maintained fork of pandas-ta with TA-Lib as an accuracy oracle.",
    },
    # --- backtesting -----------------------------------------------------------
    {
        "repo": "polakowo/vectorbt",
        "category": "backtesting",
        "priority": 1,
        "why": "Numba-accelerated vectorised backtesting. The missing half of setups.py — plans are generated but never validated against history.",
    },
    {
        "repo": "pmorissette/bt",
        "category": "backtesting",
        "priority": 3,
        "why": "Flexible strategy-tree backtesting; simpler mental model than vectorbt.",
    },
    {
        "repo": "freqtrade/freqtrade",
        "category": "backtesting",
        "priority": 3,
        "why": "A complete production trading bot — worth reading end to end for how it structures strategy, risk and live execution.",
    },
    # --- agent orchestration ---------------------------------------------------
    {
        "repo": "langchain-ai/langgraph",
        "category": "agents",
        "priority": 1,
        "why": "Stateful graph orchestration with checkpointing and interrupts. Directly relevant to brain._handle_spawn, which is a flat thread pool with no resume.",
    },
    {
        "repo": "pydantic/pydantic-ai",
        "category": "agents",
        "priority": 1,
        "why": "Type-safe agents with structured outputs — the pattern for making tool arguments validated instead of hand-parsed.",
    },
    {
        "repo": "openai/openai-agents-python",
        "category": "agents",
        "priority": 2,
        "why": "Handoffs and guardrails as primitives; small enough to read in one sitting.",
    },
    {
        "repo": "crewAIInc/crewAI",
        "category": "agents",
        "priority": 2,
        "why": "Role-based crews — the closest published analogue to the specialist roster in agents.py.",
    },
    {
        "repo": "google/adk-python",
        "category": "agents",
        "priority": 3,
        "why": "Reference implementation for wrapping sub-agents as tools.",
    },
    # --- memory / retrieval ----------------------------------------------------
    {
        "repo": "mem0ai/mem0",
        "category": "memory",
        "priority": 1,
        "why": "Long-term memory with extraction and consolidation — memory.py stores but never consolidates.",
    },
    {
        "repo": "run-llama/llama_index",
        "category": "retrieval",
        "priority": 1,
        "why": "The mature RAG toolkit: chunking, hybrid retrieval, rerankers. rag.py is a single naive embed-and-cosine pass.",
    },
    {
        "repo": "deepset-ai/haystack",
        "category": "retrieval",
        "priority": 2,
        "why": "Pipeline-shaped RAG; good source for retrieval evaluation patterns.",
    },
    {
        "repo": "lancedb/lancedb",
        "category": "memory",
        "priority": 2,
        "why": "Embedded vector store with no server — fits the local-first, single-SQLite design already in use.",
    },
    {
        "repo": "explodinggradients/ragas",
        "category": "retrieval",
        "priority": 3,
        "why": "Measures whether retrieval actually improved. eval.py currently scores nothing about the RAG path.",
    },
    # --- model plumbing --------------------------------------------------------
    {
        "repo": "BerriAI/litellm",
        "category": "agents",
        "priority": 1,
        "why": "One interface over 100+ providers with retry and fallback. Already in litellm_config.yaml but not used from Python.",
    },
    {
        "repo": "Arize-ai/phoenix",
        "category": "observability",
        "priority": 2,
        "why": "Self-hosted trace UI for agent runs — replay every tool call offline. Nothing currently traces the swarm.",
    },
    # --- extraction ------------------------------------------------------------
    {
        "repo": "unclecode/crawl4ai",
        "category": "scraping",
        "priority": 1,
        "why": "LLM-shaped extraction. opensource.crawl() is regex tag-stripping, which loses structure.",
    },
    {
        "repo": "adbar/trafilatura",
        "category": "scraping",
        "priority": 2,
        "why": "Best-in-class main-content extraction; already a dependency.",
    },
    {
        "repo": "microsoft/markitdown",
        "category": "scraping",
        "priority": 2,
        "why": "Anything (pdf, docx, xlsx, pptx) to markdown — one path for every document extract.py handles separately.",
    },
    # --- data ------------------------------------------------------------------
    {
        "repo": "pola-rs/polars",
        "category": "data",
        "priority": 2,
        "why": "Fast dataframes without the pandas footprint.",
    },
    {
        "repo": "duckdb/duckdb",
        "category": "data",
        "priority": 2,
        "why": "SQL over local files — a better analytics path than hand-written SQLite queries.",
    },
    # --- voice -----------------------------------------------------------------
    {
        "repo": "SYSTRAN/faster-whisper",
        "category": "voice",
        "priority": 2,
        "why": "4x faster local STT. voice_live.py has no local fallback when the realtime socket drops.",
    },
    # --- scheduling ------------------------------------------------------------
    {
        "repo": "agronholm/apscheduler",
        "category": "scheduling",
        "priority": 1,
        "why": "autonomy.py is a hand-rolled time.sleep beat loop: a job due while Jarvis is off is simply missed, and nothing survives a restart. This is the reference for persistent, misfire-aware scheduling.",
    },
    {
        "repo": "rq/rq",
        "category": "scheduling",
        "priority": 3,
        "why": "Simple durable job queue — the pattern for work that must outlive the process that queued it.",
    },
    # --- social ----------------------------------------------------------------
    {
        "repo": "MarshalX/atproto",
        "category": "social",
        "priority": 1,
        "why": "Bluesky SDK. engage.py has no Bluesky adapter, and Bluesky is the easiest fully-official auto-reply network to add.",
    },
    {
        "repo": "tweepy/tweepy",
        "category": "social",
        "priority": 2,
        "why": "X SDK. xpost.py hand-signs OAuth1 with hmac/base64 — this is the maintained version of that code.",
    },
    {
        "repo": "halcy/Mastodon.py",
        "category": "social",
        "priority": 3,
        "why": "Mastodon client; another network with a real reply API and no gatekeeping.",
    },
    # --- automation ------------------------------------------------------------
    {
        "repo": "n8n-io/n8n",
        "category": "automation",
        "priority": 1,
        "why": "Workflow automation. config.status() already reports an n8n flag with nothing behind it.",
    },
    {
        "repo": "windmill-labs/windmill",
        "category": "automation",
        "priority": 2,
        "why": "Scripts-as-workflows with a job runner — closer to how the bot roster actually works than n8n's node graph.",
    },
    {
        "repo": "pywinauto/pywinauto",
        "category": "automation",
        "priority": 2,
        "why": "Windows UI automation done properly. desktop.py drives apps by launching executables and guessing.",
    },
    {
        "repo": "ollama/ollama-python",
        "category": "agents",
        "priority": 2,
        "why": "Official Ollama client. ollama.py talks to it over raw httpx and re-implements the streaming protocol.",
    },
    # --- options ---------------------------------------------------------------
    {
        "repo": "vollib/py_vollib",
        "category": "options",
        "priority": 1,
        "why": "Black-Scholes greeks and implied vol. place_option and marketbeast trade options without computing a single greek — no delta, no IV, no way to size by risk.",
    },
    {
        "repo": "lballabio/QuantLib",
        "category": "options",
        "priority": 3,
        "why": "The full derivatives library. Heavy, but the reference for anything py_vollib cannot price.",
    },
    {
        "repo": "marketcalls/opengreeks",
        "category": "options",
        "priority": 2,
        "why": "Rust core with a Python API, 5-180x faster than vollib, actively maintained. Worth swapping app/greeks.py for if a whole chain ever needs pricing at once.",
    },
    {
        "repo": "ArturSepp/VanillaOptionPricers",
        "category": "options",
        "priority": 3,
        "why": "Numba-vectorised greeks and IV fits over NumPy arrays - the pattern for pricing a full chain rather than one contract at a time.",
    },
    # --- systems close enough to Jarvis to steal from --------------------------
    {
        "repo": "HKUDS/Vibe-Trading",
        "category": "trading",
        "priority": 1,
        "why": "A personal trading agent with backtesting and multi-agent orchestration - the nearest published thing to what Jarvis is trying to be on the trading side.",
    },
    {
        "repo": "HKUDS/nanobot",
        "category": "agents",
        "priority": 1,
        "why": "Self-hosted personal AI agent framework: WebUI, memory, MCP, multi-agent, workflow automation. Structurally the closest analogue to Jarvis itself.",
    },
    {
        "repo": "Panniantong/Agent-Reach",
        "category": "social",
        "priority": 1,
        "why": "Reads and searches Twitter, Reddit, YouTube and GitHub without API fees. Directly addresses engage.py's hard limit - no official API means no feed to read.",
    },
    {
        "repo": "lsdefine/GenericAgent",
        "category": "automation",
        "priority": 2,
        "why": "Self-evolving agent with a skill tree and real desktop/computer control - the direction desktop.py's pywinauto layer could grow in.",
    },
    {
        "repo": "leon-ai/leon",
        "category": "interface",
        "priority": 3,
        "why": "Long-running open-source personal assistant with offline speech in and out; useful reference for voice_live.py.",
    },
    # --- risk ------------------------------------------------------------------
    {
        "repo": "dcajasn/Riskfolio-Lib",
        "category": "risk",
        "priority": 1,
        "why": "Portfolio risk and allocation. ibkr.pnl() reports positions but nothing measures concentration, correlation or drawdown.",
    },
    {
        "repo": "ranaroussi/quantstats",
        "category": "risk",
        "priority": 2,
        "why": "Sharpe, drawdown, tear sheets — turns a trade log into an honest performance report.",
    },
    # --- persistent interface --------------------------------------------------
    {
        "repo": "zauberzeug/nicegui",
        "category": "interface",
        "priority": 1,
        "why": "Python-native UI that can run in a real native window rather than a browser tab. The HUD is currently a FastAPI page you have to keep open at 127.0.0.1:8787 — this is the path to something always-on.",
    },
    {
        "repo": "r0x0r/pywebview",
        "category": "interface",
        "priority": 2,
        "why": "Wraps the existing web HUD in a native window with a tray icon — the smallest change that makes it persistent.",
    },
    # --- event-driven triggers -------------------------------------------------
    {
        "repo": "gorakhargosh/watchdog",
        "category": "automation",
        "priority": 1,
        "why": "Filesystem events. autonomy.beat() polls on a timer, so a vault edit or a dropped file is noticed on the next tick rather than when it happens.",
    },
    # --- security --------------------------------------------------------------
    {
        "repo": "gitleaks/gitleaks",
        "category": "security",
        "priority": 1,
        "why": "Secret scanning. The repo already has a .gitleaksignore but nothing runs gitleaks, and .env holds brokerage credentials.",
    },
    {
        "repo": "Yelp/detect-secrets",
        "category": "security",
        "priority": 2,
        "why": "Pre-commit secret detection — stops a key reaching a commit rather than finding it afterwards.",
    },
]


def by_category() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for entry in INDEX:
        out.setdefault(entry["category"], []).append(entry)
    for rows in out.values():
        rows.sort(key=lambda r: r["priority"])
    return out


def for_topic(topic: str) -> list[dict[str, Any]]:
    """Indexed repos for one topic, most important first."""
    key = (topic or "").strip().lower()
    rows = [e for e in INDEX if e["category"] == key]
    rows.sort(key=lambda r: r["priority"])
    return rows


def all_repos() -> list[str]:
    return [h["repo"] for h in HUBS] + [e["repo"] for e in INDEX]


def categories() -> list[str]:
    return sorted({e["category"] for e in INDEX})


def summary() -> dict[str, Any]:
    grouped = by_category()
    return {
        "ok": True,
        "hubs": HUBS,
        "categories": {k: len(v) for k, v in sorted(grouped.items())},
        "total_repos": len(all_repos()),
        "priority_1": [e["repo"] for e in INDEX if e["priority"] == 1],
        "note": "Fetching uses unauthenticated codeload, so the whole index pulls with no keys set.",
    }
