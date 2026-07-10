# WebIntel

WebIntel is a Python web intelligence platform that crawls public company websites,
extracts structured business and technical data, stores it in PostgreSQL, and exposes
searchable APIs through FastAPI.

The repository currently implements **Phases 1 and 2** of the project plan: the
application foundation, PostgreSQL and Redis infrastructure, configuration, structured
logging, health/readiness endpoints, the relational data model, Alembic migrations,
and async repositories.

## Requirements

- Docker Desktop with the Docker engine running
- Docker Compose v2+

For local Python development, Python 3.12+ and [uv](https://docs.astral.sh/uv/) are
recommended.

## Run With Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose runs `alembic upgrade head` through a one-shot migration service before the
API starts.

Then open:

- API documentation: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health>
- Dependency readiness: <http://localhost:8000/ready>

Stop the stack with `docker compose down`. Database and Redis data remain in named
volumes. Use `docker compose down --volumes` only when intentionally resetting data.

## Local Development

```powershell
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

PostgreSQL and Redis must be reachable at the URLs in `.env`. They can be started
separately with:

```powershell
docker compose up -d postgres redis
```

## Verification

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
docker compose config --quiet
```

Apply or inspect migrations outside Compose with:

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

## API Responses

`GET /health` reports whether the API process is alive. `GET /ready` actively checks
PostgreSQL and Redis and returns HTTP `503` until both dependencies respond.

## Delivery Roadmap

1. Application and infrastructure foundation (implemented)
2. SQLAlchemy models, Alembic migrations, and repositories (implemented)
3. Crawl-job API and Celery dispatch
4. URL normalization with SSRF protections and link extraction
5. HTML parsing and business-data extraction
6. Resilient HTTP fetching and robots.txt enforcement
7. Crawl worker persistence and failure handling
8. Search, filtering, technology detection, CI, and documentation polish

The crawler will reject loopback, private, link-local, and metadata-service addresses.
This is a required security boundary because crawl targets originate from API users.
