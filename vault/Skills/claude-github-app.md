---
type: skill
name: claude-github-app
---

# Claude GitHub App

https://github.com/apps/claude — Anthropic's GitHub App (Claude Code on PRs/issues).

**Not the HUD brain.** Super Jarvis on http://127.0.0.1:8787 still uses Grok / Ollama / free APIs.

## Install (you must click)

1. Open https://github.com/apps/claude/installations/new
2. Choose **only** `rkenagy-ops/jarvis-system` (or all repos if you want).
3. Repo **Settings → Secrets and variables → Actions** → add `ANTHROPIC_API_KEY` from https://console.anthropic.com (this is billed separately from a Claude Pro chat sub).
4. Workflow is `.github/workflows/claude.yml`. Comment **@claude** on an issue or PR.

Jarvis can `desktop action=open` that install URL. She cannot finish GitHub App OAuth for you.
