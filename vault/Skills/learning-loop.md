---
type: skill
name: learning-loop
---

# Learning from open source (bot-22)

`oss` gave Jarvis unrestricted access to any public repo. This is the loop that
*uses* it on a schedule instead of waiting to be asked.

```
learning action=index                      # the curated index + what's studied
learning action=hubs                       # pull the awesome-lists first
learning action=gaps                       # which capability areas have nothing behind them
learning action=candidates topic=agents    # repos on that topic not yet studied
learning action=study repo=owner/name      # fetch + ingest one
learning action=cycle                      # the scheduled pass (bot-22, every 12h)
learning action=status                     # everything studied so far
```

Each cycle searches GitHub per topic, skips anything already in the ledger, fetches
the **real source**, ingests it into `Sources/oss/`, and reindexes the RAG. One repo
per topic per cycle, so the corpus grows broad rather than deep on one subject.

"Learning" here means retrieval, not fine-tuning: once a repo's source is indexed,
every agent can retrieve from it.

Topics: trading, market_data, prediction_markets, agents, memory, retrieval,
scheduling, social, scraping, voice, data, automation.

**It reads and indexes only.** Nothing in this loop installs or executes what it
pulls — `oss action=install` stays separate and confirm-gated.

## Why the handler registry exists

`autonomy.JOB_HANDLERS` maps every bot in `bots.SPECS` to a callable. Before it,
that mapping was a long if/elif chain inside `run_job`, and a bot added without a
matching branch fell through to the generic LLM fallback — where it would *describe*
doing its job instead of doing it. bot-21-engage shipped that way.
`test_every_bot_has_a_handler` now pins the two lists together.


## The index (app/repo_index.py)

Discovery used to be 100% GitHub search, which needs a token. With none set, every
topic failed and the cycle reported *"nothing new to learn"* — indistinguishable from
being up to date. The curated index is the primary source now; search only widens the
pool when a token exists, and is skipped entirely when the index already fills the quota.

**Fetching needs no credentials** — codeload is unauthenticated — so the whole index
pulls with zero keys configured.

Start with `learning action=hubs`. The six awesome-lists are small and each one maps a
whole field: awesome-quant, two systematic-trading indexes, public-apis,
awesome-ai-agents, and sindresorhus/awesome.

Priority-1 entries, and why they are there:

| Repo | Fills |
|---|---|
| `ib-api-reloaded/ib_async` | Maintained IBKR client — `ib_insync` is archived |
| `OpenBB-finance/OpenBB` | Broad market data + a provider abstraction worth copying |
| `polakowo/vectorbt` | Backtesting — `setups.py` generates plans it never validates |
| `langchain-ai/langgraph` | Stateful orchestration; `_handle_spawn` is a flat pool with no resume |
| `pydantic/pydantic-ai` | Type-safe tool arguments instead of hand-parsing |
| `mem0ai/mem0` | Memory consolidation — `memory.py` stores but never consolidates |
| `run-llama/llama_index` | Real RAG; `rag.py` is one naive embed-and-cosine pass |
| `BerriAI/litellm` | Provider fallback, already in the config but unused from Python |
| `unclecode/crawl4ai` | Structured extraction; `opensource.crawl()` strips tags with regex |

`test_categories_line_up_with_learning_topics` pins index categories against
`learning.TOPICS`, so an entry in a category no cycle looks at cannot sit there unnoticed.
