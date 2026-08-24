"""Shared test setup.

Two problems this fixes:

1. Tests were writing into data/jarvis.db — the real memory. A test run would
   pollute actual saved facts, messages and jobs.
2. Only some test modules called memory.init() themselves, so whether
   test_ibkr / test_ollama passed depended on whether an earlier module had
   happened to create the tables first.

Pointing the whole suite at a throwaway SQLite file and initialising it once
solves both.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True, scope="session")
def isolated_db(tmp_path_factory: pytest.TempPathFactory):
    from app import config, memory

    db_path = tmp_path_factory.mktemp("jarvis-db") / "test.db"

    # memory.py binds DB_PATH at import time, so both names need redirecting.
    config.DB_PATH = db_path
    memory.DB_PATH = db_path

    memory.init()
    yield db_path
