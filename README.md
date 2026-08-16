# jarvis-system

Super Jarvis for [rkenagy-ops](https://github.com/rkenagy-ops). The GitHub scaffold is now a running OS: Obsidian vault, multi-agent swarm, live web/X, GitHub tools, paper markets, autonomy, and optional open-source services.

Repo: https://github.com/rkenagy-ops/jarvis-system

## Quick start (no Claude, no Docker required)

```powershell
cd C:\Users\Rhett\jarvis-system
copy .env.example .env
.\start.ps1
```

Open http://127.0.0.1:8787 and paste `XAI_API_KEY` (https://console.x.ai) plus a GitHub PAT.

Open the **`vault/`** folder in [Obsidian](https://obsidian.md) with **File → Open vault**.

## What “unlocked the GitHub base” means

The original repo was a **scaffold**: CrewAI + Anthropic + Kimi + Supabase + Docker were required, and trading/memory/tools were stubs.

Those locks are off:

| Old restriction | Now |
|---|---|
| Must use Claude Code / Anthropic | SpaceXAI (`grok-4.6`) is the brain |
| Must run vLLM / Kimi | Optional LiteLLM fallback only |
| Memory only on Supabase | SQLite index + **Obsidian markdown vault** |
| Voice only Whisper/Piper containers | xAI STT/TTS + live realtime |
| MCP/tools only if Node/Docker up | Native tools always work |
| Trading skill was a README | Live quotes, RSI/MACD, paper broker |

**Still locked (on purpose):** live money. Paper is default. Live/large tickets need a confirm token. No silent brokerage.

## Obsidian

`vault/` is a real vault (daily notes, wikilinks, tags, graph). Jarvis reads/writes it.

Optional live-editor sync: [obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api) + `OBSIDIAN_API_URL` / `OBSIDIAN_API_KEY`.

## Open-source adapters (GitHub projects)

Work without the container; get richer if you start them.

| Project | Role |
|---|---|
| [Obsidian](https://obsidian.md) | Knowledge OS |
| [n8n](https://github.com/n8n-io/n8n) | `integrate n8n` + `N8N_WEBHOOK_URL` |
| [Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF) | PDF via `STIRLING_URL` or local `pypdf` |
| [Jellyfin](https://github.com/jellyfin/jellyfin) | `JELLYFIN_URL` |
| [Immich](https://github.com/immich-app/immich) | `IMMICH_URL` |
| [Postiz](https://github.com/gitroomhq/postiz-app) | `POSTIZ_URL` |
| Same-origin crawler | `integrate crawl` (crawl4ai fallback) |

```powershell
docker compose up -d
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
