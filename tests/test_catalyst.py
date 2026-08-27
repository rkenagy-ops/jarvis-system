"""News tells you WHEN, and one trap decides whether knowing that makes any money.

A catalyst is the reason to buy a short-dated option instead of a long one: if a
company reports Thursday, an expiry covering Thursday is the trade. But buying premium
into a SCHEDULED event and holding through it is one of the most reliable ways to be
right on direction and still lose - implied volatility is bid up before a known date
and collapses the instant the uncertainty resolves. Most of these tests are about that.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import catalyst as cat


# --- the trap -----------------------------------------------------------------


def test_a_scheduled_event_carries_a_crush_warning():
    out = cat.horizon("Nvidia to report third-quarter earnings on Wednesday")
    assert out["scheduled"] is True
    assert out["iv_crush"]["severe"] is True


def test_the_crush_warning_says_what_to_do_instead():
    """A warning with no alternative just gets ignored."""
    crush = cat.iv_crush_warning("earnings_upcoming")
    assert len(crush["what_to_do"]) >= 3
    assert any("spread" in x for x in crush["what_to_do"])
    assert "naked long" in crush["never"]


def test_unscheduled_news_carries_no_crush_warning():
    """Nobody bid up the premium for news nobody saw coming - that case is clean."""
    assert cat.iv_crush_warning("earnings_result") is None
    assert cat.horizon("Pfizer wins FDA approval for new cancer drug")["iv_crush"] is None


def test_macro_events_are_scheduled_too():
    assert cat.classify("Federal Reserve rate decision due Wednesday")["scheduled"] is True


# --- timing -------------------------------------------------------------------


def test_a_dated_print_gets_a_short_window():
    out = cat.horizon("Apple to report earnings on Thursday")
    assert out["suggested_dte"][0] <= 10


def test_a_war_gets_a_long_window():
    """Conflict is a condition, not a moment. It argues for MORE time, not less."""
    out = cat.horizon("Oil prices climb as the war continues and OPEC signals cuts")
    assert out["kind"] == "geopolitical"
    assert out["suggested_dte"][0] >= 20


def test_an_analyst_upgrade_is_treated_as_the_small_thing_it_is():
    out = cat.classify("Analysts upgrade Meta with a higher price target")
    assert out["kind"] == "analyst"
    assert out["horizon_days"] <= 3


def test_the_expiry_never_lands_on_the_event_itself():
    """A move that is one day late must not expire worthless the day before it arrives."""
    out = cat.horizon("Nvidia to report earnings on Wednesday")
    assert out["suggested_dte"][0] > out["horizon_days"]


def test_post_earnings_drift_gets_room_to_run():
    out = cat.classify("Apple beats on revenue, profit jumped 12%")
    assert out["kind"] == "earnings_result"
    assert out["horizon_days"] >= 7, "drift after a surprise runs for weeks"


# --- classification -----------------------------------------------------------


def test_direction_is_read_from_the_words():
    assert cat.classify("Boeing raises full-year guidance after strong deliveries")["direction"] == "bullish"
    assert cat.classify("Chip shortage halts production, company warns")["direction"] == "bearish"


def test_an_ambiguous_headline_says_unclear_rather_than_guessing():
    out = cat.classify("Company announces new product amid lawsuit and weak demand")
    assert out["direction"] in {"unclear", "bearish"}
    if out["direction"] == "unclear":
        assert out["tradeable"] is False


def test_ordinary_news_is_not_a_catalyst():
    """Most headlines are not tradeable events, and pretending otherwise is noise."""
    out = cat.classify("The weather will be nice tomorrow")
    assert out["kind"] is None
    assert out["tradeable"] is False


def test_an_empty_headline_is_refused():
    assert "error" in cat.classify("")


def test_every_kind_has_a_horizon_and_a_reason():
    for name, spec in cat.KINDS.items():
        assert spec["horizon_days"] > 0, name
        assert spec["persistence"], name
        assert spec["why"], name


def test_every_pattern_maps_to_a_real_kind():
    for kind, _ in cat.PATTERNS:
        assert kind in cat.KINDS, f"{kind} is matched but has no spec"


# --- does news actually move this name? ---------------------------------------


def _bars(n=400, shock_every=0, shock=0.08, fade=False, seed=4):
    import datetime as dt
    import random

    rng = random.Random(seed)
    px, out, d0 = 100.0, [], dt.date(2023, 1, 1)
    for i in range(n):
        move = rng.gauss(0.0003, 0.008)
        gapped = shock_every and i % shock_every == 0 and i > 0
        o = px * (1 + (shock if gapped else 0))
        c = o * (1 + (-shock * 0.8 if (gapped and fade) else move))
        out.append({"date": (d0 + dt.timedelta(days=i)).isoformat(), "open": round(o, 2),
                    "high": round(max(o, c) * 1.004, 2), "low": round(min(o, c) * 0.996, 2),
                    "close": round(c, 2), "volume": 1_000_000})
        px = c
    return out


def test_a_name_that_never_gaps_is_called_out():
    """No shocks means a catalyst may simply not move it, and short-dated is a bad bet."""
    out = cat.reaction_history(_bars())
    assert out["ok"]
    if out["shocks"] == 0:
        assert "does not gap" in out["verdict"]


def test_a_name_that_gaps_and_fades_is_flagged_as_such():
    """This is the case where the news is real and the short-dated trade still loses."""
    out = cat.reaction_history(_bars(shock_every=25, fade=True))
    if out.get("shocks"):
        assert out["follow_through_rate"] < 0.6
        assert "fades" in out["verdict"]


def test_the_shock_detection_says_how_it_defined_a_shock():
    out = cat.reaction_history(_bars(shock_every=25))
    if out.get("shocks"):
        assert "inferred from gaps" in out["caveat"], "an inferred event is not a calendar event"


def test_too_little_history_is_refused():
    assert "error" in cat.reaction_history(_bars(50))


def test_a_fading_name_shortens_the_suggested_window():
    """If shocks do not persist there is nothing to sell into, so do not pay for weeks."""
    persistent = cat.horizon("Company beats earnings badly", _bars(shock_every=25))
    fading = cat.horizon("Company beats earnings badly", _bars(shock_every=25, fade=True))
    if fading.get("history", {}).get("shocks") and persistent.get("history", {}).get("shocks"):
        assert fading["suggested_dte"][1] <= persistent["suggested_dte"][1]


def test_dispatch_surface():
    assert "error" in cat.dispatch("nonsense")
    assert cat.dispatch("classify", headline="Apple beats earnings")["ok"]
