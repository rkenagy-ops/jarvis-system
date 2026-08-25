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
import re
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
        "match": [{"confirm", "token"}, {"trust", "grant"}, {"confirm", "trusted"}],
    },
    {
        "key": "event_driven_autonomy",
        "title": "Event-driven autonomy instead of pure timers",
        "detail": "Jobs fire on events (file change, webhook, threshold) rather than waiting for the next beat.",
        "probe": _probe_event_driven,
        "match": [{"event", "driven"}, {"event", "trigger"}, {"timer", "event"}],
    },
    {
        "key": "persistent_hud",
        "title": "Persistent visual HUD",
        "detail": "A native always-on window rather than a browser tab you must keep open at 127.0.0.1:8787.",
        "probe": _probe_persistent_hud,
        "match": [{"persistent", "hud"}, {"persistent", "visual"}, {"native", "hud"}, {"persistent", "interface"}],
    },
    {
        "key": "native_device_control",
        "title": "Native device control beyond the desktop bridge",
        "detail": "Real Windows UI automation via pywinauto instead of launching executables and guessing.",
        "probe": _probe_device_control,
        "match": [{"device", "control"}, {"native", "device"}, {"desktop", "bridge"}],
    },
]


def _matches(gap: dict[str, Any], title: str) -> bool:
    """Does an existing goal describe this gap, whatever it happens to be called?

    sync() used to key on its own exact title, so a goal Jarvis had already written
    for the same gap was never found — sync created a second one beside it and the
    original stayed open forever. Every AND-group must match in full, which keeps
    this from swallowing unrelated goals.
    """
    words = set(re.findall(r"[a-z]+", (title or "").lower()))
    if not words:
        return False
    if gap["title"].lower() in (title or "").lower():
        return True
    return any(group <= words for group in gap.get("match", []))


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
    everything: list[dict[str, Any]] = []
    for status in ("open", "done"):
        everything.extend(memory.list_goals(status))

    closed, opened, unchanged, adopted = [], [], [], []
    for row in result["gaps"]:
        gap = next(g for g in GAPS if g["key"] == row["key"])
        want = "done" if row["closed"] else "open"

        # Every goal describing this gap, whatever it is titled. A gap Jarvis had
        # already logged under its own wording is adopted rather than duplicated —
        # otherwise sync closes its own copy and the original stays open forever,
        # which is exactly what happened.
        targets = [g for g in everything if _matches(gap, g.get("title") or "")]
        if not targets:
            targets = [memory.add_goal(GOAL_PREFIX + row["title"], gap["detail"], 0.75)]
            everything.extend(targets)
        elif not any((g.get("title") or "").startswith(GOAL_PREFIX) for g in targets):
            adopted.extend(g.get("title") for g in targets)

        moved = False
        for goal in targets:
            if goal.get("status") == want:
                continue
            memory.update_goal(goal["id"], want)
            goal["status"] = want
            moved = True

        if not moved:
            unchanged.append(row["key"])
            continue
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
        "adopted_existing_goals": adopted or None,
        "note": "Goals are set from probes, never from assertion — a deleted capability reopens its goal.",
    }


def goals() -> dict[str, Any]:
    """Every tracked goal and which gap, if any, it maps to.

    Use this when the audit and the goal list disagree: it shows exactly which goals
    each gap will move, and which goals no gap owns.
    """
    rows = []
    for status in ("open", "done"):
        for g in memory.list_goals(status):
            title = g.get("title") or ""
            owner = next((gap["key"] for gap in GAPS if _matches(gap, title)), None)
            rows.append({"title": title, "status": status, "gap": owner})
    return {
        "ok": True,
        "goals": rows,
        "unowned": [r["title"] for r in rows if not r["gap"]],
        "note": "A goal with gap=None is not managed by the audit and will never be closed by it.",
    }


def doctor() -> dict[str, Any]:
    """Everything needed to diagnose a stuck gap, in one payload worth pasting.

    Guessing at somebody else's machine is slow. This reports what is installed,
    what the probes saw, what the goals say, and where the two disagree.
    """
    import platform
    import sys

    installed = {}
    for mod in ("watchdog", "psutil", "ib_async", "ib_insync", "webview", "nicegui", "pywinauto"):
        try:
            importlib.import_module(mod)
            installed[mod] = True
        except ImportError:
            installed[mod] = False

    modules = {}
    for mod in ("trust", "events", "gaps", "learning", "repo_index", "oss", "setups", "engage"):
        try:
            importlib.import_module(f"app.{mod}")
            modules[mod] = True
        except ImportError:
            modules[mod] = False

    sources: dict[str, Any] = {}
    try:
        events = importlib.import_module("app.events")
        sources = {k: v.get("kind") for k, v in (getattr(events, "SOURCES", {}) or {}).items()}
    except ImportError:
        sources = {"error": "app.events not importable"}

    audit_now = audit()
    tracked = goals()

    # The disagreement that matters: a gap the probe says is closed, but whose goal
    # is still open — meaning sync has not run since the capability landed.
    stale = []
    by_gap = {}
    for row in tracked["goals"]:
        if row["gap"]:
            by_gap.setdefault(row["gap"], []).append(row)
    for row in audit_now["gaps"]:
        for goal in by_gap.get(row["key"], []):
            want = "done" if row["closed"] else "open"
            if goal["status"] != want:
                stale.append(f"{goal['title']!r} is {goal['status']} but the probe says {want}")

    return {
        "ok": True,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": installed,
        "app_modules": modules,
        "event_sources": sources,
        "audit": audit_now,
        "tracked_goals": tracked["goals"],
        "unowned_goals": tracked["unowned"],
        "stale": stale or None,
        "verdict": (
            "Run gaps action=sync — the goals disagree with the probes."
            if stale
            else "Goals and probes agree."
        ),
    }


def dispatch(action: str = "audit", **kwargs: Any) -> Any:
    act = (action or "audit").lower()
    if act in {"audit", "status", "check"}:
        return audit()
    if act in {"sync", "refresh", "update"}:
        return sync()
    if act in {"goals", "tracked", "why"}:
        return goals()
    if act in {"doctor", "diagnose", "debug"}:
        return doctor()
    return {"error": f"unknown gaps action {act}", "actions": ["audit", "sync", "goals", "doctor"]}
