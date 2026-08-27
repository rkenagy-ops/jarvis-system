"""The governor. Nothing reaches the broker without passing through here.

Every other module in this system is allowed to be clever. This one is not. It counts
money lost today, compares it to a hard number, and says yes or no. It is deliberately
boring, deliberately pessimistic, and deliberately the last thing between a strategy and
the account.

Four rules, in the order they bind:

  1. A halt is sticky. Once tripped it survives restarts, because "turn it off and on
     again" must never be a way to resume trading after a bad day. Only an explicit
     resume clears it.
  2. The daily loss limit counts realized AND open losses. A position down 20k that you
     have not closed has still lost 20k; letting it hide because it is unrealized is
     how a day limit gets discovered in hindsight.
  3. The broker is the authority on P&L, not our own tally. We keep a tally as a floor
     for when the broker is unreachable, and take the WORSE of the two. A bookkeeping
     gap must never read as a good day.
  4. Per-trade exposure is capped separately. The day limit does not help if one order
     can exceed it by itself.

The day rolls at the US equity close boundary in New York, not at local midnight and
not in UTC — a trading day is a market day.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any
from zoneinfo import ZoneInfo

from . import config, memory

MARKET_TZ = ZoneInfo("America/New_York")

# Persisted under these keys so a restart cannot lose them.
_HALT_KEY = "risk.halt"
_DAY_KEY = "risk.day"

# Ceilings the caller cannot raise at runtime. Config may lower them, never exceed them.
# A hard ceiling in code is the difference between a limit and a suggestion.
HARD_MAX_DAILY_LOSS = 25_000.0
HARD_MAX_TRADE_NOTIONAL = 25_000.0
HARD_MAX_TRADES_PER_DAY = 40

# After this many losers in a row, stand down for the session. A strategy that has been
# wrong repeatedly today is not more likely to be right on the next one, and this is the
# point at which a bad day usually becomes a catastrophic one.
MAX_CONSECUTIVE_LOSSES = 4


def max_daily_loss() -> float:
    raw = getattr(config, "MAX_DAILY_LOSS", None)
    try:
        value = float(raw) if raw is not None else HARD_MAX_DAILY_LOSS
    except (TypeError, ValueError):
        value = HARD_MAX_DAILY_LOSS
    return min(abs(value), HARD_MAX_DAILY_LOSS)


def max_trade_notional() -> float:
    raw = getattr(config, "MAX_TRADE_NOTIONAL", None)
    try:
        value = float(raw) if raw is not None else HARD_MAX_TRADE_NOTIONAL
    except (TypeError, ValueError):
        value = HARD_MAX_TRADE_NOTIONAL
    return min(abs(value), HARD_MAX_TRADE_NOTIONAL)


def trading_day(now: dt.datetime | None = None) -> str:
    """The market day this moment belongs to, as an ISO date in New York."""
    moment = (now or dt.datetime.now(dt.timezone.utc)).astimezone(MARKET_TZ)
    return moment.date().isoformat()


# --------------------------------------------------------------------------- state


def _read(key: str) -> dict[str, Any]:
    for fact in memory.get_facts():
        if fact.get("key") == key:
            try:
                data = json.loads(fact.get("value") or "{}")
                return data if isinstance(data, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
    return {}


def _write(key: str, data: dict[str, Any]) -> None:
    memory.set_fact(key, json.dumps(data), confidence=1.0, source_agent="risk")


def _day_state() -> dict[str, Any]:
    """Today's tally, reset automatically when the market date rolls."""
    today = trading_day()
    state = _read(_DAY_KEY)
    if state.get("day") != today:
        state = {"day": today, "realized": 0.0, "trades": 0, "consecutive_losses": 0, "notional": 0.0}
        _write(_DAY_KEY, state)
    return state


def _broker_pnl() -> dict[str, Any]:
    """What the broker says. None values mean unreachable, not zero."""
    try:
        from . import ibkr

        out = ibkr.pnl()
        if not out.get("ok"):
            return {"reachable": False, "reason": out.get("error") or "broker unreachable"}
        return {
            "reachable": True,
            "realized": float(out.get("total_realized") or 0.0),
            "unrealized": float(out.get("total_unrealized") or 0.0),
            "positions": len(out.get("positions") or []),
        }
    except Exception as exc:
        return {"reachable": False, "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}


def day_loss() -> dict[str, Any]:
    """How much is gone today, counting open losses, taking the worse source.

    Returns a positive number for a loss. Profit reports as 0.0 - a good day does not
    buy extra room, because the limit is about survivable damage, not net position.
    """
    state = _day_state()
    ours = float(state.get("realized") or 0.0)
    broker = _broker_pnl()

    if broker.get("reachable"):
        combined = broker["realized"] + min(0.0, broker["unrealized"])
        source = "broker"
        # Take whichever is worse. A gap in either ledger must not read as a good day.
        total = min(combined, ours)
        if total == ours and ours < combined:
            source = "internal tally (worse than broker)"
    else:
        total = ours
        source = f"internal tally only - {broker.get('reason')}"

    return {
        "loss": round(abs(min(0.0, total)), 2),
        "net": round(total, 2),
        "source": source,
        "broker": broker,
        "internal_realized": round(ours, 2),
        "day": state["day"],
    }


def state() -> dict[str, Any]:
    day = _day_state()
    halt = _read(_HALT_KEY)
    loss = day_loss()
    limit = max_daily_loss()
    return {
        "day": day["day"],
        "halted": bool(halt.get("halted")),
        "halt_reason": halt.get("reason"),
        "halted_at": halt.get("at"),
        "loss_today": loss["loss"],
        "limit": limit,
        "remaining": round(max(0.0, limit - loss["loss"]), 2),
        "pct_used": round(100 * loss["loss"] / limit, 1) if limit else None,
        "trades_today": day["trades"],
        "max_trades": HARD_MAX_TRADES_PER_DAY,
        "consecutive_losses": day["consecutive_losses"],
        "notional_today": round(float(day.get("notional") or 0.0), 2),
        "max_trade_notional": max_trade_notional(),
        "pnl_source": loss["source"],
    }


# --------------------------------------------------------------------------- the gate


def check(notional: float = 0.0, *, kind: str = "trade") -> dict[str, Any]:
    """May this order be sent? The only question this module answers.

    Denials are final and say why. There is no override parameter, deliberately: a gate
    with a bypass argument gets bypassed, and the one time it matters will be the one
    time somebody passed it in a hurry.
    """
    s = state()

    if s["halted"]:
        return {
            "allowed": False,
            "reason": f"Trading is halted: {s['halt_reason']}",
            "fix": "risk action=resume once you have decided the day is worth continuing.",
            "state": s,
        }

    if s["loss_today"] >= s["limit"]:
        auto = halt(f"Daily loss limit reached: {s['loss_today']} of {s['limit']}.")
        return {
            "allowed": False,
            "reason": f"Daily loss limit reached: {s['loss_today']} of {s['limit']} allowed.",
            "halted": True,
            "state": auto.get("state"),
        }

    if s["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
        auto = halt(f"{s['consecutive_losses']} losing trades in a row.")
        return {
            "allowed": False,
            "reason": (
                f"{s['consecutive_losses']} losses in a row - standing down for the session. "
                "Repeated losses are the point where a bad day becomes an expensive one."
            ),
            "halted": True,
            "state": auto.get("state"),
        }

    if s["trades_today"] >= HARD_MAX_TRADES_PER_DAY:
        return {
            "allowed": False,
            "reason": f"{s['trades_today']} trades today, the cap is {HARD_MAX_TRADES_PER_DAY}.",
            "state": s,
        }

    value = abs(float(notional or 0.0))
    cap = s["max_trade_notional"]
    if value > cap:
        return {
            "allowed": False,
            "reason": f"Order notional {value:,.0f} exceeds the per-trade cap of {cap:,.0f}.",
            "state": s,
        }

    # An order that could, by itself, take the day past the limit is refused. Sizing to
    # the remaining room rather than the nominal cap is the whole point of a day limit.
    if value > s["remaining"] and s["remaining"] < cap:
        return {
            "allowed": False,
            "reason": (
                f"Only {s['remaining']:,.0f} of daily loss budget remains; this order risks "
                f"{value:,.0f}. Size down or stop for the day."
            ),
            "state": s,
        }

    return {"allowed": True, "kind": kind, "notional": round(value, 2), "state": s}


def record(*, pnl: float = 0.0, notional: float = 0.0, symbol: str = "", note: str = "") -> dict[str, Any]:
    """Book a closed trade into today's tally."""
    day = _day_state()
    day["realized"] = round(float(day.get("realized") or 0.0) + float(pnl or 0.0), 2)
    day["trades"] = int(day.get("trades") or 0) + 1
    day["notional"] = round(float(day.get("notional") or 0.0) + abs(float(notional or 0.0)), 2)
    day["consecutive_losses"] = (int(day.get("consecutive_losses") or 0) + 1) if pnl < 0 else 0
    _write(_DAY_KEY, day)

    try:
        memory.remember(
            f"Trade booked {symbol} pnl={pnl} notional={notional}. {note}".strip(),
            kind="trade",
            tags=["risk", "trade"],
            importance=0.7,
            source_agent="risk",
        )
    except Exception:
        pass  # the audit note is nice to have; the tally is not optional

    s = state()
    if s["loss_today"] >= s["limit"]:
        halt(f"Daily loss limit reached after {symbol or 'trade'}: {s['loss_today']} of {s['limit']}.")
    elif day["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
        halt(f"{day['consecutive_losses']} losing trades in a row.")
    return state()


def halt(reason: str = "manual") -> dict[str, Any]:
    """Stop trading. Survives restarts by design."""
    _write(_HALT_KEY, {
        "halted": True,
        "reason": reason,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
    try:
        memory.remember(f"TRADING HALTED: {reason}", kind="alert", tags=["risk", "halt"],
                        importance=1.0, source_agent="risk")
    except Exception:
        pass
    return {"ok": True, "halted": True, "reason": reason, "state": state()}


def resume(reason: str = "") -> dict[str, Any]:
    """Clear a halt. Deliberately a human decision, never automatic."""
    prior = _read(_HALT_KEY)
    if not prior.get("halted"):
        return {"ok": True, "halted": False, "note": "Not halted.", "state": state()}
    _write(_HALT_KEY, {"halted": False, "cleared_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "prior_reason": prior.get("reason"), "note": reason})
    try:
        memory.remember(f"Trading resumed after: {prior.get('reason')}. {reason}".strip(),
                        kind="alert", tags=["risk"], importance=0.9, source_agent="risk")
    except Exception:
        pass
    return {"ok": True, "halted": False, "cleared": prior.get("reason"), "state": state()}


def budget(risk_fraction: float = 0.02) -> dict[str, Any]:
    """How much to risk on the next trade, given what is left of the day.

    Sized off remaining budget rather than the account, so the last trade of a bad day
    is smaller than the first - which is the opposite of what a losing trader does.
    """
    s = state()
    if s["halted"] or s["remaining"] <= 0:
        return {"risk": 0.0, "reason": "No budget left today.", "state": s}
    per_trade = min(s["remaining"] * max(0.05, min(risk_fraction * 10, 0.5)), s["remaining"])
    return {
        "risk": round(per_trade, 2),
        "remaining_today": s["remaining"],
        "note": "Sized off what is left of today's loss budget, not off account equity.",
        "state": s,
    }


def dispatch(action: str = "state", **kwargs: Any) -> Any:
    act = (action or "state").lower()
    if act in {"state", "status", "check_state"}:
        return state()
    if act in {"check", "allow"}:
        return check(float(kwargs.get("notional") or 0), kind=str(kwargs.get("kind") or "trade"))
    if act in {"halt", "stop", "kill", "panic"}:
        return halt(str(kwargs.get("reason") or "manual"))
    if act in {"resume", "clear", "start"}:
        return resume(str(kwargs.get("reason") or ""))
    if act in {"record", "book"}:
        return record(
            pnl=float(kwargs.get("pnl") or 0),
            notional=float(kwargs.get("notional") or 0),
            symbol=str(kwargs.get("symbol") or ""),
            note=str(kwargs.get("note") or ""),
        )
    if act in {"budget", "size"}:
        return budget(float(kwargs.get("risk_fraction") or 0.02))
    if act in {"pnl", "loss"}:
        return day_loss()
    return {"error": f"unknown risk action {act}",
            "actions": ["state", "check", "halt", "resume", "record", "budget", "pnl"]}
