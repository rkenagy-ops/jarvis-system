# Super Jarvis

Local multi-agent OS for Rhett. Python FastAPI + SpaceXAI (xAI) + GitHub.

Current version: **5.8.2**. Repo: https://github.com/rkenagy-ops/jarvis-system — this tree *is* the OS. Do not Import a second GitHub repo.

- Provider is SpaceXAI via `XAI_API_KEY` and `https://api.x.ai/v1`. Do not add OpenAI/Anthropic.
- Default model: `grok-4.6`. Live voice: `grok-voice-think-fast-2.0`. TTS voice: `eve` (composed, educated woman).
- Never commit `.env` or `data/`.
- GitHub access is `gh auth` or `GITHUB_TOKEN` for **rkenagy-ops**. Token is refreshed from the GitHub CLI when possible.
- Agents share one SQLite mind in `data/jarvis.db`. Do not silo memory.
- Knowledge source of truth is the Obsidian vault in `vault/`. Keep wikilinks and frontmatter.
- Trading: paper local book + official **IBKR TWS** (`app/ibkr.py`, persistent session, adapter `persistent-tws-2026`). Live TWS is port **7496**. Live stock/option orders require a **confirm token**. Optional Alpaca. Do not add unofficial brokers or silent live fills.
- MarketBeast engines from `D:\MARKETBEAST` live in `vendor/marketbeast/`. Jarvis runs v9 + Super Jarvis grades (A/B buyable).
- HUD is loopback-only. Never recommend `0.0.0.0` or port-forwarding 8787.
- Claude/Anthropic/Supabase/Kimi/CrewAI orchestrator are optional leftovers. Do not make them required again.
- Do not add jailbreak / safety-bypass features.
