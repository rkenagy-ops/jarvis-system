"""Black-Scholes greeks.

Financial maths is easy to get subtly wrong and hard to eyeball, so these check
properties that must hold rather than numbers I typed in and could have typed wrong:
put-call parity, greek bounds and signs, monotonicity, and an IV round-trip.
"""

from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import greeks


# --- identities that must hold ------------------------------------------------


def test_put_call_parity():
    """C - P = S*e^(-qT) - K*e^(-rT). Wrong signs anywhere break this."""
    S, K, T, r, sigma, q = 100.0, 105.0, 0.5, 0.045, 0.25, 0.01
    c = greeks.price(S, K, T, r, sigma, "C", q)
    p = greeks.price(S, K, T, r, sigma, "P", q)
    expected = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert abs((c - p) - expected) < 1e-8


def test_delta_parity():
    """call delta - put delta = e^(-qT)."""
    S, K, T, r, sigma, q = 100.0, 100.0, 0.25, 0.045, 0.3, 0.0
    cd = greeks.greeks(S, K, T, r, sigma, "C", q)["delta"]
    pd = greeks.greeks(S, K, T, r, sigma, "P", q)["delta"]
    assert abs((cd - pd) - math.exp(-q * T)) < 1e-3


def test_deep_itm_call_approaches_intrinsic():
    v = greeks.price(200.0, 100.0, 0.01, 0.045, 0.2, "C")
    assert abs(v - (200.0 - 100.0 * math.exp(-0.045 * 0.01))) < 0.5


def test_deep_otm_is_nearly_worthless():
    assert greeks.price(100.0, 300.0, 0.02, 0.045, 0.2, "C") < 0.01


# --- greek bounds and signs ---------------------------------------------------


def test_call_delta_between_zero_and_one():
    for K in (50, 80, 100, 120, 200):
        d = greeks.greeks(100.0, float(K), 0.5, 0.045, 0.25, "C")["delta"]
        assert 0.0 <= d <= 1.0, f"call delta {d} out of range at K={K}"


def test_put_delta_between_minus_one_and_zero():
    for K in (50, 80, 100, 120, 200):
        d = greeks.greeks(100.0, float(K), 0.5, 0.045, 0.25, "P")["delta"]
        assert -1.0 <= d <= 0.0, f"put delta {d} out of range at K={K}"


def test_gamma_and_vega_are_positive_for_both_rights():
    for right in ("C", "P"):
        g = greeks.greeks(100.0, 100.0, 0.5, 0.045, 0.25, right)
        assert g["gamma"] > 0
        assert g["vega"] > 0


def test_gamma_is_identical_for_call_and_put():
    c = greeks.greeks(100.0, 100.0, 0.4, 0.045, 0.3, "C")["gamma"]
    p = greeks.greeks(100.0, 100.0, 0.4, 0.045, 0.3, "P")["gamma"]
    assert abs(c - p) < 1e-9


def test_long_options_decay():
    """Theta is negative for a long option — it is a cost, and the sign says so."""
    for right in ("C", "P"):
        assert greeks.greeks(100.0, 100.0, 0.25, 0.045, 0.25, right)["theta"] < 0


def test_atm_gamma_exceeds_wing_gamma():
    atm = greeks.greeks(100.0, 100.0, 0.25, 0.045, 0.25, "C")["gamma"]
    otm = greeks.greeks(100.0, 160.0, 0.25, 0.045, 0.25, "C")["gamma"]
    assert atm > otm


def test_price_rises_with_volatility():
    prev = 0.0
    for sigma in (0.1, 0.2, 0.3, 0.5, 0.8):
        v = greeks.price(100.0, 100.0, 0.5, 0.045, sigma, "C")
        assert v > prev
        prev = v


def test_call_price_rises_with_spot():
    prev = 0.0
    for S in (80, 90, 100, 110, 120):
        v = greeks.price(float(S), 100.0, 0.5, 0.045, 0.25, "C")
        assert v > prev
        prev = v


# --- implied volatility -------------------------------------------------------


def test_iv_round_trip():
    """Price at a known vol, solve for it, get it back."""
    for sigma in (0.12, 0.25, 0.60, 1.20):
        for K in (80.0, 100.0, 130.0):
            for right in ("C", "P"):
                p = greeks.price(100.0, K, 0.4, 0.045, sigma, right)
                out = greeks.implied_vol(p, 100.0, K, 0.4, 0.045, right)
                assert out.get("ok"), f"no solve at sigma={sigma} K={K} {right}: {out}"
                assert abs(out["iv"] - sigma) < 1e-3, f"got {out['iv']} want {sigma}"


def test_iv_solves_far_from_the_money():
    """Newton's vega denominator collapses out here; bisection has to catch it."""
    p = greeks.price(100.0, 250.0, 0.08, 0.045, 0.9, "C")
    out = greeks.implied_vol(p, 100.0, 250.0, 0.08, 0.045, "C")
    assert out.get("ok"), out
    assert abs(out["iv"] - 0.9) < 1e-2


def test_iv_rejects_a_price_below_intrinsic():
    out = greeks.implied_vol(1.0, 200.0, 100.0, 0.5, 0.045, "C")
    assert "error" in out
    assert "intrinsic" in out["error"]


def test_iv_rejects_nonsense():
    assert "error" in greeks.implied_vol(0, 100.0, 100.0, 0.5)
    assert "error" in greeks.implied_vol(5.0, -100.0, 100.0, 0.5)
    assert "error" in greeks.implied_vol(5.0, 100.0, 100.0, 0.0)


# --- input validation ---------------------------------------------------------


def test_greeks_reject_expired_and_negative_inputs():
    assert "error" in greeks.greeks(100.0, 100.0, 0.0, 0.045, 0.25)
    assert "error" in greeks.greeks(-100.0, 100.0, 0.5, 0.045, 0.25)
    assert "error" in greeks.greeks(100.0, 0.0, 0.5, 0.045, 0.25)
    assert "error" in greeks.greeks(100.0, 100.0, 0.5, 0.045, 0.0)


# --- the trading-facing layer -------------------------------------------------


def test_analyze_needs_sigma_or_premium():
    assert "error" in greeks.analyze(spot=100, strike=100, days=30)


def test_analyze_solves_iv_from_premium():
    out = greeks.analyze(symbol="SPY", spot=100, strike=105, days=30, right="C", premium=1.50)
    assert out["ok"]
    assert out["iv"]["ok"] is True
    assert out["position"] == "out of the money"


def test_contract_multiplier_is_applied():
    """A contract is 100 shares. This is the classic sizing error."""
    out = greeks.analyze(spot=100, strike=100, days=30, right="C", sigma=0.25, qty=1)
    per_share = out["per_share"]["delta"]
    per_contract = out["per_contract"]["delta"]
    assert abs(per_contract - per_share * 100) < 0.01


def test_delta_shares_scales_with_contracts():
    one = greeks.analyze(spot=100, strike=100, days=30, sigma=0.25, qty=1)
    ten = greeks.analyze(spot=100, strike=100, days=30, sigma=0.25, qty=10)
    assert abs(ten["position_totals"]["delta_shares"] - one["position_totals"]["delta_shares"] * 10) < 0.5


def test_low_delta_contract_is_called_out():
    out = greeks.analyze(spot=100, strike=160, days=20, right="C", sigma=0.3)
    assert any("low-probability" in n for n in out["notes"])


def test_near_expiry_is_flagged():
    out = greeks.analyze(spot=100, strike=100, days=3, sigma=0.3)
    assert any("gamma and theta" in n for n in out["notes"])


def test_analyze_rejects_expired():
    assert "error" in greeks.analyze(spot=100, strike=100, days=0, sigma=0.2)


# --- sizing -------------------------------------------------------------------


def test_size_by_risk_respects_the_budget():
    out = greeks.size_by_risk(spot=100, strike=105, days=30, premium=1.50, risk_budget=1000)
    assert out["ok"]
    assert out["contracts"] == 6  # 150 per contract
    assert out["cost"] <= 1000


def test_size_by_risk_reports_delta_exposure():
    """The point of sizing: what stock exposure does that quietly buy."""
    out = greeks.size_by_risk(spot=100, strike=105, days=30, premium=1.50, risk_budget=1000)
    assert out["delta_shares"] > 0
    assert "shares" in out["note"]


def test_size_by_risk_when_one_contract_is_too_dear():
    out = greeks.size_by_risk(spot=100, strike=100, days=30, premium=8.0, risk_budget=500)
    assert out["contracts"] == 0
    assert "over the" in out["reason"]


def test_size_by_risk_validates():
    assert "error" in greeks.size_by_risk(spot=100, strike=100, days=30, premium=0, risk_budget=500)
    assert "error" in greeks.size_by_risk(spot=100, strike=100, days=30, premium=1.0, risk_budget=0)


# --- dispatch -----------------------------------------------------------------


def test_dispatch_routes():
    out = greeks.dispatch("analyze", spot=100, strike=100, days=30, sigma=0.25)
    assert out["ok"]
    assert greeks.dispatch("iv", premium=2.0, spot=100, strike=100, days=30).get("ok")
    assert greeks.dispatch("size", spot=100, strike=100, days=30, premium=2.0, risk=1000)["ok"]
    assert "error" in greeks.dispatch("nonsense")


def test_dispatch_survives_bad_input():
    assert "error" in greeks.dispatch("analyze", spot="abc", strike=100, days=30)


@pytest.mark.parametrize("right", ["C", "P", "call", "put", "CALL", ""])
def test_right_parsing_is_forgiving(right):
    out = greeks.greeks(100.0, 100.0, 0.5, 0.045, 0.25, right)
    assert out["ok"]
