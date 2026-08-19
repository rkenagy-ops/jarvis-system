# jarvis-system

Super Jarvis **5.8.2** for [rkenagy-ops](https://github.com/rkenagy-ops). This repo **is** the OS — do not GitHub-Import a second copy.

Local HUD: [http://127.0.0.1:8787](http://127.0.0.1:8787) (fortress / loopback only).

## Quick start

```powershell
cd C:\Users\Rhett\jarvis-system
copy .env.example .env
.\start.ps1
```

Or after install: Windows logon task `SuperJarvis` (`install-startup.ps1` / `serve.ps1`).

Paste `XAI_API_KEY` from [console.x.ai](https://console.x.ai). GitHub is `gh auth login` (account **rkenagy-ops**) or a `repo` PAT in KEYS.

Open **`vault/`** in [Obsidian](https://obsidian.md) → File → Open vault.

## What it is now

| Layer | Running |
|---|---|
| Brain | SpaceXAI `grok-4.6` → Ollama `llama3.1:8b` → free APIs |
| Voice | Eve + `grok-voice-think-fast-2.0` (short excerpt, no double-speak) |
| Knowledge | Obsidian vault + SQLite FTS + local embeddings |
| Calendar / mail | Microsoft Graph (device login) |
| Markets | Yahoo desk + **MarketBeast v9** (D:\MARKETBEAST vendored) |
| Brokerage | IBKR TWS **persistent session** (`app/ibkr.py` adapter `persistent-tws-2026`). Live **7496**, paper **7497**. Live orders need a **confirm token**. Optional Alpaca. |
| Autonomy | Briefing, watchlist, calendar sync, weekly backup, MarketBeast scan, self-upgrade |
| HUD | Animated living orb (5.7+), Grow chip |

**Still gated:** real cash. `IBKR_LIVE=true` + live TWS + confirm token. No silent fills.

## GitHub

Canonical repo: **https://github.com/rkenagy-ops/jarvis-system**

Do **not** use GitHub *Import repository*. Clone this repo; copy `.env` privately to another PC.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Fortress

Bind `127.0.0.1` only. Do not port-forward 8787. Docker compose (if ever used) is also loopback-pinned.
