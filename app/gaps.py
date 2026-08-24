"""Capability gaps: probe what actually exists, then set the tracked goals from that.

Goals live in the memory.goals table and only ever closed by hand. So shipping code
never moved them — Jarvis kept reporting four open gaps while the code for one of them
was already merged, and it was right to: nothing had told it otherwise.

The fix is not to flip the flags. A goal closed by assertion is worse than an open one,
because it stops you looking. Each gap here carries a **probe** that inspects the running
system, and sync() closes only what the probe actually confirms. Delete app/trust.py and
the trusted-confirm gap reopens on the next audit, which is the property that makes this
worth having.

Probes are functional wherever possible — for trusted_confirm we mint a real grant,
check it is honoured, and revoke it — because an import succeeding proves a file exists,
not that it is wired to anything.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any, Callable

from . import memory

GOAL_PREFIX = "Capability gap: "


# --------------------------------------------------------------------------- probes


def _probe_trusted_confirm() -> tuple[bool, str]:
    """Can a bounded standing grant actually short-circuit a confirm gate?"""
    try:
        trust = importlib.import_module("app.trust")
        ibkr = importlib.import_module("app.ibkr")
    except ImportError as exc:
        return False, f"module missing: {exc}"

    # Wiring: the confirm gate must consult trust, not merely import it.
    try:
        src = inspect.getsource(ibkr._need_confirm)
    except (OSError, TypeError):
        return False, "could not read ibkr._need_confirm"
    if "trust" not in src:
        return False, "app/trust.py exists but ibkr._need_confirm does not consult it"

    # Behaviour: mint a narrow grant, confirm it is honoured, then clean up.
    granted = trust.grant(
        "ibkr_stock",
        max_uses=1,
        ttl_sec=60,
        max_notional=1.0,
        symbols="__PROBE__",
        note="capability probe — revoked immediately",
    )
    if not granted.get("ok"):
        return False, f"grant refused: {granted.get('error')}"
    try:
        verdict = trust.evaluate("ibkr_stock", {"symbol": "__PROBE__", "qty": 1, "limit": 0.5})
        if not verdict.get("trusted"):
            return False, f"grant not honoured: {verdict.get('reason')}"
        # And the ceilings must actually bind.
        over = trust.evaluate("ibkr_stock", {"symbol": "__PROBE__", "qty": 1000, "limit": 0.5})
        if over.get("trusted"):
            return False, "grant honoured an order past its own notional cap"
    finally:
        trust.revoke(granted["grant_id"])

    return True, f"standing grants live and bound to the confirm gate ({len(trust.KINDS)} eligible kinds)"


def _probe_event_driven() -> tuple[bool, str]:
    """Can anything fire a job on an event rather than a timer?"""
    try:
        autonomy = importlib.import_module("app.autonomy")
    except ImportError as exc:
        return False, f"module missing: {exc}"

    if not hasattr(autonomy, "emit"):
        return False, "autonomy.beat() is timer-only; no emit()/event bus exists"
    try:
        events = importlib.import_module("app.events")
    except ImportError:
        return False, "autonomy.emit exists but no app/events.py backs it"
    if not getattr(events, "SOURCES", None):
        return False, "app/events.py has no registered event sources"
    return True, f"event bus live with {len(events.SOURCES)} source(s)"


def _probe_persistent_hud() -> tuple[bool, str]:
    """Is there a native, always-on window rather than a browser tab?"""
    have = []
    for mod in ("webview", "nicegui"):
        try:
            importlib.import_module(mod)
            have.append(mod)
        except ImportError:
            pass
    if not have:
        return False, "no native-window library installed (pywebview or nicegui)"
    try:
        importlib.import_module("app.hud")
    except ImportError:
        return False, f"{'/'.join(have)} installed but no app/hud.py launcher wires it up"
    return True, f"native HUD launcher present, using {'/'.join(have)}"


def _probe_device_control() -> tuple[bool, str]:
    """Real UI automation, or still launching executables and hoping?"""
    try:
        importlib.import_module("pywinauto")
    except ImportError:
        return False, "pywinauto not installed; desktop.py launches executables and guesses"
    try:
        desktop = importlib.import_module("app.desktop")
        src = inspect.getsource(desktop)
    except (ImportError, OSError, TypeError) as exc:
        return False, f"could not inspect app/desktop.py: {exc}"
    if "pywinauto" not in src:
        return False, "pywinauto installed but app/desktop.py does not use it"
    return True, "desktop bridge uses pywinauto for real UI control"


GAPS: list[dict[str, Any]] = [
    {
        "key": "trusted_confirm",
        "title": "Streamlined confirm tokens for trusted operations",
        "detail": "Bounded, expiring, audited standing grants so routine operations skip the token without removing the gate.",
        "probe": _probe_trusted_confirm,
    },
    {
        "key": "event_driven_autonomy",
        "title": "Event-driven autonomy instead of pure timers",
        "detail": "Jobs fire on events (file change, webhook, threshold) rather than waiting for the next beat.",
        "probe": _probe_event_driven,
    },
    {
        "key": "persistent_hud",
        "title": "Persistent visual HUD",
        "detail": "A native always-on window rather than a browser tab you must keep open at 127.0.0.1:8787.",
        "probe": _probe_persistent_hud,
    },
    {
        "key": "native_device_control",
        "title": "Native device control beyond the desktop bridge",
        "detail": "Real Windows UI automation via pywinauto instead of launching executables and guessing.",
        "probe": _probe_device_control,
    },
]


# --------------------------------------------------------------------------- audit


def audit() -> dict[str, Any]:
    """Run every probe. Read-only — touches no goals."""
    rows = []
    for gap in GAPS:
        probe: Callable[[], tuple[bool, str]] = gap["probe"]
        try:
            closed, evidence = probe()
        except Exception as exc:
            closed, evidence = False, f"probe raised {type(exc).__name__}: {str(exc)[:150]}"
        rows.append(
            {
                "key": gap["key"],
                "title": gap["title"],
                "closed": closed,
                "evidence": evidence,
            }
        )
    done = [r for r in rows if r["closed"]]
    return {
        "ok": True,
        "gaps": rows,
        "closed": len(done),
        "open": len(rows) - len(done),
        "total": len(rows),
        "summary": f"{len(done)}/{len(rows)} capability gaps closed.",
    }


def sync() -> dict[str, Any]:
    """Set the tracked goals from the probe results.

    Closes only what probed true, and reopens anything that regressed. This is the
    only thing that should ever close a capability goal.
    """
    result = audit()
    # list_goals(None) caps at 30 rows, which would silently create a duplicate goal
    # on a busy vault. The per-status queries are unbounded, so union those instead.
    existing: dict[str, Any] = {}
    for status in ("open", "done"):
        for g in memory.list_goals(status):
            existing.setdefault(g.get("title"), g)

    closed, opened, unchanged = [], [], []
    for row in result["gaps"]:
        title = GOAL_PREFIX + row["title"]
        goal = existing.get(title)

        if goal is None:
            goal = memory.add_goal(
                title,
                next(g["detail"] for g in GAPS if g["key"] == row["key"]),
                0.75,
            )
            existing[title] = goal

        want = "done" if row["closed"] else "open"
        have = goal.get("status")
        if have == want:
            unchanged.append(row["key"])
            continue

        memory.update_goal(goal["id"], want)
        (closed if row["closed"] else opened).append(row["key"])
        memory.remember(
            f"Capability gap {row['key']} -> {want}: {row['evidence']}",
            kind="capability",
            tags=["gaps", row["key"]],
            importance=0.8,
            source_agent="jarvis",
        )

    return {
        **result,
        "goals_closed": closed,
        "goals_reopened": opened,
        "unchanged": unchanged,
        "note": "Goals are set from probes, never from assertion — a deleted capability reopens its goal.",
    }


def dispatch(action: str = "audit", **kwargs: Any) -> Any:
    act = (action or "audit").lower()
    if act in {"audit", "status", "check"}:
        return audit()
    if act in {"sync", "refresh", "update"}:
        return sync()
    return {"error": f"unknown gaps action {act}", "actions": ["audit", "sync"]}
