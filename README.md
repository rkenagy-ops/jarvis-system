# jarvis-system

Super Jarvis for [rkenagy-ops](https://github.com/rkenagy-ops). Multi-agent swarm, unlocked shared memory, live web/X, GitHub on this account, and voice.

Repo: https://github.com/rkenagy-ops/jarvis-system

## Quick start

```powershell
cd C:\Users\Rhett\jarvis-system
copy .env.example .env
# put XAI_API_KEY and GITHUB_TOKEN in .env
.\start.ps1
```

Open http://127.0.0.1:8787 and paste keys under **KEYS** if needed.

- SpaceXAI key: https://console.x.ai
- GitHub PAT (`repo`, `read:user`): https://github.com/settings/tokens

## What runs

| Piece | Role |
|---|---|
| **J.A.R.V.I.S.** | Conductor |
| **ORACLE** | Live web + X research |
| **FORGE** | Code |
| **SENTINEL** | This GitHub account |
| **ARCHIVIST** | Long-term memory |
| **CRITIC** | Adversarial insight |
| **STRATEGIST** | Plans |
| **TRADER** | Paper analysis only — no live orders without confirm |

Voice: hold **MIC**, or **LIVE VOICE** for realtime speech-to-speech.

## Layout

```
app/                 Super Jarvis backend (SpaceXAI, memory, GitHub, voice)
web/                 HUD
tests/               pytest
orchestrator.py      Optional CrewAI CLI loop
docker-compose.yml   Optional litellm / n8n / whisper / piper
mcp_config.json      MCP servers for Claude Code / Grok
skills/trading/      Trading skill (confirmation required)
```

## Optional stack

```powershell
docker compose up -d
python orchestrator.py
```

CrewAI will use SpaceXAI when `XAI_API_KEY` is set, otherwise the local LiteLLM / Kimi gateway.

## Trading safety

`skills/trading` is stubbed. Paper mode is the default. No live order, transfer, or account change without an explicit human confirmation of that specific action.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
