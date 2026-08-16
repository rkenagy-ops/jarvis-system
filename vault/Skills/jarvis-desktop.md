---
type: skill
name: jarvis-desktop
---

# Best of GitHub Jarvis

We did not clone their stacks. We stole the qualities that make a room assistant feel alive.

| Quality | From | In Super Jarvis |
|---|---|---|
| Third person in the room / rolling context | isair/jarvis | `app/room.py`, wake word hears every line |
| Secret redaction before disk | isair/jarvis | `app/redact.py` |
| Always-on time + place | isair, kishan, Gaurav | `desktop.situation` + local/UTC |
| Wake word anywhere in the sentence | isair, llm-guy | HUD WAKE |
| Open website / YouTube / maps | Gaurav, kishan, Bolisetty | `desktop` |
| Launch apps (whitelist) | kishan, Gladiator07 | `desktop.open_app` |
| Google search | kishan | `desktop.google` |
| Screenshot | kishan, Gaurav | `desktop.screenshot` |
| Notes + reminders + plan the day | ethanplusai | `desktop.note` / `remind` / `plan_day` |
| Jokes + greeting | kishan, Gaurav | `desktop.joke` + `skills.greeting` |
| Email draft (no silent send) | Gaurav | `desktop.email_draft` |
| System vitals | Gaurav (psutil) | `desktop.sysinfo` |
| Plugin/skill catalog | Dipeshpal, Melissa-Core, JARVIS-on-Messenger | `app/skills.py` |
| Voice → LLM → HUD | AlexandreSajus, ethanplusai | existing live voice |
| Privacy-first local option | Priler/jarvis, isair | free_brain + local vault |

Skipped on purpose: unofficial WhatsApp, face-ID login, unrestricted shell, YouTube download, live money/social without a confirm token.
