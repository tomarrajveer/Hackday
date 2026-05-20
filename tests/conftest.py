"""Test fixtures: isolated SQLite DB per test, FastAPI TestClient with deps overridden."""
import os
import sys
from pathlib import Path

# Ensure the repo root is importable when pytest is invoked from inside tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# These MUST be set before importing app modules — auth.py reads SECRET_KEY at
# import time, and database.py reads DATABASE_URL.
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
TEST_DB_PATH = Path(__file__).resolve().parent / "test_cricbuzz.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from database import Base, engine, get_db, SessionLocal  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Drop and recreate all tables before every test for isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def pytest_sessionfinish(session, exitstatus):
    """Remove the SQLite test DB file after the test session."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


# ───────────────────────────── helpers ──────────────────────────────

def _player(name, role="Batsman", batting_style="RHB", bowling_style=None):
    return {
        "name": name,
        "role": role,
        "batting_style": batting_style,
        "bowling_style": bowling_style,
    }


@pytest.fixture
def auth_header(client):
    """Register a user, log in, return a Bearer auth header."""
    client.post("/users/", json={"username": "scorer", "password": "hunter2"})
    r = client.post(
        "/token",
        data={"username": "scorer", "password": "hunter2"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def match_payload():
    """Minimal valid MatchCreate body — 2 batsmen + 1 bowler per side is enough for tests."""
    return {
        "format": "T20",
        "venue": "Wankhede",
        "date": "2026-03-01",
        "team_a": {
            "name": "India",
            "players": [
                _player("Rohit"),
                _player("Kohli"),
                _player("Bumrah", role="Bowler", bowling_style="RM"),
            ],
        },
        "team_b": {
            "name": "Australia",
            "players": [
                _player("Warner"),
                _player("Smith"),
                _player("Starc", role="Bowler", bowling_style="LM"),
            ],
        },
    }


@pytest.fixture
def match(client, auth_header, match_payload):
    """Create a match via the API, return its full response (with team + player IDs)."""
    r = client.post("/matches/", json=match_payload, headers=auth_header)
    assert r.status_code == 200, r.text
    return r.json()


def _player_ids(match_resp):
    """Return {team_name: {player_name: id}} for convenient lookup in tests."""
    out = {}
    for team in match_resp["teams"]:
        out[team["name"]] = {p["name"]: p["id"] for p in team["players"]}
    return out


@pytest.fixture
def players(match):
    return _player_ids(match)
