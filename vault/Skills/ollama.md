---
type: skill
name: ollama
---

# Ollama local brain

Grok stays primary. Ollama is the **local** fallback when `JARVIS_OFFLINE=true` or xAI is down.

```
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
# Fallback if RAM is tight: llama3.2
```

Install: [ollama.com](https://ollama.com) then `ollama pull llama3.2`.

Loopback only. Not a Docker stack.
