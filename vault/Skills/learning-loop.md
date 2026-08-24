---
type: skill
name: learning-loop
---

# Learning from open source (bot-22)

`oss` gave Jarvis unrestricted access to any public repo. This is the loop that
*uses* it on a schedule instead of waiting to be asked.

```
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
