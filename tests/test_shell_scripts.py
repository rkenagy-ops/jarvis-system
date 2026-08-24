"""Shell scripts must be pure ASCII.

PowerShell 5.1 — still the default on Windows — reads a .ps1 with no BOM as
Windows-1252, not UTF-8. An em-dash is UTF-8 E2 80 94, and 0x94 is a RIGHT DOUBLE
QUOTATION MARK in 1252, so the string terminates early and the file fails to parse
with a misleading error pointing at the next word.

That is exactly what happened to start.ps1: a single em-dash in a Write-Host string
made Jarvis unlaunchable, and the error blamed the token 'Ollama'.

Python source is safe (PEP 3120 makes UTF-8 the default), so this only applies to
the shell entrypoints.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

SCRIPTS = sorted(list(ROOT.glob("*.ps1")) + list(ROOT.glob("*.bat")) + list(ROOT.glob("*.cmd")))

# The characters most likely to slip in from prose, and their safe replacements.
DANGEROUS = {
    "—": "- (em dash)",
    "–": "- (en dash)",
    "‘": "' (left single quote)",
    "’": "' (right single quote)",
    "“": '" (left double quote)',
    "”": '" (right double quote)',
    "…": "... (ellipsis)",
    " ": "a normal space (non-breaking space)",
}


def test_there_are_scripts_to_check():
    assert SCRIPTS, "expected .ps1/.bat entrypoints at the repo root"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_is_ascii_only(script: Path):
    text = script.read_text(encoding="utf-8")
    offenders = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for ch in line:
            if ord(ch) > 126:
                hint = DANGEROUS.get(ch, "use the ASCII equivalent")
                offenders.append(f"{script.name}:{lineno} contains {ch!r} (U+{ord(ch):04X}) — replace with {hint}")
                break

    assert not offenders, (
        "Non-ASCII in a shell script breaks PowerShell 5.1, which reads .ps1 as "
        "Windows-1252 without a BOM:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_decodes_as_windows_1252(script: Path):
    """The actual failure mode: can PowerShell 5.1 read this file at all?"""
    raw = script.read_bytes()
    try:
        decoded = raw.decode("cp1252")
    except UnicodeDecodeError as exc:
        pytest.fail(f"{script.name} is not readable as Windows-1252: {exc}")

    # A stray smart quote from a mis-decoded multibyte char would appear here as a
    # quote PowerShell would honour, silently changing where strings end.
    for bad in ("“", "”", "‘", "’"):
        assert bad not in decoded, (
            f"{script.name} decodes to a smart quote under Windows-1252 — "
            "PowerShell would end a string in the wrong place"
        )
