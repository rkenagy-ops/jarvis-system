"""Standing grants let a bounded slice of operations skip the confirm token.

These tests are mostly about what a grant CANNOT do, because that is the property
that matters: the ceilings are enforced in code, not by whoever asks for the grant.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import ibkr, memory, trust


@pytest.fixture(autouse=True)
def clean_grants():
    memory.revoke_all_trust_grants()
    yield
    memory.revoke_all_trust_grants()


# --- default posture ---------------------------------------------------------


def test_default_is_everything_confirms():
    st = trust.status()
    assert st["count"] == 0
    assert trust.evaluate("ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 1})["trusted"] is False


def test_ineligible_kinds_never_get_a_grant():
    """oss_install runs fetched code beside brokerage credentials."""
    out = trust.grant("oss_install", max_uses=5)
    assert "error" in out
    assert "oss_install" not in trust.KINDS
    assert trust.evaluate("oss_install", {})["trusted"] is False


def test_unknown_kind_rejected():
    assert "error" in trust.grant("something_made_up")


# --- the ceilings ------------------------------------------------------------


def test_uses_are_clamped_to_the_ceiling():
    out = trust.grant("ibkr_stock", max_uses=10_000, ttl_sec=600, max_notional=100)
    assert out["max_uses"] == trust.MAX_USES
    assert out["clamped"]["max_uses"] is True


def test_ttl_is_clamped_to_the_ceiling():
    out = trust.grant("ibkr_stock", max_uses=1, ttl_sec=999_999, max_notional=100)
    assert out["expires_in_sec"] <= trust.MAX_TTL_SEC
    assert out["clamped"]["ttl_sec"] is True


def test_notional_is_clamped_to_the_ceiling():
    out = trust.grant("ibkr_stock", max_uses=1, ttl_sec=600, max_notional=10_000_000)
    assert out["constraints"]["max_notional"] == trust.MAX_NOTIONAL


def test_money_grants_always_get_a_value_cap():
    """An IBKR grant with no cap asked for still gets one."""
    out = trust.grant("ibkr_stock", max_uses=1, ttl_sec=600)
    assert out["constraints"]["max_notional"] == 500.0


# --- scoping -----------------------------------------------------------------


def test_symbol_scope_is_enforced():
    trust.grant("ibkr_stock", max_uses=5, ttl_sec=600, max_notional=5000, symbols="SPY")
    assert trust.evaluate("ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 100})["trusted"] is True
    out = trust.evaluate("ibkr_stock", {"symbol": "TSLA", "qty": 1, "limit": 100})
    assert out["trusted"] is False
    assert "TSLA" in out["reason"]


def test_notional_cap_is_enforced():
    trust.grant("ibkr_stock", max_uses=5, ttl_sec=600, max_notional=500)
    assert trust.evaluate("ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 400})["trusted"] is True
    out = trust.evaluate("ibkr_stock", {"symbol": "SPY", "qty": 10, "limit": 400})
    assert out["trusted"] is False
    assert "exceeds" in out["reason"]


def test_option_notional_counts_the_contract_multiplier():
    """A 3.00 option contract is 300 of exposure, not 3."""
    trust.grant("ibkr_option", max_uses=5, ttl_sec=600, max_notional=500)
    ok = trust.evaluate("ibkr_option", {"symbol": "SPY", "qty": 1, "limit": 3.0, "right": "C"})
    assert ok["trusted"] is True  # 300
    bad = trust.evaluate("ibkr_option", {"symbol": "SPY", "qty": 2, "limit": 3.0, "right": "C"})
    assert bad["trusted"] is False  # 600


def test_unpriceable_order_is_not_auto_approved():
    """A market order has no price, so the cap cannot be applied — send it to a human."""
    trust.grant("ibkr_stock", max_uses=5, ttl_sec=600, max_notional=5000)
    out = trust.evaluate("ibkr_stock", {"symbol": "SPY", "qty": 1})
    assert out["trusted"] is False
    assert "could not be established" in out["reason"]


def test_a_grant_covers_only_its_own_kind():
    trust.grant("ibkr_stock", max_uses=5, ttl_sec=600, max_notional=5000, symbols="SPY")
    assert trust.evaluate("ibkr_option", {"symbol": "SPY", "qty": 1, "limit": 1})["trusted"] is False
    assert trust.evaluate("publer_post", {})["trusted"] is False


def test_network_scope_for_social():
    trust.grant("engage_reply", max_uses=5, ttl_sec=600, networks="x")
    assert trust.evaluate("engage_reply", {"network": "x"})["trusted"] is True
    assert trust.evaluate("engage_reply", {"network": "instagram"})["trusted"] is False


# --- spending and revocation -------------------------------------------------


def test_uses_are_spent_and_run_out():
    trust.grant("ibkr_stock", max_uses=2, ttl_sec=600, max_notional=5000, symbols="SPY")
    payload = {"symbol": "SPY", "qty": 1, "limit": 100}
    assert trust.check_and_spend("ibkr_stock", payload)["trusted"] is True
    assert trust.check_and_spend("ibkr_stock", payload)["trusted"] is True
    assert trust.check_and_spend("ibkr_stock", payload)["trusted"] is False


def test_evaluate_does_not_spend():
    trust.grant("ibkr_stock", max_uses=1, ttl_sec=600, max_notional=5000, symbols="SPY")
    payload = {"symbol": "SPY", "qty": 1, "limit": 100}
    for _ in range(5):
        assert trust.evaluate("ibkr_stock", payload)["trusted"] is True
    assert trust.check_and_spend("ibkr_stock", payload)["trusted"] is True


def test_revoke_one():
    g = trust.grant("ibkr_stock", max_uses=5, ttl_sec=600, max_notional=5000, symbols="SPY")
    assert trust.revoke(g["grant_id"])["ok"] is True
    assert trust.evaluate("ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 100})["trusted"] is False


def test_revoke_all_is_one_call():
    trust.grant("ibkr_stock", max_uses=5, ttl_sec=600, max_notional=5000)
    trust.grant("ibkr_option", max_uses=5, ttl_sec=600, max_notional=5000)
    out = trust.revoke(all_grants=True)
    assert out["revoked"] >= 2
    assert trust.status()["count"] == 0


def test_expired_grant_does_not_apply():
    memory.add_trust_grant(
        "ibkr_stock", constraints={"max_notional": 5000}, max_uses=5, ttl_sec=-10, note="already expired"
    )
    assert trust.evaluate("ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 100})["trusted"] is False


# --- audit -------------------------------------------------------------------


def test_auto_approval_is_audited():
    trust.grant("ibkr_stock", max_uses=1, ttl_sec=600, max_notional=5000, symbols="SPY")
    trust.check_and_spend("ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 100})
    decisions = [d["decision"] for d in trust.audit(10)["decisions"]]
    assert "auto_approved" in decisions


def test_refusal_is_audited_too():
    trust.check_and_spend("ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 100})
    decisions = [d["decision"] for d in trust.audit(10)["decisions"]]
    assert "confirm_required" in decisions


# --- integration with the real IBKR gate -------------------------------------


def test_ibkr_gate_still_blocks_without_a_grant(monkeypatch):
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)
    monkeypatch.setattr(memory, "create_pending", lambda k, p, ttl_sec=180: {"confirm_token": "tok", "kind": k})
    monkeypatch.setattr(memory, "set_fact", lambda *a, **k: None)

    out = ibkr._need_confirm(
        "ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 100}, confirmed=False, confirm_token=None
    )
    assert out is not None and out["blocked"] is True
    assert out["confirm_token"] == "tok"


def test_ibkr_gate_passes_through_with_a_grant(monkeypatch):
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)

    def should_not_be_called(*a, **k):
        raise AssertionError("a covered order must not create a pending confirm")

    monkeypatch.setattr(memory, "create_pending", should_not_be_called)
    trust.grant("ibkr_stock", max_uses=1, ttl_sec=600, max_notional=5000, symbols="SPY")

    out = ibkr._need_confirm(
        "ibkr_stock", {"symbol": "SPY", "qty": 1, "limit": 100}, confirmed=False, confirm_token=None
    )
    assert out is None, "grant should let the order through"


def test_ibkr_gate_blocks_an_order_outside_the_grant(monkeypatch):
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)
    monkeypatch.setattr(memory, "create_pending", lambda k, p, ttl_sec=180: {"confirm_token": "tok", "kind": k})
    monkeypatch.setattr(memory, "set_fact", lambda *a, **k: None)
    trust.grant("ibkr_stock", max_uses=5, ttl_sec=600, max_notional=500, symbols="SPY")

    # right symbol, too big
    out = ibkr._need_confirm(
        "ibkr_stock", {"symbol": "SPY", "qty": 100, "limit": 100}, confirmed=False, confirm_token=None
    )
    assert out is not None and out["blocked"] is True
    assert "exceeds" in (out.get("trust") or "")


def test_dispatch_surface():
    assert trust.dispatch("status")["ok"] is True
    assert "error" in trust.dispatch("nonsense")
    assert trust.dispatch("kinds")["ok"] is True
