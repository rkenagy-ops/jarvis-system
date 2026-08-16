"""Redact secrets before they hit disk — from isair/jarvis privacy model."""

from __future__ import annotations

import re

PATTERNS = [
    (re.compile(r"xai-[A-Za-z0-9_\-]{20,}"), "[REDACTED_XAI_KEY]"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "[REDACTED_GITHUB]"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "[REDACTED_GITHUB]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b(?:\d[ \-]?){13,19}\b"), "[REDACTED_CARD]"),
]


def redact(text: str) -> str:
    out = text or ""
    for pat, repl in PATTERNS:
        out = pat.sub(repl, out)
    return out
