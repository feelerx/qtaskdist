# qtaskdist — README

## Project overview

`qtaskdist` is a small distributed task framework focused on running quantum-related jobs. The repository contains two main components:

* `qtaskdist_api` — a FastAPI-based HTTP API and database layer that stores task metadata in PostgreSQL and pushes tasks into Redis Streams.
* `qtaskdist_worker` — worker code that listens to Redis Streams, processes circuits (simulation, conversion, backend execution), and writes results back to the database.

The project includes Docker assets (`docker-compose.yml`) to bring up the Redis, Postgres, API, and worker services locally.

---

## High-level architecture

1. Client (HTTP) -> FastAPI endpoints to create and manage tasks.
2. FastAPI persists task objects in PostgreSQL (SQLAlchemy ORM) and can enqueue tasks on Redis Streams.
3. Worker processes subscribe to different Redis Streams and perform work:

   * circuit simulation (simulate)
   * circuit-to-QIR / conversion (c_qir_convert)
   * backend execution (backend_run)
4. Workers update the `tasks` database rows with results, errors, and status.

---

## Repository layout (important files & folders)

```
qtaskdist-main/
├── docker-compose.yml
├── README.md  (existing trivial README)
├── qtaskdist_api/
│   ├── Dockerfile
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud_task.py
│   ├── queue_manager.py
│   ├── redis_client.py
│   └── scripts/create_db.py
└── qtaskdist_worker/
    ├── Dockerfile
    ├── backend_worker.py
    ├── simulator_worker.py
    ├── circuit_processor.py
    ├── models.py
    └── test_client.py
```

Each of the two top-level packages (`qtaskdist_api`, `qtaskdist_worker`) has its own `Dockerfile` and `requirements.txt` (inside `qtaskdist_api`) so they can be built/run independently.

---

## Database model

A single SQLAlchemy ORM model `Task` is defined in `qtaskdist_api/models.py` (and mirrored or referenced by worker `models.py`). Key columns include:

* `task_id` (UUID, PK)
* `task_type` (text)
* `status` (text) — default: `pending`
* `payload` (JSONB) — input data for the task
* `result` (JSONB, nullable)
* `error` (text, nullable)
* `retry_count` / `max_retries` (int)
* `created_at`, `updated_at`, `scheduled_for` (timestamps)
* `meta_data` (JSONB) — profiling or metadata

This schema supports queuing, retrying and storing execution results.

---

## Redis Streams mapping

`qtaskdist_api/queue_manager.py` defines a `STREAMS` mapping used when enqueueing a task:

* `simulate` -> `stream:simulate`
* `c_qir_convert` -> `stream:c_qir`
* `backend_run` -> `stream:backend`

When enqueueing, the API puts a message to the appropriate Redis Stream via `redis.xadd` (the redis client is `redis.asyncio` configured from `REDIS_URL`).

---

## API (what is present / how to use)

`qtaskdist_api/main.py` exposes a FastAPI app with lifespan management that closes DB engine and Redis client on shutdown. The code in `main.py` in the copy you supplied contains literal ellipses (`...`) in places which indicate missing blocks, but the following routes are present (or expected from the code & other modules):

* `POST /tasks` — Create a task (request body validated with `schemas.TaskCreate`). The implementation material is present in `crud_task.create_task`.
* `POST /tasks/{task_id}/enqueue?task_type=...` — Enqueue a persisted task onto a Redis Stream (via `queue_manager.enqueue_task`).
* `GET /tasks/{task_id}` — Fetch a specific task (response model `TaskRead`).
* `GET /tasks` — List tasks.
* `PATCH /tasks/{task_id}` — Update a task (status, result, error, etc.).

`schemas.py` defines Pydantic models used for validation and serialization: `TaskCreate`, `TaskRead`, `TaskUpdate`, and `ProfilingInfo` nested types.

---

## Worker responsibilities and behavior

There are multiple worker modules in `qtaskdist_worker`:

* `simulator_worker.py` — Contains utilities for converting circuits and performing simulation. The repository includes a `CircuitConverter` referenced by other workers.
* `backend_worker.py` — Uses Qbraid (via `QbraidProvider`) to submit circuits to an external backend. This file references environment variable `QBRAID_API_KEY` and imports `QueueProcessor` from `circuit_processor.py`. Some functions are truncated/placeholder in the current copy.
* `circuit_processor.py` — Appears to define a `QueueProcessor` type that abstracts listening to Redis streams and dispatching messages to a handler. This file also maps stream names (`STREAMS`) and contains logic for reading from streams and updating the DB.
* `test_client.py` — A small interactive script to test streams and worker functionality.

Workers typically:

1. Listen to a Redis Stream (via `XREADGROUP`/`XREAD` semantics in `redis.asyncio`).
2. Parse messages and transform `payload` JSON into Python structures.
3. Call either a simulator, converter, or submit to backend provider.
4. Update `tasks` table with `result`, `status`, `error` and increment `retry_count` if needed.

Note: Several worker source files also contain `...` or truncated functions in this copy; some logic will need to be implemented or restored.

---

## Environment variables

The repo expects configuration from environment variables (see usage in `database.py`, `redis_client.py`, worker files and `docker-compose.yml`). Key variables:

* `DATABASE_URL` — SQLAlchemy async DB URL (Postgres).
* `REDIS_URL` — full redis URL consumed by `redis.from_url` (for API service). 
* `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` — used in worker code to build connection params
* `QBRAID_API_KEY` — API key used by `backend_worker` to access Qbraid provider

`docker-compose.yml` passes environment variables into both API and worker services and defines services for `redis` and `postgres`.

---

## Docker & running locally (with docker-compose)

The repo ships a `docker-compose.yml` that defines the following services:

* `redis` using `redis:7-alpine`
* `postgres` using `postgres:15-alpine` (with volume `postgres_data`)
* `api` built from `qtaskdist_api/Dockerfile`
* `worker` built from `qtaskdist_worker/Dockerfile`

Example quick start (from repo root):

```bash
# 1) ensure .env is present and contains DATABASE_URL and REDIS_URL (and QBRAID_API_KEY if using Qbraid)
# 2) bring up the infra
docker compose up --build

# 3) create database tables (the repo contains qtaskdist_api/scripts/create_db.py)
# either run the script inside the api container, or run locally with proper env
python qtaskdist_api/scripts/create_db.py

# 4) the API should be reachable at the container's exposed port (if any exposed in your compose). Use /docs for FastAPI docs if swagger is configured.
```

**Notes**: The supplied `docker-compose.yml` uses environment variables like `${DATABASE_URL}` and `${REDIS_URL}`. Provide an appropriate `.env` file or export those variables in your shell before running `docker compose`.

---

## How to create and enqueue a task (conceptual)

1. `POST /tasks` with a `TaskCreate` payload (see `schemas.TaskCreate`) to persist the task in Postgres.
2. `POST /tasks/{task_id}/enqueue?task_type=simulate` (or `c_qir_convert`, `backend_run`) to push the task onto the corresponding Redis Stream (`stream:simulate`, etc.).
3. Worker picks up stream message, processes it, then updates DB row with `result`/`status`.

---

## Next Steps
1. **Add instructions for DB migration**: Use Alembic or ensure `scripts/create_db.py` is complete and documented to initialize DB schema.
2. **Unit/integration tests**: Add tests for queueing, worker behavior and DB CRUD operations. `qtaskdist_worker/test_client.py` then expand it into automated tests.
3. **Logging & error handling**: Ensure workers have robust retry/backoff and log messages so you can trace failed tasks.
4. **Document message format**: State exact payload JSON structure expected per `task_type` (e.g., what fields are in `payload` for simulate vs backend_run).

---

## Troubleshooting

* `Invalid DATABASE_URL` errors: verify `DATABASE_URL` uses asyncpg dialect, e.g. `postgresql+asyncpg://user:pass@postgres:5432/dbname`.
* Redis connection errors: ensure `REDIS_URL` or `REDIS_HOST` / `REDIS_PORT` are set and reachable from containers.
* Worker does not process messages: check Redis stream names (`stream:simulate`, `stream:c_qir`, `stream:backend`) and that messages are properly formatted JSON strings.

---
