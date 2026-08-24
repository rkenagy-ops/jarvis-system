"""Standing authorizations: skip the confirm token for a bounded class of operations.

Every live action in Jarvis needs a confirm_token. That is correct for a first live
order and tiresome for the twentieth paper one, so the friction lands in the wrong
place: you start reflex-confirming, which is exactly when the gate stops protecting
anything.

This does not remove the gate. It lets you pre-authorize a *narrow, bounded, expiring*
slice of it — "the next 5 SPY orders under $500, for the next hour" — and confirm
everything else as before.

Four properties make that safe:

  bounded    every grant carries a hard expiry, a use count, and per-kind limits.
             The ceilings are enforced in code (MAX_*), so nothing — not you in a
             hurry, not an agent that misread a prompt — can mint an unlimited grant.
  narrow     a grant names one kind. There is no wildcard, and no grant kind exists
             for anything not in KINDS.
  audited    every decision is written to trust_audit, whether it auto-approved,
             fell through to a confirm, or was denied. An auto-approved live order
             leaves the same trail as a confirmed one.
  revocable  revoke_all() kills every grant instantly, and is one call.

Default state is zero grants, which is byte-for-byte the old behaviour: everything
asks. Trust is something you switch on deliberately, for a while, on purpose.
"""

from __future__ import annotations

import time
from typing import Any

from . import memory

# Operations that can carry a standing grant. Anything not here always confirms.
KINDS: dict[str, str] = {
    "ibkr_stock": "Stock orders through IBKR.",
    "ibkr_option": "Option orders through IBKR.",
    "ibkr_bracket": "Bracketed entries (entry + stop + target) through IBKR.",
    "ibkr_close": "Flattening an existing position.",
    "publer_post": "Scheduling or publishing a post via Publer.",
    "engage_reply": "Posting a follow-up comment or reply.",
}

# Hard ceilings. A grant cannot exceed these no matter what is asked for.
MAX_TTL_SEC = 12 * 3600
MAX_USES = 25
MAX_NOTIONAL = 25_000.0
# oss_install is deliberately absent: it runs fetched code next to brokerage
# credentials, so it is never eligible for a standing grant.


def kinds() -> dict[str, str]:
    return dict(KINDS)


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def grant(
    kind: str,
    *,
    max_uses: int = 1,
    ttl_sec: float = 1800,
    max_notional: float | None = None,
    symbols: Any = None,
    networks: Any = None,
    note: str = "",
) -> dict[str, Any]:
    """Authorize a bounded slice of one operation kind. Caps are clamped, not trusted."""
    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        return {
            "error": f"{kind!r} cannot carry a standing grant.",
            "eligible": sorted(KINDS),
            "note": "oss_install is deliberately excluded — it executes fetched code.",
        }

    uses = int(_clamp(max_uses, 1, MAX_USES, 1))
    ttl = _clamp(ttl_sec, 60, MAX_TTL_SEC, 1800)

    constraints: dict[str, Any] = {}
    if max_notional is not None:
        constraints["max_notional"] = _clamp(max_notional, 1, MAX_NOTIONAL, 500)
    if symbols:
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",") if s.strip()]
        constraints["symbols"] = sorted({str(s).upper() for s in symbols})
    if networks:
        if isinstance(networks, str):
            networks = [n.strip() for n in networks.split(",") if n.strip()]
        constraints["networks"] = sorted({str(n).lower() for n in networks})

    # A money-moving grant with no value ceiling is not bounded in the way that matters.
    if kind.startswith("ibkr_") and "max_notional" not in constraints:
        constraints["max_notional"] = 500.0

    row = memory.add_trust_grant(kind, constraints=constraints, max_uses=uses, ttl_sec=ttl, note=note)
    memory.log_trust_decision(kind, "granted", reason=note or "standing grant created", grant_id=row["id"])
    return {
        "ok": True,
        "grant_id": row["id"],
        "kind": kind,
        "constraints": constraints,
        "max_uses": uses,
        "expires_in_sec": int(ttl),
        "clamped": {
            "max_uses": uses != int(max_uses or 1),
            "ttl_sec": ttl != float(ttl_sec or 1800),
        },
        "revoke": f"trust action=revoke grant_id={row['id']}",
    }


def _notional(payload: dict[str, Any]) -> float | None:
    """Best-effort order value. None when it cannot be established."""
    qty = payload.get("qty")
    price = payload.get("limit") or payload.get("entry") or payload.get("price")
    try:
        if qty is None or price is None:
            return None
        value = abs(float(qty)) * float(price)
    except (TypeError, ValueError):
        return None
    # Option contracts are per 100 shares.
    if payload.get("right") or payload.get("strike"):
        value *= 100
    return value


def _fits(grant_row: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, str]:
    c = grant_row.get("constraints") or {}

    allowed = c.get("symbols")
    if allowed:
        symbol = str(payload.get("symbol") or "").upper()
        if symbol not in allowed:
            return False, f"{symbol or 'no symbol'} is not in this grant's symbols {allowed}"

    nets = c.get("networks")
    if nets:
        net = str(payload.get("network") or "").lower()
        if net not in nets:
            return False, f"{net or 'no network'} is not in this grant's networks {nets}"

    cap = c.get("max_notional")
    if cap is not None:
        value = _notional(payload)
        if value is None:
            # A market order has no price to check against the cap. Unpriceable is
            # not the same as within budget — send it to a human.
            return False, "order value could not be established (market order?), so the cap cannot be applied"
        if value > float(cap):
            return False, f"order value {value:.2f} exceeds this grant's cap {float(cap):.2f}"

    return True, "within grant"


def evaluate(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Would a standing grant cover this? Read-only — spends nothing."""
    kind = (kind or "").strip().lower()
    payload = payload or {}
    if kind not in KINDS:
        return {"trusted": False, "reason": f"{kind} never carries standing grants"}

    misses = []
    for row in memory.live_trust_grants(kind):
        ok, why = _fits(row, payload)
        if ok:
            return {
                "trusted": True,
                "grant_id": row["id"],
                "reason": why,
                "remaining": row["max_uses"] - row["used"] - 1,
                "constraints": row.get("constraints") or {},
            }
        misses.append(f"{row['id']}: {why}")

    return {
        "trusted": False,
        "reason": misses[0] if misses else "no standing grant for this operation",
        "near_misses": misses[1:6] or None,
    }


def check_and_spend(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate, and if covered, spend the use. This is what the confirm gates call."""
    verdict = evaluate(kind, payload)
    if not verdict.get("trusted"):
        memory.log_trust_decision(kind, "confirm_required", reason=verdict.get("reason", ""), payload=payload)
        return verdict

    grant_id = verdict["grant_id"]
    if not memory.use_trust_grant(grant_id):
        # Expired, revoked or exhausted between evaluate and spend.
        memory.log_trust_decision(kind, "confirm_required", reason="grant no longer valid", grant_id=grant_id, payload=payload)
        return {"trusted": False, "reason": "grant expired or was revoked before it could be used"}

    memory.log_trust_decision(
        kind, "auto_approved", reason=verdict.get("reason", ""), grant_id=grant_id, payload=payload
    )
    return verdict


def revoke(grant_id: str = "", *, all_grants: bool = False) -> dict[str, Any]:
    if all_grants:
        n = memory.revoke_all_trust_grants()
        memory.log_trust_decision("*", "revoked_all", reason=f"{n} grants revoked")
        return {"ok": True, "revoked": n}
    if not grant_id:
        return {"error": "grant_id required, or pass all_grants=true."}
    if memory.revoke_trust_grant(grant_id):
        memory.log_trust_decision("*", "revoked", grant_id=grant_id)
        return {"ok": True, "revoked": 1, "grant_id": grant_id}
    return {"ok": False, "error": f"No live grant {grant_id}."}


def status() -> dict[str, Any]:
    live = memory.live_trust_grants()
    now = time.time()
    return {
        "ok": True,
        "live_grants": [
            {
                "grant_id": g["id"],
                "kind": g["kind"],
                "constraints": g.get("constraints") or {},
                "uses_left": g["max_uses"] - g["used"],
                "expires_in_sec": int(g["expires_at"] - now),
                "note": g.get("note") or None,
            }
            for g in live
        ],
        "count": len(live),
        "eligible_kinds": KINDS,
        "ceilings": {"max_ttl_sec": MAX_TTL_SEC, "max_uses": MAX_USES, "max_notional": MAX_NOTIONAL},
        "note": "No live grants means every operation confirms, which is the default.",
    }


def audit(limit: int = 25) -> dict[str, Any]:
    rows = memory.trust_audit(limit)
    return {
        "ok": True,
        "count": len(rows),
        "decisions": [
            {
                "kind": r["kind"],
                "decision": r["decision"],
                "reason": r.get("reason"),
                "grant_id": r.get("grant_id") or None,
                "payload": r.get("payload") or {},
                "at": r["created_at"],
            }
            for r in rows
        ],
        "note": "Auto-approved live actions leave the same trail as confirmed ones.",
    }


def dispatch(action: str = "status", **kwargs: Any) -> Any:
    act = (action or "status").lower()
    if act in {"status", "list", "grants"}:
        return status()
    if act in {"audit", "log", "history"}:
        return audit(int(kwargs.get("limit") or 25))
    if act in {"kinds", "eligible"}:
        return {"ok": True, "kinds": kinds(), "ceilings": {"max_ttl_sec": MAX_TTL_SEC, "max_uses": MAX_USES, "max_notional": MAX_NOTIONAL}}
    if act in {"grant", "trust", "allow"}:
        return grant(
            str(kwargs.get("kind") or ""),
            max_uses=int(kwargs.get("max_uses") or 1),
            ttl_sec=float(kwargs.get("ttl_sec") or kwargs.get("minutes", 30) * 60 if kwargs.get("minutes") else kwargs.get("ttl_sec") or 1800),
            max_notional=kwargs.get("max_notional"),
            symbols=kwargs.get("symbols"),
            networks=kwargs.get("networks"),
            note=str(kwargs.get("note") or ""),
        )
    if act in {"revoke", "cancel"}:
        return revoke(str(kwargs.get("grant_id") or ""), all_grants=bool(kwargs.get("all_grants") or kwargs.get("all")))
    if act in {"check", "evaluate", "would"}:
        return evaluate(str(kwargs.get("kind") or ""), kwargs.get("payload") or {})
    return {"error": f"unknown trust action {act}", "actions": ["status", "kinds", "grant", "revoke", "check", "audit"]}
