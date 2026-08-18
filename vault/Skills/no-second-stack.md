---
type: skill
name: no-second-stack
---

# Do not install a second Jarvis

Evaluated 2026-08-18. Same rule as Docker / n8n / Postiz / OpenHands.

| Project | Install? | Why |
|---|---|---|
| **OpenCode** | No | Second coding agent. We already use Grok CLI + this HUD. Optional later if Rhett wants a dedicated TUI — not inside Super Jarvis. |
| **Open WebUI** | No | Second chat HUD + RAG + Ollama UI. Duplicates fortress, vault, swarm. Extra port. |
| **ComfyUI** | No | Local Stable Diffusion workstation. Needs a GPU. This box is CPU / 16 GB RAM. Image gen stays Grok Imagine. |
| **Vane** | Steal only | Local Perplexity clone (SearxNG + LLM). We already have Grok `web_search` + vault RAG. Do not add SearxNG Docker. |
| **Meetily** | Later, as an app | Only *new* job: live meeting minutes. Separate desktop app. If we add it, run it standalone and drop transcripts into `vault/Meetings/`. Do not embed Rust/Whisper into the HUD. |
| **AgenticSeek** | No | Full second Manus/Jarvis (browser + code + voice + UI). Clone of us. |
| **Duix.Avatar** | No | Offline talking-head video. Heavy GPU toolkit. Voice + Imagine already cover presence. |

Ingest READMEs into `Sources/github/`. Absorb workflows. Do not clone stacks.
