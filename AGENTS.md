# Super Jarvis

Local multi-agent OS for Rhett. Python FastAPI + SpaceXAI (xAI) + GitHub.

- Provider is SpaceXAI via `XAI_API_KEY` and `https://api.x.ai/v1`. Do not add OpenAI/Anthropic.
- Default model: `grok-4.6`. Voice: `grok-voice-latest` + TTS voice `orion`.
- Never commit `.env` or `data/`.
- GitHub access is the owner's PAT (`GITHUB_TOKEN`), not a hardcoded account.
- Agents share one SQLite mind in `data/jarvis.db`. Do not silo memory.
- Do not add jailbreak / safety-bypass features.
