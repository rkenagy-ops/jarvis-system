"""The playback clock must belong to the context that owns it.

state.playTime is a timestamp on one AudioContext's clock, but it was global state
that outlived the context. toggleLive builds a fresh AudioContext each time it is
switched on and a fresh context restarts currentTime at zero, so on the second live
session playTime still held a large value from the first. Nothing reset it, and both
gates that read it failed closed: incoming audio was dropped as "too far ahead", and
the microphone gate concluded Jarvis was still speaking and sent silence upstream.
Deaf and mute together, until a page reload.

There is no JS runtime in the test environment, so these assert on the source. Crude,
but it pins the exact shape of a bug that cost a real debugging session.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def test_the_clock_is_reset_when_the_context_changes():
    assert "function audioClock()" in SRC
    assert "state.playCtx !== state.audioCtx" in SRC, "the reset must key on the context identity"


def test_both_gates_go_through_the_clock_helper():
    """Either gate reading state.playTime raw is the bug coming back."""
    assert "audioClock() > now + 0.08" in SRC, "the mic gate must use the context-checked clock"
    assert "(state.playTime || 0) > now" not in SRC, "raw stale read reintroduced"


def test_live_does_not_build_a_second_context_behind_the_first():
    """Two contexts meant two clocks, and the state only ever tracked one."""
    assert SRC.count("new AudioContext({ sampleRate: 24000 })") == 2, (
        "expected exactly the playback fallback and the one built inside the click"
    )
    assert "const ctx = liveCtx;" in SRC, "the mic path must reuse the context created in the click"


def test_the_context_is_created_inside_the_user_gesture():
    """Created in ws.onopen it starts suspended: nothing plays, onaudioprocess never fires."""
    # Split on the handler assignment, not the bare name — the comment above it
    # mentions ws.onopen and would cut the slice short.
    click_half = SRC.split("async function toggleLive()", 1)[1].split("ws.onopen = async", 1)[0]
    assert "new AudioContext" in click_half, "the context must exist before the socket opens"
    assert "liveCtx.resume()" in click_half


def test_a_blocked_context_says_so():
    assert "browser blocked audio" in SRC


def test_a_refused_microphone_is_reported():
    """It used to reject inside onopen and vanish without a word."""
    assert "microphone refused" in SRC


def test_the_playback_queue_cap_is_not_tighter_than_a_sentence():
    assert "now + 2.5" in SRC, "0.9s discarded the middle of ordinary speech"


def test_the_cache_buster_matches_the_shipped_version():
    """A stale cached app.js is indistinguishable from a bug that was never fixed."""
    from app import __version__

    assert f"app.js?v={__version__}" in HTML
    assert f"styles.css?v={__version__}" in HTML
