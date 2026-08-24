---
type: skill
name: capability-gaps
---

# Capability gaps — closed by probe, never by assertion

```
gaps action=audit    # probe everything, change nothing
gaps action=sync     # set the tracked goals from those probes
```

Goals live in `memory.goals` and were only ever closed by hand, so shipping code never
moved them. Jarvis kept reporting four open gaps while one was already merged — and it
was right to, because nothing had told it otherwise.

The fix is **not** flipping flags. A goal closed by assertion is worse than an open one,
because it stops you looking. Each gap carries a probe that inspects the running system:

| Gap | Probe checks |
|---|---|
| Streamlined confirm tokens | mints a real grant, checks it's honoured, checks the cap **binds**, revokes |
| Event-driven autonomy | `autonomy.emit` exists, `app/events.py` backs it, a source is actually running |
| Persistent HUD | pywebview/nicegui installed **and** `app/hud.py` wires them |
| Native device control | pywinauto installed **and** `desktop.py` actually uses it |

Probes are functional where they can be — an import succeeding proves a file exists,
not that it's wired to anything. Delete `app/trust.py` and the gap reopens on the next
audit. That reversibility is the point.

Run `gaps action=sync` after pulling new code.

## Events (`app/events.py`)

```
events action=status
events action=subscribe event=vault.changed job=bot-19-rag
events action=emit event=vault.changed
```

`beat()` is the timer half of autonomy; `emit()` is the event half. Both run jobs
through the same `JOB_HANDLERS` registry, so an event-fired job is the same code path
as a scheduled one.

The vault watcher starts at boot — watchdog if installed, 30s polling otherwise, and
`status()` says which rather than implying the watcher is live. Source events **coalesce
within 5s**, because one editor save fires several filesystem events and a subscribed
job should run once, not six times. Manual `emit()` never coalesces: if you asked for it
explicitly, you meant it.
