---
type: skill
name: fortress
---

# Fortress — how Super Jarvis stays private

You need the **internet outbound**. You do **not** need Jarvis inbound.

| Traffic | Need it? | Why |
|---|---|---|
| Out to `api.x.ai` | Yes, for Grok | Brain, voice, imagine |
| Out to GitHub / Yahoo / weather | Yes | Tools |
| In from LAN / internet to `:8787` | **No** | Vault, keys, trades, memory |

## The right setup

1. Bind **127.0.0.1 only** (`JARVIS_HOST=127.0.0.1`). Default.
2. HUD token auto-saved to `.env` as `JARVIS_TOKEN`. Browser on this PC bootstraps it. Nothing else can.
3. Host header must be localhost. Random `Host:` is 403.
4. Fetch/crawl refuse loopback, RFC1918, link-local, cloud metadata.
5. OpenAPI docs are off.

## VPN

Use a VPN on this PC when you are on **coffee-shop / hotel Wi-Fi**. It encrypts *your* outbound path (Grok, GitHub).

A VPN is **not** a substitute for loopback bind. Do not port-forward 8787 “through the VPN.” Do not set `JARVIS_HOST=0.0.0.0`.

Phone access later = Tailscale to this machine **plus** the token **plus** still no public port. Not now.

## Offline

`JARVIS_OFFLINE=true` — Grok stays dark, free-brain only. Use if you want zero cloud. The HUD still stays local.

## Never

- ngrok / Cloudflare tunnel the HUD
- `0.0.0.0` without a damn good reason
- Share `JARVIS_TOKEN`, `XAI_API_KEY`, or `GITHUB_TOKEN`
