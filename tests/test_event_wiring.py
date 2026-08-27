"""The event half of autonomy was built and never switched on.

watch_vault() started a real watcher. emit() looked jobs up in SUBSCRIPTIONS. Nothing
ever put anything in SUBSCRIPTIONS, so health reported "subscriptions: 0" and every
vault edit fired into an empty registry. Learning therefore only ever happened when its
six-hour timer came round - "her learning isn't constant, it's scheduled", exactly.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import autonomy, events


@pytest.fixture(autouse=True)
def _clean():
    saved = {k: list(v) for k, v in events.SUBSCRIPTIONS.items()}
    events.SUBSCRIPTIONS.clear()
    yield
    events.SUBSCRIPTIONS.clear()
    events.SUBSCRIPTIONS.update(saved)


def test_wiring_produces_actual_subscriptions():
    out = events.wire_defaults()
    assert out["ok"], "the whole bug was that this stayed empty"
    assert out["subscriptions"] > 0


def test_a_vault_edit_reaches_learning():
    """The specific complaint: learning waited for a timer instead of reacting."""
    events.wire_defaults()
    assert "bot-22-learn" in events.SUBSCRIPTIONS.get("vault.changed", [])


def test_a_vault_edit_still_reindexes():
    events.wire_defaults()
    assert "bot-19-rag" in events.SUBSCRIPTIONS.get("vault.changed", [])


def test_wiring_twice_does_not_double_subscribe():
    """Boot may call this more than once; a job running twice per event is a bug."""
    events.wire_defaults()
    first = {k: list(v) for k, v in events.SUBSCRIPTIONS.items()}
    events.wire_defaults()
    assert {k: list(v) for k, v in events.SUBSCRIPTIONS.items()} == first


def test_every_default_subscriber_is_a_real_job():
    """Subscribing a job name with no handler is a silent no-op at fire time."""
    for event, jobs in events.DEFAULT_SUBSCRIPTIONS.items():
        for job in jobs:
            assert job in autonomy.JOB_HANDLERS, f"{event} -> {job} has no handler"


def test_boot_wires_the_defaults():
    """The fix only counts if boot actually calls it."""
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "_events.wire_defaults()" in src


def test_health_reports_the_subscriptions_it_now_has():
    events.wire_defaults()
    from app import health

    subs = health.subsystems().get("events") or {}
    assert subs.get("subscriptions", 0) > 0, "health said 0 for the entire time this was broken"
