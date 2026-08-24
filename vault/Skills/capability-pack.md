---
type: skill
name: capability-pack
---

# GitHub hunt → capability_pack

Searched GitHub for gaps vs "handle whatever Rhett asks." Ingested **READMEs**, not clones.

| Area | Repo | Use |
|---|---|---|
| IBKR | erdewit/ib_insync, ib-api-reloaded/ib_async | Already wired via TWS; playbook only |
| Markets | OpenBB-finance/OpenBB, alpacahq/alpaca-py | Research / official Alpaca |
| Payments | stripe/stripe-python | Official Stripe if we add a key later |
| SMS | twilio/twilio-python | Official Twilio |
| Notes | ramnes/notion-sdk-py | Official Notion |
| Speech | SYSTRAN/faster-whisper | Local STT fallback ideas |
| Media | yt-dlp/yt-dlp, ffmpeg-python, Pillow | Public media / images |
| Browser | microsoft/playwright-python | Official dashboards only — no hamburger farms |
| Chat | slackapi/python-slack-sdk, praw-dev/praw | Official Slack / Reddit |
| Data | pola-rs/polars, duckdb/duckdb, py-pdf/pypdf | Spreadsheets, SQL, PDFs |
| Calendar | collective/icalendar | ICS parse |
| Home | home-assistant/core | README only, do not install HA |
| Email | resend/resend-python | Official transactional email |

Still **not** everything: no unofficial IG login, no silent IBKR fills, no extra Polymarket accounts.
