"""End-to-end smoke tests for the CricBuzz API.

Covers register → token → create match → score deliveries → query live state.
Each test gets a fresh in-memory SQLite (see conftest.py).
"""


def test_health_endpoint_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_endpoint_returns_ready_when_db_up(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_register_user_returns_201_with_id(client):
    r = client.post("/users/", json={"username": "alice", "password": "pw1234"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "alice"
    assert "id" in body
    assert "password" not in body


def test_duplicate_username_rejected(client):
    body = {"username": "alice", "password": "pw1234"}
    assert client.post("/users/", json=body).status_code == 201
    r = client.post("/users/", json=body)
    assert r.status_code == 400
    assert "already" in r.json()["detail"].lower()


def test_login_returns_jwt(client):
    client.post("/users/", json={"username": "scorer", "password": "hunter2"})
    r = client.post(
        "/token",
        data={"username": "scorer", "password": "hunter2"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_with_wrong_password_returns_401(client):
    client.post("/users/", json={"username": "scorer", "password": "hunter2"})
    r = client.post(
        "/token",
        data={"username": "scorer", "password": "WRONG"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 401


def test_protected_route_requires_token(client, match_payload):
    r = client.post("/matches/", json=match_payload)
    assert r.status_code == 401


def test_create_match_returns_teams_and_players(client, auth_header, match_payload):
    r = client.post("/matches/", json=match_payload, headers=auth_header)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == "T20"
    assert body["status"] == "UPCOMING"
    assert len(body["teams"]) == 2
    team_names = {t["name"] for t in body["teams"]}
    assert team_names == {"India", "Australia"}
    for team in body["teams"]:
        assert len(team["players"]) == 3


def test_score_deliveries_and_live_scorecard_reflects_runs(client, auth_header, match, players):
    match_id = match["id"]
    bumrah = players["India"]["Bumrah"]
    warner = players["Australia"]["Warner"]
    smith = players["Australia"]["Smith"]

    # Six legal deliveries: 4, 1, 0, 6, 2, 1 = 14 runs in 1 over
    runs_per_ball = [4, 1, 0, 6, 2, 1]
    for ball, runs in enumerate(runs_per_ball, start=1):
        r = client.post(
            "/scoring/delivery",
            headers=auth_header,
            json={
                "match_id": match_id,
                "innings": 1,
                "over_number": 0,
                "ball_number": ball,
                "bowler_id": bumrah,
                "batsman_id": warner if ball % 2 == 1 else smith,
                "non_striker_id": smith if ball % 2 == 1 else warner,
                "runs": runs,
            },
        )
        assert r.status_code == 200, r.text

    r = client.get(f"/scoring/match/{match_id}/live")
    assert r.status_code == 200
    body = r.json()
    assert body["1"]["runs"] == sum(runs_per_ball)
    assert body["1"]["wickets"] == 0
    assert body["1"]["overs"] == "1.0"


def test_duplicate_delivery_for_same_ball_rejected(client, auth_header, match, players):
    match_id = match["id"]
    delivery = {
        "match_id": match_id,
        "innings": 1,
        "over_number": 0,
        "ball_number": 1,
        "bowler_id": players["India"]["Bumrah"],
        "batsman_id": players["Australia"]["Warner"],
        "non_striker_id": players["Australia"]["Smith"],
        "runs": 4,
    }
    assert client.post("/scoring/delivery", json=delivery, headers=auth_header).status_code == 200
    r = client.post("/scoring/delivery", json=delivery, headers=auth_header)
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"].lower()


def test_bowler_from_same_team_as_batsman_is_rejected(client, auth_header, match, players):
    """Domain rule: bowler must be on the opposite team."""
    match_id = match["id"]
    r = client.post(
        "/scoring/delivery",
        headers=auth_header,
        json={
            "match_id": match_id,
            "innings": 1,
            "over_number": 0,
            "ball_number": 1,
            "bowler_id": players["Australia"]["Starc"],   # bowler...
            "batsman_id": players["Australia"]["Warner"], # ...same team as batsman
            "non_striker_id": players["Australia"]["Smith"],
            "runs": 0,
        },
    )
    assert r.status_code == 400
    assert "opposing" in r.json()["detail"].lower()
