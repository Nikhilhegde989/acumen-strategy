# Customer Data Pipeline

A production-style 3-service Docker pipeline that ingests customer data from a mock REST API into PostgreSQL using [dlt](https://dlthub.com/).

## Architecture

```
┌─────────────────────────┐
│   Flask Mock Server     │  port 5000
│   (customers.json)      │
└──────────┬──────────────┘
           │ HTTP (paginated JSON)
           ▼
┌─────────────────────────┐
│  FastAPI Pipeline Svc   │  port 8000
│  dlt upsert → Postgres  │
└──────────┬──────────────┘
           │ SQLAlchemy / dlt
           ▼
┌─────────────────────────┐
│     PostgreSQL 15        │  port 5432
│     customer_db          │
└─────────────────────────┘
```

**Data flow:** `POST /api/ingest` → FastAPI fetches all pages from Flask → dlt upserts into PostgreSQL → `GET /api/customers` serves from DB.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- `docker compose` v2+

> **macOS only:** AirPlay Receiver occupies port 5000 by default. Disable it at  
> System Settings → General → AirDrop & Handoff → AirPlay Receiver → Off

## Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/Nikhilhegde989/acumen-strategy.git && cd acumen-strategy

# 2. Start all three services
docker-compose up -d

# 3. Ingest data (Flask → PostgreSQL)
curl -X POST http://localhost:8000/api/ingest
# {"status":"success","records_processed":25}

# 4. Query from the database
curl "http://localhost:8000/api/customers?page=1&limit=5"
```

Interactive API docs (Swagger UI): http://localhost:8000/docs

## Project Structure

```
acumen-strategy/
├── docker-compose.yml
├── README.md
├── mock-server/
│   ├── app.py                  # Flask app
│   ├── data/customers.json     # 25 customers
│   ├── Dockerfile
│   ├── .dockerignore
│   └── requirements.txt
└── pipeline-service/
    ├── main.py                 # FastAPI app + endpoints
    ├── schemas.py              # Pydantic response models
    ├── database.py             # SQLAlchemy engine (retry logic)
    ├── models/customer.py      # ORM model
    ├── services/ingestion.py   # dlt pipeline
    ├── Dockerfile
    ├── .dockerignore
    └── requirements.txt
```

## API Reference

### Flask Mock Server `localhost:5000`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health + customer count |
| GET | `/api/customers?page=1&limit=10` | Paginated customer list |
| GET | `/api/customers/{id}` | Single customer or 404 |

### FastAPI Pipeline Service `localhost:8000`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health + database connectivity |
| POST | `/api/ingest` | Fetch all Flask pages and upsert into PostgreSQL |
| GET | `/api/customers?page=1&limit=10` | Paginated results from database |
| GET | `/api/customers/{id}` | Single customer from database or 404 |

### Pagination Response Shape

```json
{
  "data": [...],
  "total": 25,
  "page": 1,
  "limit": 5,
  "total_pages": 5,
  "has_next": true
}
```

### Health Response (pipeline-service)

```json
{ "status": "healthy", "database": "healthy" }
```

If the database is unreachable:
```json
{ "status": "degraded", "database": "unhealthy", "database_error": "..." }
```

## Database Schema

Table: `customers` (PostgreSQL 15, schema: `public`)

| Column | Type | Constraints |
|--------|------|-------------|
| customer_id | VARCHAR(50) | PRIMARY KEY |
| first_name | VARCHAR(100) | NOT NULL |
| last_name | VARCHAR(100) | NOT NULL |
| email | VARCHAR(255) | NOT NULL |
| phone | VARCHAR(20) | |
| address | TEXT | |
| date_of_birth | DATE | |
| account_balance | DECIMAL(15,2) | |
| created_at | TIMESTAMP | |

## Environment Variables

| Variable | Value | Service |
|----------|-------|---------|
| `DATABASE_URL` | `postgresql://postgres:password@postgres:5432/customer_db` | pipeline-service |
| `DESTINATION__POSTGRES__CREDENTIALS` | same as `DATABASE_URL` | pipeline-service (dlt) |
| `FLASK_URL` | `http://mock-server:5000` | pipeline-service |
| `POSTGRES_USER` | `postgres` | postgres |
| `POSTGRES_PASSWORD` | `password` | postgres |
| `POSTGRES_DB` | `customer_db` | postgres |

## Beyond the Requirements

The assessment asked for a working 3-service pipeline. The following were added on top of that baseline to make the project production-ready:

| Addition | Why |
|----------|-----|
| **Database connectivity in `/api/health`** | The spec asked for a basic health check. A health endpoint that only confirms the process is running is not useful in production, operators need to know if the DB is actually reachable. The pipeline-service health now runs `SELECT 1` and returns `"status": "degraded"` with an error message if Postgres is down. |
| **Pydantic response models + Swagger UI** | FastAPI supports typed response schemas via `response_model=`. Adding `schemas.py` makes the auto-generated docs at `/docs` show a fully typed, explorable API, no curl required. It also enforces response shape at the framework level, catching serialization bugs early. |
| **`total_pages` and `has_next` in pagination** | The spec only required `data`, `total`, `page`, `limit`. Any frontend or API consumer needs to know whether there is a next page without doing the math themselves. These two fields are standard in production pagination APIs. |
| **Structured logging** | Neither service had any logging. Without it, debugging a failed ingest or a slow query requires guesswork. Both services now emit timestamped `[INFO]`/`[WARNING]`/`[ERROR]` logs visible via `docker-compose logs -f`. The ingestion service also logs per-page progress and total pipeline duration. |
| **Input validation with 400 errors** | The spec didn't mention bad input handling. Passing `?page=abc` or `?page=-1` would have caused an unhandled exception. Both services now return a clear `400` with an error message instead of a `500` or crash. |
| **Specific error handling in ingestion** | The original ingest would raise a generic exception on any failure. It now distinguishes between connection errors, timeouts, HTTP errors, invalid JSON from Flask, and data type conversion failures each with a descriptive message that tells you exactly what went wrong. |
| **Docker healthchecks with `condition: service_healthy`** | The spec used basic `depends_on` which only waits for a container to start, not to be ready. The pipeline-service was frequently crashing on startup because Postgres wasn't accepting connections yet. Healthchecks on all three services (`pg_isready`, `curl /api/health`) ensure each service only starts when its dependency is genuinely ready. |
| **DB connection retry logic** | Even with healthchecks, there is a small window where Postgres accepts TCP connections but isn't ready for queries. `database.py` retries the connection up to 10 times with a 3-second delay as a second safety net, eliminating any remaining race condition. |
| **`.dockerignore` files** | Without these, Docker copies `__pycache__`, `.pyc` files, `.dlt/` cache, and any `.env` files into the image. This bloats image size and risks leaking local credentials into a built image. |

## Design Decisions

**dlt for upsert** Using `write_disposition="merge"` with `primary_key="customer_id"` means re-running `POST /api/ingest` any number of times is safe: existing records are updated, no duplicates are created.

**Startup retry logic** `database.py` retries the DB connection up to 10 times (3s apart). Combined with Docker `depends_on: condition: service_healthy`, this eliminates race conditions between containers without needing `sleep` hacks.

**Separation of concerns** The Flask service deliberately serves only from JSON (simulating a 3rd-party API). The FastAPI service owns the database layer. Neither service overlaps in responsibility.

**Structured logging** Both services emit timestamped logs at INFO/WARNING/ERROR levels. Viewable via `docker-compose logs -f`.

## Useful Commands

```bash
# View live logs
docker-compose logs -f

# Rebuild after code changes
docker-compose up -d --build

# Stop services (keeps DB data)
docker-compose down

# Stop and delete all data
docker-compose down -v

# Connect directly to PostgreSQL
docker exec -it acumen-strategy-postgres-1 psql -U postgres -d customer_db
```
