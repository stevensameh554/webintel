# WebIntel

WebIntel is a Python web intelligence platform that crawls public company websites,
extracts structured business and technical data, stores it in PostgreSQL, and exposes
searchable APIs through FastAPI.

The repository currently implements **Phases 1 through 5** of the project plan: the
application foundation, PostgreSQL and Redis infrastructure, configuration, structured
logging, health/readiness endpoints, the relational data model, Alembic migrations,
async repositories, the crawl-job API with Celery dispatch, canonical URL handling,
link extraction, and structured HTML parsing.

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

## Crawl Jobs

Submit a crawl job:

```powershell
$body = @{ url = "https://example.com"; max_pages = 20 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/crawl-jobs `
  -ContentType application/json -Body $body
```

Available endpoints:

- `POST /api/v1/crawl-jobs`
- `GET /api/v1/crawl-jobs?status=queued&offset=0&limit=50`
- `GET /api/v1/crawl-jobs/{job_id}`
- `POST /api/v1/crawl-jobs/{job_id}/retry`

The API commits a queued job before dispatching its stable UUID to the `crawl_jobs`
Celery queue. Queue failures are stored on the job and returned as HTTP `503`. The
Phase 7 worker is intentionally not started yet, so successfully submitted jobs remain
queued until the crawler worker is implemented.

## URL And Link Rules

Phase 4 provides reusable crawler services that:

- resolve relative and protocol-relative HTTP(S) links
- lowercase and IDNA-normalize hostnames
- remove fragments, default ports, trailing slashes, and common tracking parameters
- normalize dot segments, percent escapes, and query ordering
- classify only the exact submitted hostname as internal
- ignore credentials, unsupported schemes, malformed URLs, and document fragments
- deduplicate links by normalized URL while retaining the first link text
- honor valid HTML `<base>` elements

Literal private, loopback, link-local, and metadata-service addresses are rejected.
`validate_public_url` also rejects a hostname when any DNS answer is non-public. The
Phase 6 fetcher must run this check for every redirect and bind the validated address
to the connection; validation followed by an unrelated DNS lookup would remain
vulnerable to DNS rebinding.

## HTML Extraction

`parse_html` converts complete or malformed HTML into a `ParsedPage` containing:

- title and meta description, with Open Graph description fallback
- ordered H1-H3 headings
- unique visible and `mailto:` emails with asset-like false positives removed
- normalized social profile links with sharing/content URLs excluded
- conservative important-page candidates with confidence scores
- normalized internal and external links
- a bounded visible-text preview excluding scripts, styles, templates, and comments

Important-page detection favors navigation hubs. For example, `/careers` is a careers
page, while `/careers/backend-engineer` is not automatically mislabeled as the hub.

## HTTP Fetching And Robots

Phase 6 provides a reusable async `PageFetcher` with:

- a configurable 10-second timeout and two retries with 1/3-second backoff
- manual redirects with URL and public-address validation on every hop
- DNS-rebinding protection that pins each connection to its validated IP address
- TLS certificate and hostname verification, including for pinned HTTPS connections
- structured status, final URL, content type, response time, attempt, and redirect data
- HTML/XHTML decoding with a configurable 5 MB in-memory response limit
- non-HTML detection without buffering binary response bodies
- typed timeout, network, redirect-limit, and response-size failures

`RobotsPolicy` fetches `robots.txt` through the same protected transport, caches one
policy per origin, reports crawl delay directives, and allows crawling when a robots
file is missing or temporarily unavailable. The Phase 7 worker will check this policy
before fetching each queued page.

## Delivery Roadmap

1. Application and infrastructure foundation (implemented)
2. SQLAlchemy models, Alembic migrations, and repositories (implemented)
3. Crawl-job API and Celery dispatch (implemented)
4. URL normalization with SSRF protections and link extraction (implemented)
5. HTML parsing and business-data extraction (implemented)
6. Resilient HTTP fetching and robots.txt enforcement (implemented)
7. Crawl worker persistence and failure handling
8. Search, filtering, technology detection, CI, and documentation polish

The crawler will reject loopback, private, link-local, and metadata-service addresses.
This is a required security boundary because crawl targets originate from API users.
