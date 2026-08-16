---
type: skill
name: why-not-docker
---

# Why we parked Docker, n8n, and Postiz

They are real tools. They are the wrong *next* tool.

## Docker compose in this repo
The file starts LiteLLM, n8n, Whisper, Piper, Stirling. Super Jarvis already has:
- Grok STT/TTS (no Whisper/Piper containers)
- local PDF extract (no Stirling required)
- autonomy jobs (no n8n required)
- content drafts in the vault (no Postiz required)

Those containers publish extra ports. Default Compose binds `0.0.0.0`, which punches a hole in fortress. If you ever start them, ports are pinned to `127.0.0.1` now.

## n8n
A visual workflow box for *other people's* SaaS. We already fire briefings, watchlist pulses, reminders, and confirm-gated publishes in-process. n8n earns its keep when there is a *specific* webhook (Shopify, a form, a CRM) — not as atmosphere.

## Postiz
A second app, second login stack, second database, for a social queue. Studio already drafts captions/blogs/listings. Live post still needs official OAuth + a confirm token. Adding Postiz before one official channel works is another control plane with nothing to queue.

## When we will turn them on
- **n8n**: you name a real trigger (“when this form lands, draft a listing”).
- **Postiz**: after one official network publishes with confirm, and you want a calendar UI.
- **Docker**: only to run *that* named service, loopback-bound.
