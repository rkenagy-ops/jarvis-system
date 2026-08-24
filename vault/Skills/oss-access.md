---
type: skill
name: oss-access
---

# Open source: unrestricted access

`github_oss` packs were README-only, from curated lists. `oss` removes that —
**any public repo, real source, no allowlist.**

| Want | Call |
|---|---|
| Find repos | `oss action=search query="limit order book python"` |
| Pull the source | `oss action=fetch repo=pola-rs/polars` |
| See what's in it | `oss action=tree repo=pola-rs/polars` |
| Read any file | `oss action=read repo=... path=py-polars/polars/functions.py` |
| Search inside it | `oss action=grep repo=... pattern="def rolling"` |
| Make it importable | `oss action=vendor repo=...` |
| Into the vault/RAG | `oss action=ingest repo=...` |

Fetched source lands in `workspace/oss/<owner>__<name>/`.

## The one gate

`oss action=install` takes a **confirm_token**, like `place_stock` and
`publer_schedule` do.

Access is unrestricted; *running* fetched code is deliberate. This process holds
the IBKR session and brokerage credentials, so `pip install` of an arbitrary repo
executes its setup code right next to them. Fetch anything, read anything, search
anything — decide to run it.
