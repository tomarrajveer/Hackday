# CricBuzz Live Match Tracker API

A FastAPI backend for tracking cricket matches in real time — innings, deliveries, partnerships, batsman/bowler stats, and head-to-head records. Backed by PostgreSQL, packaged with Docker, deployable to Kubernetes via Minikube or runnable locally with Docker Compose.

## Stack

- **API**: FastAPI · SQLAlchemy · Pydantic
- **Auth**: OAuth2 password flow with JWT (python-jose, passlib/bcrypt)
- **DB**: PostgreSQL 15
- **Container**: Python 3.11-slim
- **Orchestration**: Kubernetes manifests in [k8s/](k8s/) (Postgres StatefulSet + headless service, API Deployment with 2 replicas + NodePort service)

## Quick start

Pick the path that matches what you have installed.

### Option A — Minikube (recommended)

End-to-end: starts Minikube, builds the image inside Minikube's Docker daemon, applies all manifests, and opens a port-forward so the API is reachable on `http://localhost:8000`.

```bash
make up
```

When it finishes you should see:

```
✓ App is reachable at: http://localhost:8000
  Swagger UI:           http://localhost:8000/docs
  Health check:         http://localhost:8000/health
```

To tear everything down:

```bash
make down       # stops port-forward, deletes k8s resources
make clean      # also runs `minikube delete`
```

Other targets:

```bash
make logs       # tail API pod logs
make status     # pods, services, deployments
make test       # curl /health
make restart    # down + up
```

### Option B — Docker Compose (fastest for local dev)

```bash
docker compose up --build
```

API on `http://localhost:8000`, Postgres on `localhost:5432`. Stop with **Ctrl-C**, then `docker compose down -v` to clean up the volume.

> **macOS+Rancher**: if `docker compose` fails with `error getting credentials … docker-credential-osxkeychain: executable file not found`, run `export PATH="$HOME/.rd/bin:$PATH"` and try again. See [Troubleshooting](#troubleshooting) for the permanent fix.

### Option C — bare uvicorn (no containers)

Requires a running Postgres reachable via `DATABASE_URL`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:devpassword@localhost:5432/cricbuzz
export SECRET_KEY=dev-secret
uvicorn main:app --reload
```

## Prerequisites

| Tool       | Option A (k8s) | Option B (compose) | Option C (uvicorn) |
| ---------- | -------------- | ------------------ | ------------------ |
| `rancher`   | ✓              | ✓                  |                    |
| `minikube` | ✓              |                    |                    |
| `kubectl`  | ✓              |                    |                    |
| `python3`  |                |                    | ✓                  |
| Postgres   |                | (compose runs it)  | ✓ (you provide)    |

> **macOS users**: Docker Desktop won't run on some machines — use [Rancher Desktop](https://rancherdesktop.io/) with the `dockerd (moby)` engine instead.
>
> ```bash
> brew install --cask rancher
> # Open Rancher Desktop → Preferences → Container Engine → select dockerd (moby) → Apply
> docker context use rancher-desktop
> # Make Rancher's docker tooling visible to non-login shells (IDE terminals, Make):
> echo 'export PATH="$HOME/.rd/bin:$PATH"' >> ~/.zshrc
> source ~/.zshrc
> docker info   # should print server info, not an error
> ```

## Using the API

Once running, the interactive Swagger UI is at [http://localhost:8000/docs](http://localhost:8000/docs).

### 1. Register a user

```bash
curl -X POST http://localhost:8000/users/ \
  -H "Content-Type: application/json" \
  -d '{"username":"scorer","password":"hunter2"}'
```

### 2. Get a token
 
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -d "username=scorer&password=hunter2" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

### 3. Create a match (auth required)

```bash
curl -X POST http://localhost:8000/matches/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"team_a_name":"India","team_b_name":"Australia","overs":20}'
```

### 4. Score a delivery

```bash
curl -X POST http://localhost:8000/scoring/delivery \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"match_id":1,"innings":1,"over":1,"ball":1,"batsman_id":2,"non_striker_id":3,"bowler_id":6,"runs":4}'
```

### 5. Watch the live state

```bash
curl http://localhost:8000/scoring/match/1/live
curl http://localhost:8000/matches/1/summary
curl http://localhost:8000/scoring/match/1/partnerships
curl "http://localhost:8000/stats/head-to-head?team_a_name=India&team_b_name=Australia"
```

## Endpoints at a glance

| Method | Path                                     | Auth | Purpose                            |
| ------ | ---------------------------------------- | ---- | ---------------------------------- |
| GET    | `/health`                                |      | Liveness — cheap, no DB hit        |
| GET    | `/ready`                                 |      | Readiness — verifies DB reachable  |
| GET    | `/docs`                                  |      | Swagger UI                         |
| POST   | `/token`                                 |      | Exchange username/password for JWT |
| POST   | `/users/`                                |      | Register                           |
| POST   | `/matches/`                              | ✓    | Create match                       |
| GET    | `/matches/{id}`                          |      | Match by id                        |
| PATCH  | `/matches/{id}/status`                   | ✓    | Update match status                |
| GET    | `/matches/{id}/summary`                  |      | Final summary                      |
| POST   | `/scoring/delivery`                      | ✓    | Record a delivery                  |
| GET    | `/scoring/match/{id}/live`               |      | Live scorecard                     |
| GET    | `/scoring/match/{id}/batsman/{batsman}`  |      | Batsman stats                      |
| GET    | `/scoring/match/{id}/bowler/{bowler}`    |      | Bowler stats                       |
| GET    | `/scoring/match/{id}/partnerships`       |      | Partnership tracker                |
| GET    | `/stats/head-to-head`                    |      | Team vs team record                |

## Configuration

The API reads two environment variables:

| Variable       | Purpose                  | Default in k8s                  | Default in compose                                            |
| -------------- | ------------------------ | ------------------------------- | ------------------------------------------------------------- |
| `DATABASE_URL` | Postgres connection URL  | from `postgres-secret`          | `postgresql://postgres:devpassword@db:5432/cricbuzz`          |
| `SECRET_KEY`   | JWT signing secret       | from `postgres-secret`          | `local-dev-secret-key-not-for-production`                     |

For Kubernetes, edit [k8s/postgres-secret.yaml](k8s/postgres-secret.yaml) before deploying to production.

> **Note**: `SECRET_KEY` is **required at startup**. The app refuses to boot if it's missing — there is no built-in dev fallback, so a misconfigured prod can never accidentally run on a known JWT key. All three deployment paths set it for you (compose env, k8s secret, README's uvicorn export).

## Architecture

### Deployment topology

Two stateless API replicas behind a Service, fronting a single Postgres StatefulSet. Postgres exposes both a regular ClusterIP service (for the API) and a headless service (so the StatefulSet pod gets a stable DNS name).

```mermaid
flowchart TB
    client["Client<br/>(curl / Swagger / Postman)"]
    pf["kubectl port-forward<br/>(macOS) / NodePort 30080 (Linux)"]
    svc["Service: cricbuzz-api-service"]
    api1["Pod: cricbuzz-api-1<br/>FastAPI :8000"]
    api2["Pod: cricbuzz-api-2<br/>FastAPI :8000"]
    pgsvc["Service: postgres-service"]
    pg["StatefulSet: postgres-0<br/>PVC: postgres-data"]

    client -->|http :8000| pf
    pf --> svc
    svc --> api1
    svc --> api2
    api1 -->|DATABASE_URL| pgsvc
    api2 -->|DATABASE_URL| pgsvc
    pgsvc --> pg
```

In Docker Compose mode the topology collapses to a single `api` container talking to a single `db` container over Compose's default network — same code, simpler wiring.

### Code layers

```
HTTP                main.py · routers/{users,matches,scoring,stats}.py
                    │
Auth                auth.py    bcrypt hashing · JWT issue/verify · OAuth2 dependency
                    │
Schemas (I/O)       schemas.py Pydantic request/response models
                    │
Domain logic        crud.py    queries + business rules (partnerships, summaries)
                    │
Persistence         models.py  SQLAlchemy ORM
                    database.py engine + Session factory
                    │
Storage             PostgreSQL
```

### Data model

```mermaid
erDiagram
    USERS {
        int id PK
        string username
        string hashed_password
    }
    MATCHES {
        int id PK
        string team_a_name
        string team_b_name
        int overs
        enum format
        enum status
        datetime created_at
    }
    TEAMS {
        int id PK
        string name
    }
    PLAYERS {
        int id PK
        int team_id FK
        string name
    }
    DELIVERIES {
        int id PK
        int match_id FK
        int innings
        int over
        int ball
        int batsman_id FK
        int non_striker_id FK
        int bowler_id FK
        int runs
        int extras
        string extra_type
        bool is_wicket
        string wicket_type
    }
    TEAMS ||--o{ PLAYERS : has
    MATCHES ||--o{ DELIVERIES : "scored in"
    PLAYERS ||--o{ DELIVERIES : "batsman / non-striker / bowler"
```

Aggregates like batsman scores, bowler figures, current partnership, and innings totals are **computed on read** from the `deliveries` table — no denormalized scoreboard. The trade-off is correctness over write speed: scoring is append-only and idempotent, but `/scoring/match/{id}/live` does the math each time.

### Request / data flow — a typical scoring session

```mermaid
sequenceDiagram
    actor U as Scorer
    participant API as FastAPI<br/>(any pod)
    participant DB as Postgres

    U->>API: POST /users/ {username, password}
    API->>DB: INSERT user (bcrypt hash)
    DB-->>API: user row
    API-->>U: 201 Created

    U->>API: POST /token (form: username, password)
    API->>DB: SELECT user
    API->>API: verify password · sign JWT (HS256)
    API-->>U: { access_token }

    U->>API: POST /matches/ + Bearer token
    API->>API: verify JWT
    API->>DB: INSERT match
    API-->>U: match { id }

    loop one call per legal delivery
        U->>API: POST /scoring/delivery + Bearer token
        API->>DB: INSERT delivery
        API-->>U: 200 OK
    end

    U->>API: GET /scoring/match/{id}/live
    API->>DB: SELECT deliveries WHERE match_id=...
    API->>API: aggregate runs, wickets, overs, partnerships
    API-->>U: live scorecard (JSON)

    U->>API: GET /matches/{id}/summary
    API->>DB: SELECT deliveries · aggregate
    API-->>U: final result
```

**Auth boundary** — only `POST /matches/`, `PATCH /matches/{id}/status`, and `POST /scoring/delivery` require a Bearer token. Read endpoints (`/live`, `/summary`, `/partnerships`, batsman/bowler stats, head-to-head) are public, so a scoreboard frontend can poll without holding credentials.

**Statelessness** — each pod is identical and shares no in-memory state. Any pod can serve any request; horizontal scaling just means more replicas. The only stateful component is Postgres.

## Project layout

```
.
├── main.py                  FastAPI app + /token, /health, /
├── auth.py                  JWT issuance + password hashing
├── database.py              SQLAlchemy engine + session
├── models.py                ORM models
├── schemas.py               Pydantic request/response schemas
├── crud.py                  DB queries
├── routers/
│   ├── users.py             /users
│   ├── matches.py           /matches
│   ├── scoring.py           /scoring
│   └── stats.py             /stats
├── tests/
│   ├── conftest.py          Test fixtures (in-memory SQLite, TestClient)
│   └── test_api.py          End-to-end smoke tests (11 cases)
├── k8s/                     Kubernetes manifests
├── Dockerfile               Single-stage Python 3.11-slim image
├── docker-compose.yml       Local dev (api + postgres)
├── Makefile                 make up / down / test / logs / status
├── setup.sh                 Equivalent of `make up` as a plain script
├── requirements.txt         Runtime dependencies
└── requirements-dev.txt     Adds pytest + httpx for tests
```

## Running tests

```bash
make test
```

That's it. The target creates `.venv` if missing, installs `requirements-dev.txt`, and runs `pytest` — fully offline, against an in-memory-style SQLite database (no Docker, no Postgres needed).

You should see:
```
...........                                                              [100%]
11 passed in 2.5s
```

Manual invocation if you don't want to use Make:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
SECRET_KEY=test-secret pytest -q tests/
```

The 11 tests cover register → token → create match → score deliveries → live scorecard, plus the negative cases (duplicate username, wrong password, missing token, duplicate ball, bowler-on-same-team-as-batsman). See [tests/test_api.py](tests/test_api.py).

## Troubleshooting

### `error getting credentials — exec: "docker-credential-osxkeychain": executable file not found in $PATH`

You'll see this on macOS+Rancher Desktop when running `docker compose up --build` or `make up` from a terminal that hasn't picked up Rancher's PATH (common in IDE-launched terminals or sessions started before Rancher was installed). Docker's config tells it to use the `osxkeychain` credential helper, but Rancher's copy of that binary at `~/.rd/bin/` isn't on PATH.

**One-shot fix (current terminal):**

```bash
export PATH="$HOME/.rd/bin:$PATH"
docker compose up --build         # or: make up
```

**Permanent fix (all future terminals):**

```bash
echo 'export PATH="$HOME/.rd/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

> The `Makefile` already injects this PATH itself, so `make up` is immune to this issue. The bare `docker compose` command is not.

### `Cannot connect to the Docker daemon`

Rancher Desktop / Docker isn't running. Open Rancher Desktop from Applications and wait for the whale icon in the menu bar to settle.

### `port is already allocated` on 8000

Something else is already on port 8000. Either stop it, or change the host port in [docker-compose.yml:23](docker-compose.yml#L23) from `"8000:8000"` to e.g. `"8080:8000"` — then visit `http://localhost:8080`.

### `db` container never reaches healthy

```bash
docker compose logs db
```

Most likely causes: port 5432 is taken on your host, or the `postgres_data` volume is corrupt. Fix with:

```bash
docker compose down -v   # nukes the volume
docker compose up --build
```

### `make up` fails at "Starting Minikube"

Make sure Docker (or Rancher Desktop with the `dockerd` engine) is actually running. `docker info` should succeed.

### `✗ App did not become reachable` (Option A)

The port-forward is up but `/health` isn't responding. Check `make logs` for stack traces, or `make status` to see if pods are crash-looping.

### `make down` left something behind

`make clean` runs `minikube delete` which nukes the entire VM/cluster.

### Code changes not picked up after re-running `make up`

That should be fixed (the Makefile runs `kubectl rollout restart` to force pods to pull the freshly built image), but if you suspect a stale image, run `make clean && make up` to rebuild from scratch.

### `the attribute 'version' is obsolete` warning from compose

Cosmetic only — compose v2 ignores the `version: "3.9"` line. Safe to ignore or remove from [docker-compose.yml:1](docker-compose.yml#L1).
