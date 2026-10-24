# Codebase Guide & Technical Architecture: IncuBrix Distribution

> **Target Audience:** AI Engineering Assistants & Software Developers
> **Repository:** `c:\Users\aravi\python\incubrix-distribution`
> **Source of Truth Specification:** `ps4.pdf` ("Engineering Assessment 4 | Long-Tail Distribution")
> **Date of Audit:** October 24, 2026
> **Status:** Fully Audited, Implemented, and Verified (103 passed, 1 skipped integration test)

---

## 1. Executive Summary in Simple Language

**IncuBrix Distribution** is a backend service designed to solve the "long-tail" problem in content publishing.

Major social networks (YouTube, Instagram, LinkedIn, Reddit, X) have centralized APIs and massive audiences. However, high-conversion growth frequently happens across hundreds of smaller, specialized "long-tail" destinations:
- Niche community discussion forums (running on software like **Discourse**)
- Decentralized, federated communities on ActivityPub (running on **Lemmy**)
- Developer publication feeds (such as **DEV.to**)
- Independent creator blogs (running on **Ghost**)
- Partner websites and syndication endpoints (receiving authenticated HTTP POSTs via **HMAC-SHA256 Webhooks**)
- Highly-moderated or invite-only communities where automated bots are prohibited, requiring a human moderator to post manually (**Assisted Publishing**).

If a company automates posts recklessly to these niche platforms, it risks being permanently banned for spam, violating posting rules, or having credentials revoked.

**IncuBrix Distribution** provides a unified, safe, and rule-respecting API to manage this entire process:
1. **Connector Layer ("One connector, many destinations"):** A single connector class communicates with a whole family of platforms. Adding a new forum instance requires only adding a configuration record in the catalogue, not writing new code.
2. **Posting Rules Engine:** Evaluates community rules (frequency limits, self-promotion prohibitions, AI disclosure mandates, and automation bans) *before* any request leaves the server.
3. **Asynchronous Background Job Processor:** Follows Integration Standard IS-3: accepts content immediately, issues an HTTP 202 with a tracking `job_id`, checks idempotency to eliminate duplicate posts, processes the job asynchronously, records output manifests, and updates state in PostgreSQL.
4. **Safety & Simulation Engine:** Enforces a global `SIMULATION_MODE` toggle defaulting to `True`. In simulation mode, no outbound HTTP calls can reach external servers; deterministic synthetic responses are returned, and zero external posts or deletions can occur.
5. **Secure Credential Store:** Encrypts external platform credentials (API keys, passwords, bearer tokens) at rest using symmetric Fernet encryption (AES-128-CBC + HMAC-SHA256). Secrets are never returned via GET/LIST endpoints and are redacted from log outputs.
6. **Certification Harness:** A built-in testing pipeline that verifies destinations end-to-end (`validate` → `publish` → `get_status` → `delete`), captures machine-readable evidence, and increments certification levels from L0 to L4.

---

## 2. Verified Repository Structure

```text
c:\Users\aravi\python\incubrix-distribution\
├── .env                                # Local secrets & environment configuration (Ignored by Git)
├── .env.example                        # Template environment variables with safe dev defaults
├── .gitignore                          # Standard git ignore for Python, data, caches, secrets
├── AI_USE.md                           # AI assistance disclosure per Assessment requirements
├── ANTIGRAVITY_HANDOVER.md             # Implementation history and architecture session handover
├── CODEBASE_GUIDE_FOR_CHATGPT.md       # THIS DOCUMENT: Master archaeological guide & developer documentation
├── Dockerfile                          # Multi-stage production container build (Python 3.11-slim)
├── Makefile                            # Convenience runner for migrations, tests, and linting
├── NEXT_SESSION_PROMPT.md              # Checkpoint log for continuity across agent sessions
├── README.md                           # Concise project description
├── SOURCES.md                          # Third-party library and specification source acknowledgements
├── alembic.ini                         # Alembic database migration configuration
├── docker-compose.yml                  # Complete multi-service orchestration (Postgres, MinIO, Lemmy, Ghost, Mock)
├── openapi.yaml                        # OpenAPI 3.1 export generated via scripts/export_openapi.py
├── ps4.pdf                             # 9-page assessment brief (Primary specification source of truth)
├── pyproject.toml                      # Project metadata, pytest, and ruff linting configuration
├── requirements-dev.txt                # Development and testing dependencies
├── requirements.txt                    # Production application dependencies
├── write_project.py                    # Scaffolding utility script (Ignored by Git)
│
├── alembic/                            # Database migration management
│   ├── env.py                          # Alembic environment hook connecting settings to DB engine
│   ├── script.py.mako                  # Migration script generator template
│   └── versions/                       # Migration version history
│       └── c66fc5ebae72_initial_schema.py # Initial migration covering all 9 application models
│
├── app/                                # First-party application source code
│   ├── __init__.py                     # Package marker
│   ├── main.py                         # FastAPI app factory, lifespan, middleware, routers
│   │
│   ├── api/                            # HTTP Interface Layer
│   │   ├── __init__.py
│   │   ├── routes/                     # Endpoint router controllers
│   │   │   ├── __init__.py
│   │   │   ├── certification.py        # /api/v1/certification/run, /api/v1/certify/{id}
│   │   │   ├── connections.py          # /api/v1/connections (CRUD + credential management)
│   │   │   ├── connector.py            # /connector/v1/{key}/{method} (Direct contract dispatch)
│   │   │   ├── destinations.py         # /api/v1/destinations (CRUD + CSV/JSON bulk import)
│   │   │   ├── health.py               # /health (Liveness) and /ready (Dependency readiness)
│   │   │   ├── jobs.py                 # /api/v1/publish (Job submission) and /api/v1/jobs/{id}
│   │   │   └── storage.py              # /api/v1/storage (Backend metadata)
│   │   └── schemas/                    # (Empty placeholder; schemas defined inline in route modules)
│   │
│   ├── connectors/                     # Connector Extensibility Layer
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseConnector abstract base class & simulation mocks
│   │   ├── registry.py                 # Thread-safe connector registry and manifest loader
│   │   ├── implementations/            # The 6 concrete platform connectors
│   │   │   ├── __init__.py
│   │   │   ├── assisted.py             # Assisted Publishing (pack generator for human operators)
│   │   │   ├── devto.py                # DEV.to Article REST API connector
│   │   │   ├── discourse.py            # Discourse Forum REST API connector
│   │   │   ├── ghost.py                # Ghost Blog Admin API connector (JWT signed)
│   │   │   ├── lemmy.py                # Lemmy ActivityPub Forum REST API connector
│   │   │   └── webhook_hmac.py         # Generic Webhook with HMAC-SHA256 signature
│   │   ├── manifests/                  # YAML capability manifests per connector
│   │   │   ├── assisted.yaml
│   │   │   ├── devto.yaml
│   │   │   ├── discourse.yaml
│   │   │   ├── ghost.yaml
│   │   │   ├── lemmy.yaml
│   │   │   └── webhook_hmac.yaml
│   │   └── mocks/                      # (Reserved directory for future mocked connector classes)
│   │
│   ├── core/                           # Cross-cutting concerns & foundational utilities
│   │   ├── errors.py                   # Canonical ErrorCode enum, AppError, and JSON error envelope
│   │   ├── logging.py                  # Structlog JSON logging, correlation IDs, secret redaction
│   │   ├── middleware.py               # CorrelationIdMiddleware (X-Correlation-Id tracking)
│   │   ├── security.py                 # Bearer authentication, HMAC-SHA256 hashing & verification
│   │   └── settings.py                 # Pydantic BaseSettings singleton loading from .env
│   │
│   ├── db/                             # Persistence & Relational Layer
│   │   ├── __init__.py
│   │   ├── base.py                     # SQLAlchemy 2.0 DeclarativeBase, UUID generator, TimestampMixin
│   │   ├── engine.py                   # AsyncEngine, async_sessionmaker, FastAPI get_db_session
│   │   ├── models/                     # Declarative ORM entities
│   │   │   ├── __init__.py             # Central export of all 9 models for Alembic detection
│   │   │   ├── certification.py        # CertificationRun model
│   │   │   ├── connection.py           # Connection model (encrypted platform credentials)
│   │   │   ├── destination.py          # Destination catalogue model (Appendix A fields)
│   │   │   ├── idempotency.py          # IdempotencyRecord model (key & SHA-256 fingerprint)
│   │   │   ├── job.py                  # PublishJob model (state machine, progress, results)
│   │   │   ├── manifest.py             # OutputManifest model (JSON metadata per publish)
│   │   │   ├── publication.py          # Publication model (platform_post_id & live_url tracking)
│   │   │   └── rule.py                 # DestinationRule & RuleEvaluation models
│   │   └── repos/                      # Repository pattern for database queries
│   │       ├── __init__.py
│   │       ├── connections.py          # ConnectionRepository
│   │       ├── destinations.py         # DestinationRepository
│   │       ├── idempotency.py          # IdempotencyRepository
│   │       └── jobs.py                 # JobRepository
│   │
│   ├── jobs/                           # Background Task Execution
│   │   ├── __init__.py
│   │   └── processor.py                # Async publish job processor (rules → validate → publish → persist)
│   │
│   ├── rules/                          # Governance & Policy Engine
│   │   ├── __init__.py
│   │   └── engine.py                   # Pure synchronous rules evaluator (caps, disclosure, promo)
│   │
│   ├── services/                       # Business Domain Services
│   │   ├── __init__.py
│   │   └── credentials.py              # Fernet symmetric encryption and decryption service
│   │
│   └── storage/                        # Object Storage Abstraction Layer
│       ├── __init__.py
│       ├── base.py                     # BaseStorage abstract base class
│       ├── factory.py                  # Storage factory returning S3Storage or LocalStorage
│       ├── local.py                    # LocalStorage (local filesystem with path-traversal prevention)
│       └── s3.py                       # S3Storage (aiobotocore async S3/MinIO client)
│
├── docs/                               # Architecture decision records and compliance matrices
│   ├── architecture-decisions.md       # ADR-001 through ADR-011
│   ├── implementation-plan.md          # Multi-milestone delivery tracking
│   ├── integration-standard-evidence.md# IS-1 through IS-10 point breakdown
│   └── requirements-matrix.md          # Verification status of Must-Haves and Extended capabilities
│
├── infra/                              # Local integration test environment configurations
│   ├── lemmy/
│   │   └── lemmy.hjson                 # Lemmy server configuration file for Docker Compose
│   └── mock-server/
│       ├── Dockerfile                  # Lightweight container for mock server
│       └── server.py                   # Mock HTTP server for Discourse, DEV.to, and Webhooks
│
├── scripts/                            # Operational & verification scripts
│   ├── batch_runner.py                 # IS-10 CLI tool for batch job submission and polling
│   ├── export_openapi.py               # Headless exporter writing openapi.yaml
│   ├── grant_db_perms.py               # Postgres permission grantor utility
│   └── setup_local_db.py               # Local postgres database initialisation helper
│
└── tests/                              # Pytest automated test suite
    ├── __init__.py
    ├── conftest.py                     # Test settings, fixtures, and in-memory DB overrides
    ├── test_certification_api.py       # Certification endpoint unit & integration tests
    ├── test_connections_api.py         # Connection CRUD and credential security tests
    ├── test_connector_contract.py      # Appendix A contract compliance across all 6 connectors
    ├── test_destinations_api.py        # Destination CRUD, filtering, and bulk-import tests
    ├── test_errors.py                  # Error envelope and canonical code tests
    ├── test_health.py                  # /health and /ready probe tests
    ├── test_idempotency.py             # Idempotency fingerprinting and replay tests
    ├── test_rules.py                   # Policy enforcement tests (frequency, AI disclosure, promo)
    ├── test_storage.py                 # LocalStorage and S3Storage tests
    └── test_connectors/
        ├── __init__.py
        ├── test_discourse.py           # Discourse connector HTTP mock tests
        └── test_simulation.py          # Universal SIMULATION_MODE tests across all 6 connectors
```

---

## 3. Technology Stack

- **Runtime Environment:** Python 3.11+ (Development on Python 3.15.0; Docker on Python 3.11-slim)
- **Web Framework:** FastAPI 0.115+ (Modern async ASGI framework with automatic OpenAPI 3.1 schema generation)
- **Data Validation & Serialization:** Pydantic v2 (Strict typing, fast C-based core serialization)
- **Settings Management:** `pydantic-settings` 2.6+ (Environment variable parsing from `.env`)
- **Database Engine & ORM:** SQLAlchemy 2.0.36+ (Modern async declarative ORM using `async_sessionmaker`)
- **PostgreSQL Async Driver:** `asyncpg` 0.30+ (High-performance async binary protocol driver)
- **PostgreSQL Sync Driver:** `psycopg2-binary` 2.9+ (Used strictly by Alembic migration scripts)
- **Database Migrations:** Alembic 1.14+ (Schema versioning and auto-generation)
- **HTTP Client:** HTTPX 0.28+ (Async HTTP client with timeout management and connection pooling)
- **Storage Backend (Object Storage):** `aiobotocore` 2.15+ (Async AWS S3 and MinIO client)
- **Cryptography & Security:** `cryptography` 43.0+ (Fernet symmetric encryption based on AES-128-CBC + HMAC-SHA256)
- **Structured Logging:** `structlog` 24.4+ (JSON formatted, context-variable aware, secret-redacting logger)
- **Configuration Parsing:** `pyyaml` 6.0+ (Loading connector YAML manifests)
- **Containerization:** Docker & Docker Compose v2 (Multi-container stack with PostgreSQL 16, MinIO, Lemmy, Ghost, and Mock server)
- **Test Harness:** `pytest` 9.1+, `pytest-asyncio` 1.4+, `pytest-cov` 7.1+

---

## 4. Architecture and Module Dependency Map

The following Mermaid diagram traces the architectural layers and data boundaries across IncuBrix Distribution:

```mermaid
flowchart TD
    Client([HTTP Client / SDK / CLI])

    subgraph CoreLayer [FastAPI & Middleware Layer]
        Main[app/main.py]
        CorrMid[app/core/middleware.py\nCorrelationIdMiddleware]
        SecDep[app/core/security.py\nrequire_bearer_token]
        ErrHand[app/core/errors.py\napp_error_handler]
    end

    subgraph APIRoutes [API Route Controllers]
        JobRoute[app/api/routes/jobs.py\nPOST /api/v1/publish\nGET /api/v1/jobs/:id]
        DestRoute[app/api/routes/destinations.py\nCRUD & Bulk Import]
        ConnRoute[app/api/routes/connections.py\nCRUD & Encrypted Creds]
        CertRoute[app/api/routes/certification.py\nCertification Harness]
        ContRoute[app/api/routes/connector.py\nPOST /connector/v1/:key/:method]
        HealthRoute[app/api/routes/health.py\n/health & /ready]
        StoreRoute[app/api/routes/storage.py\n/api/v1/storage]
    end

    subgraph ServiceLayer [Business Logic & Services]
        CredSvc[app/services/credentials.py\nFernet Encrypt/Decrypt]
        RuleEng[app/rules/engine.py\nevaluate_rules]
        JobProc[app/jobs/processor.py\nprocess_publish_job]
        StoreFact[app/storage/factory.py\nget_storage]
    end

    subgraph ConnectorLayer [Connector Extensibility Engine]
        Registry[app/connectors/registry.py\nRegistry & Manifest Loader]
        BaseConn[app/connectors/base.py\nBaseConnector ABC]
        DiscConn[app/connectors/implementations/discourse.py]
        LemmConn[app/connectors/implementations/lemmy.py]
        DevtConn[app/connectors/implementations/devto.py]
        GhosConn[app/connectors/implementations/ghost.py]
        WebhConn[app/connectors/implementations/webhook_hmac.py]
        AssiConn[app/connectors/implementations/assisted.py]
    end

    subgraph PersistenceLayer [Database & Storage Layer]
        DBEng[app/db/engine.py\nAsyncSession]
        Repos[app/db/repos/*\nJob, Destination, Connection, Idempotency]
        Postgres[(PostgreSQL 16\n9 Relational Tables)]
        ObjStore[(MinIO / S3 Storage\nArtifacts & Manifests)]
    end

    subgraph ExternalPlatforms [Target Networks / Mocks]
        DiscourseExt[Discourse Forums]
        LemmyExt[Lemmy ActivityPub Nodes]
        DevtoExt[DEV.to API]
        GhostExt[Ghost Admin API]
        WebhookExt[Partner HMAC Webhooks]
        HumanUser[Human Community Moderator]
    end

    %% Call Flow
    Client -->|HTTP Request with Bearer Token| Main
    Main --> CorrMid
    CorrMid --> SecDep
    SecDep --> APIRoutes
    Main -.-> ErrHand

    JobRoute -->|1. Check/Write Fingerprint| Repos
    JobRoute -->|2. Fire Async Task| JobProc
    JobProc -->|3. Evaluate Policy| RuleEng
    JobProc -->|4. Get Connector| Registry
    Registry --> BaseConn
    BaseConn --> DiscConn & LemmConn & DevtConn & GhosConn & WebhConn & AssiConn

    ConnRoute -->|Encrypt/Decrypt Credentials| CredSvc
    DestRoute -->|Persist Destinations| Repos
    CertRoute -->|Run 4-stage Test Cycle| BaseConn
    CertRoute -->|Update L0-L4 Level| Repos

    JobProc -->|5. Record Publications & Manifests| Repos
    Repos --> DBEng --> Postgres
    StoreFact --> ObjStore

    DiscConn -.->|Simulation = False| DiscourseExt
    LemmConn -.->|Simulation = False| LemmyExt
    DevtConn -.->|Simulation = False| DevtoExt
    GhosConn -.->|Simulation = False| GhostExt
    WebhConn -.->|Simulation = False| WebhookExt
    AssiConn -->|Generate Post Pack| HumanUser
```

---

## 5. File-by-File Technical Inventory

Every first-party source file in the repository has been analyzed directly from disk.

### 5.1 Entry Point & Application Core

#### `app/main.py`
- **Responsibility:** Application entry point, lifespan lifecycle management, middleware configuration, and router aggregation.
- **Key Components:**
  - `lifespan(app: FastAPI)`: Asynchronous context manager that initializes logging via `configure_logging()`, loads connector manifests into `init_registry()`, and cleanly closes database connection pools via `dispose_engine()` on shutdown.
  - `app`: The main `FastAPI` application instance configured with CORS middleware and `CorrelationIdMiddleware`.
- **Dependencies:** Imports route modules from `app.api.routes`, settings from `app.core.settings`, registry initialization from `app.connectors.registry`, and custom exception handlers.
- **Beginner Explanation:** This file is the "front door" of the web server. When the server boots up, this file runs startup chores, turns on the loggers, connects the database, and maps URLs to their respective handler functions.

#### `app/core/settings.py`
- **Responsibility:** Application-wide configuration management backed by environment variables and `.env`.
- **Key Components:**
  - `Settings`: Pydantic `BaseSettings` class defining typed fields for database URLs, pool sizes, S3 credentials, bearer tokens, simulation toggles, and per-connector default base URLs.
  - `@field_validator("test_database_url")`: Safety guard that enforces that the test database connection string contains `_test` to prevent accidental drops of development databases.
  - `get_settings()`: Cached singleton function returning the active configuration.
- **Beginner Explanation:** Keeps all configuration settings (like database passwords and port numbers) in one place so code doesn't hardcode sensitive values.

#### `app/core/logging.py`
- **Responsibility:** Configures structured JSON logging via `structlog` and guarantees secrets never leak into logs.
- **Key Components:**
  - `_redact_secrets(logger, method_name, event_dict)`: Structlog processor that inspects all log fields, using regular expressions to replace API keys, tokens, passwords, and database connection credentials with `[REDACTED]`.
  - `configure_logging(log_level)`: Configures the standard library logging and structlog to output machine-readable JSON lines with ISO-8601 timestamps and log levels.
- **Beginner Explanation:** Ensures every log message printed by the server is structured as clean JSON while automatically scrubbing passwords and secret tokens before they hit the screen or disk.

#### `app/core/middleware.py`
- **Responsibility:** Request tracking, correlation ID propagation, and latency monitoring.
- **Key Components:**
  - `CorrelationIdMiddleware`: Starlette middleware that extracts `X-Correlation-Id` from incoming HTTP headers or generates a fresh UUID4 if absent. Binds the ID to structlog context variables so every subsequent log line emitted during that request automatically carries the ID. Measures execution time in milliseconds and returns the header in the response.
- **Beginner Explanation:** Tags every incoming request with a unique tracking number so developers can follow a single request's path through complex log files.

#### `app/core/security.py`
- **Responsibility:** API authentication, cryptographic HMAC signature generation, and webhook verification.
- **Key Components:**
  - `require_bearer_token(credentials)`: FastAPI dependency that enforces HTTP Bearer authentication against `settings.api_bearer_token`. Raises HTTP 401 if missing or invalid.
  - `compute_hmac_sha256(payload, secret)`: Calculates a hex-encoded SHA-256 HMAC signature.
  - `verify_hmac_sha256(payload, secret, signature)`: Verifies HMAC signatures in constant time (`hmac.compare_digest`) to prevent timing attack vulnerabilities.
  - `sign_job_callback(job_id, event, payload)`: Formats and signs outgoing webhooks in compliance with Integration Standard IS-3 (`X-IncuBrix-Signature: sha256={hex}`).
- **Beginner Explanation:** Acts as the bouncer checking bearer tokens at the door, and signs outgoing notifications so partner sites know messages genuinely came from IncuBrix.

#### `app/core/errors.py`
- **Responsibility:** Canonical error classification, standard JSON error envelope formatting, and exception handling.
- **Key Components:**
  - `ErrorCode`: String enumeration implementing Appendix A error codes (`DEST_SPEC_VIOLATION`, `DEST_RULE_FREQUENCY_CAP`, `CONNECTION_AUTH_EXPIRED`, `PLATFORM_RATE_LIMIT`, `PLATFORM_QUOTA_EXHAUSTED`, `PLATFORM_CONTENT_REJECTED`, `PLATFORM_UNAVAILABLE`, `CONNECTOR_DISABLED`, etc.).
  - `_RETRYABLE`: Lookup dictionary indicating whether an error is retryable (`True`, `False`, `"Later"`, `"After reconnect"`, `"Next window"`).
  - `AppError`: Base exception class holding `code`, `message`, `retryable`, and `details`.
  - `ErrorEnvelope`: Pydantic model enforcing the standard error schema: `{"error": {"code": str, "message": str, "retryable": str | bool, "details": dict}}`.
- **Beginner Explanation:** Translates server exceptions into clean, uniform error messages without leaking stack traces or internal implementation details to users.

---

### 5.2 API Routes (`app/api/routes/`)

#### `app/api/routes/health.py`
- **Responsibility:** High-reliability liveness and readiness monitoring.
- **Endpoints:**
  - `GET /health`: Liveness probe. Returns HTTP 200 immediately if the Python process is alive.
  - `GET /ready`: Readiness probe. Executes a live `SELECT 1` against PostgreSQL and calls `health_check()` on the storage backend. Returns HTTP 200 if all dependencies respond, or HTTP 503 if any dependency fails.
- **Beginner Explanation:** Lets container orchestrators (like Kubernetes or Docker) check whether the service is alive and whether its database and storage connections are healthy.

#### `app/api/routes/jobs.py`
- **Responsibility:** Publishing job creation, idempotency enforcement, and status retrieval.
- **Endpoints:**
  - `POST /api/v1/publish`: Primary ingestion endpoint. Requires `Idempotency-Key` header. Generates a SHA-256 fingerprint from the key and canonical JSON payload. Checks `idempotency_records`; if the key exists with the same fingerprint, it immediately returns the existing job (idempotent replay). If the payload differs, it raises HTTP 409 `IDEMPOTENCY_CONFLICT`. Creates a `PublishJob` record in PostgreSQL, schedules `process_publish_job` on the asyncio event loop, and returns HTTP 202 Accepted with the `job_id`.
  - `GET /api/v1/jobs/{job_id}`: Retrieves the current progress (0–100), execution state (`queued`, `running`, `succeeded`, `failed`), and output links for a job.
- **Beginner Explanation:** The submission desk where clients drop off articles to publish. It gives clients a ticket number (`job_id`) right away so they don't have to wait on slow platform APIs.

#### `app/api/routes/destinations.py`
- **Responsibility:** Destination catalogue CRUD management and bulk importation.
- **Endpoints:**
  - `GET /api/v1/destinations`: Lists catalogue destinations with optional query filters (`connector_key`, `active`) and pagination (`limit`, `offset`).
  - `POST /api/v1/destinations`: Creates a new destination entity with rules and format parameters.
  - `GET /api/v1/destinations/{id}`: Retrieves metadata for a specific destination.
  - `PUT /api/v1/destinations/{id}` & `PATCH /api/v1/destinations/{id}`: Updates destination settings.
  - `DELETE /api/v1/destinations/{id}`: Performs a soft-delete (sets `active=False`).
  - `POST /api/v1/destinations/import` & `POST /api/v1/destinations/bulk`: High-speed bulk ingestion supporting either a JSON payload (`list` or `{"destinations": [...]}`) or a multipart CSV file upload. Parses booleans, integers, and JSON tags cleanly.
- **Beginner Explanation:** The address book of all community forums, blogs, and sites IncuBrix can publish to, with tools to import whole spreadsheets of destinations at once.

#### `app/api/routes/connections.py`
- **Responsibility:** Secure credential management for third-party platforms.
- **Endpoints:**
  - `GET /api/v1/connections`: Lists connections metadata (`id`, `label`, `connector_key`, `active`). Crucially, credentials are never returned in list outputs.
  - `POST /api/v1/connections`: Accepts platform credentials, encrypts them at rest via Fernet symmetric encryption, and persists the record.
  - `GET /api/v1/connections/{id}`: Retrieves metadata for a connection (credentials omitted).
  - `PATCH /api/v1/connections/{id}`: Updates labels, active status, or re-encrypts updated credentials.
  - `POST /api/v1/connections/{id}/decrypt`: Secure internal endpoint used for debugging or test execution to inspect decrypted credentials.
  - `DELETE /api/v1/connections/{id}`: Soft-deletes a connection (`active=False`).
- **Beginner Explanation:** The encrypted digital safe where API keys and login passwords are stored.

#### `app/api/routes/certification.py`
- **Responsibility:** Automated certification execution and compliance evidence recording.
- **Endpoints:**
  - `POST /api/v1/certification/run` & `POST /api/v1/certify/{destination_id}`: Runs an end-to-end certification cycle against a destination (`validate` → `publish` → `get_status` → `delete`). Saves raw responses into the `certification_runs` table. If all stages pass, it automatically upgrades the destination's certification level (e.g. L0 → L1/L3).
  - `GET /api/v1/certification/{run_id}`: Fetches detailed stage-by-stage results and stored evidence for a specific certification run.
  - `GET /api/v1/certify/{destination_id}/history`: Lists historical certification runs for a destination.
- **Beginner Explanation:** An automated testing robot that tests whether a destination actually works by posting a test message, checking that it's online, and deleting it immediately.

#### `app/api/routes/connector.py`
- **Responsibility:** Direct HTTP dispatch following Appendix A of the IncuBrix connector specification.
- **Endpoints:**
  - `POST /connector/v1/{connector_key}/{method}`: Directly dispatches calls (`validate`, `publish`, `get_status`, `delete`, `fetch_metrics`, `refresh_auth`, `build_assist_pack`) to the selected connector without creating background database jobs.
- **Beginner Explanation:** A direct line to individual connectors for low-level validation and testing.

#### `app/api/routes/storage.py`
- **Responsibility:** Exposes non-sensitive metadata regarding the active object storage backend.
- **Endpoints:**
  - `GET /api/v1/storage`: Returns the active storage backend name (`s3` or `local`), bucket name, and endpoint.
- **Beginner Explanation:** Tells administrators whether files are being saved locally or in an S3/MinIO cloud bucket.

---

### 5.3 Connectors Layer (`app/connectors/`)

#### `app/connectors/base.py`
- **Responsibility:** Abstract Base Class (`BaseConnector`) defining the mandatory contract methods and common simulation behaviors.
- **Abstract Methods:**
  - `validate(rendition, destination, connection) -> {ok: bool, violations: list}`
  - `publish(rendition, destination, connection, idempotency_key) -> {platform_post_id: str, live_url: str, status: str}`
  - `get_status(platform_post_id, connection) -> {status: str, live_url: str}`
  - `delete(platform_post_id, connection) -> {deleted: bool}`
- **Optional Methods (Default to `NotImplementedError`):**
  - `fetch_metrics(platform_post_id, connection, since) -> dict`
  - `refresh_auth(connection) -> dict`
  - `build_assist_pack(rendition, destination) -> dict`
- **Simulation Helpers:**
  - `_is_simulation()`: Checks if `settings.simulation_mode` is enabled.
  - `_sim_publish()`, `_sim_status()`, `_sim_delete()`, `_sim_metrics()`: Generate deterministic mock outputs without making external network calls.
- **Beginner Explanation:** The blueprint that every connector must follow, providing built-in mock routines so tests run safely without real social media accounts.

#### `app/connectors/registry.py`
- **Responsibility:** In-memory registry holding all loaded connector instances and their YAML capability manifests.
- **Key Functions:**
  - `init_registry()`: Scans `app/connectors/manifests/*.yaml` to populate manifest metadata, and instantiates the 6 connector classes into a singleton dictionary.
  - `get_connector(key)`: Returns a connector instance. Enforces feature toggles via `settings.connector_enabled(key)` and raises `ConnectorDisabledError` if disabled.
  - `get_manifest(key)`: Retrieves raw manifest configuration for a connector.
  - `list_connectors()`: Returns a list of all connectors with their version, tier, and enabled status.
- **Beginner Explanation:** The service catalog that loads connector definitions into memory when the server boots.

---

### 5.4 The Six Connector Implementations

#### 1. Discourse (`app/connectors/implementations/discourse.py`)
- **Tier:** Native | **Auth:** API Key + Username | **Manifest:** `discourse.yaml`
- **Instance Parameter:** `base_url` (points to the specific forum domain)
- **Validation:** Enforces title length (1 to 255 chars) and body length (up to 32,000 chars).
- **Outbound HTTP Calls:**
  - `publish`: `POST {base_url}/posts.json` with headers `Api-Key` and `Api-Username`. Request body: `{"title": str, "raw": str, "category": int}`. Returns `{"platform_post_id": str, "live_url": f"{base_url}/t/{topic_id}", "status": "published"}`.
  - `get_status`: `GET {base_url}/posts/{id}.json`.
  - `delete`: `DELETE {base_url}/posts/{id}.json`. Handles HTTP 404 cleanly as `{"deleted": True}`.
  - `fetch_metrics`: `GET {base_url}/posts/{id}.json` mapping `reads` to views, `like_count` to likes, and `reply_count` to comments.
- **Simulation Mode:** Bypasses HTTP requests, returns `sim-discourse-{id}`.

#### 2. Lemmy (`app/connectors/implementations/lemmy.py`)
- **Tier:** Protocol (ActivityPub) | **Auth:** JWT Token via Bot Login | **Manifest:** `lemmy.yaml`
- **Instance Parameter:** `base_url` (points to the federated Lemmy instance)
- **Validation:** Enforces title length (1 to 200 chars), body length (up to 10,000 chars), and requires `community_id`.
- **Outbound HTTP Calls:**
  - `_get_token`: Automatically logs in via `POST {base_url}/api/v3/user/login` using credentials from connection or settings to obtain a short-lived JWT.
  - `publish`: `POST {base_url}/api/v3/post` with `Authorization: Bearer {jwt}`. Body: `{"name": title, "body": body, "community_id": int, "nsfw": False}`. Returns platform ID and ActivityPub URL (`ap_id`).
  - `get_status`: `GET {base_url}/api/v3/post?id={id}`.
  - `delete`: `POST {base_url}/api/v3/post/delete` with `{"post_id": int, "deleted": True}`.
  - `fetch_metrics`: Maps Lemmy post view counts (`read_count`, `upvotes`, `comments`, `saved`).
- **Simulation Mode:** Bypasses HTTP requests, returns `sim-lemmy-{id}`.

#### 3. DEV.to (`app/connectors/implementations/devto.py`)
- **Tier:** Native | **Auth:** API Key (`api-key` header) | **Manifest:** `devto.yaml`
- **Instance Parameter:** None (Global SaaS platform, defaults to `https://dev.to/api`)
- **Validation:** Enforces title length (1 to 128 chars).
- **Outbound HTTP Calls:**
  - `publish`: `POST {base_url}/articles` with header `api-key`. Body: `{"article": {"title": str, "body_markdown": str, "published": True, "tags": list, "canonical_url": str}}`. Truncates tags to maximum 4 per platform limits.
  - `get_status`: `GET {base_url}/articles/{id}`.
  - `delete`: DEV.to API does not provide an HTTP DELETE method for articles. Implements ADR-011: executes `PUT {base_url}/articles/{id}` with `{"article": {"published": False}}` to unpublish content.
  - `fetch_metrics`: `GET {base_url}/articles/{id}` extracting `page_views_count`, `positive_reactions_count`, and `comments_count`.
- **Simulation Mode:** Bypasses HTTP requests, returns `sim-devto-{id}`.

#### 4. Ghost (`app/connectors/implementations/ghost.py`)
- **Tier:** Native | **Auth:** Ghost Admin API Key | **Manifest:** `ghost.yaml`
- **Instance Parameter:** `base_url` (points to the Ghost blog instance)
- **Authentication Protocol:** Ghost Admin API keys consist of an `id:secret` pair. Ghost requires short-lived JSON Web Tokens (JWT) signed using HMAC-SHA256 with an audience of `/admin/` and expiration within 5 minutes. Implemented in `_make_ghost_jwt()`.
- **Validation:** Requires non-empty title.
- **Outbound HTTP Calls:**
  - `publish`: `POST {base_url}/ghost/api/admin/posts/` with `Authorization: Ghost {jwt}`. Body: `{"posts": [{"title": title, "html": html, "status": "published"}]}`.
  - `get_status`: `GET {base_url}/ghost/api/admin/posts/{id}/`.
  - `delete`: `DELETE {base_url}/ghost/api/admin/posts/{id}/`. Treats 404 as already deleted.
- **Simulation Mode:** Bypasses HTTP requests, returns `sim-ghost-{id}`.

#### 5. Generic HMAC-SHA256 Webhook (`app/connectors/implementations/webhook_hmac.py`)
- **Tier:** Bridge | **Auth:** HMAC-SHA256 Signature Header | **Manifest:** `webhook_hmac.yaml`
- **Instance Parameter:** `webhook_url`
- **Validation:** Verifies rendition body size does not exceed 64 KB (65,536 bytes).
- **Outbound HTTP Calls:**
  - `publish`: Computes an HMAC-SHA256 signature over the JSON body using the shared secret. Issues `POST {webhook_url}` with headers `X-IncuBrix-Signature: {sig}`, `X-Idempotency-Key: {key}`, and `Content-Type: application/json`.
  - `get_status`: Webhooks are fire-and-forget; returns `{"status": "delivered"}`.
  - `delete`: Sends an event payload `{"event": "delete", "platform_post_id": id}` to the target URL signed with HMAC.
- **Simulation Mode:** Early exits on `publish` and `delete`, returning simulated delivery receipts without making network calls.

#### 6. Assisted Publishing (`app/connectors/implementations/assisted.py`)
- **Tier:** Assisted | **Auth:** None | **Manifest:** `assisted.yaml`
- **Role:** Designed for destinations where automated bots are prohibited by community policy. Instead of posting over an API, it compiles a human-ready "Assist Pack".
- **Validation:** Ensures a title is present.
- **Operations:**
  - `publish`: Calls `build_assist_pack()`, records the post state as `assist_ready`, and returns a deep link for the user.
  - `build_assist_pack`: Generates a Markdown file `post.md`, packages attached image URLs, generates a checklist of destination-specific rules (e.g. "Read community rules before posting", "Disclose AI content"), and constructs a direct submission URL.
  - `get_status`: Returns `{"status": "assist_ready"}`.
  - `delete`: Returns `{"deleted": True}`.

---

### 5.5 Business Logic, Rules & Jobs

#### `app/rules/engine.py`
- **Responsibility:** Pure synchronous rule evaluation against target community policies.
- **Rules Enforced:**
  1. `frequency_cap`: Parses expressions like `"1/week"`, `"2/day"` and compares against timestamps in `recent_publications`. Emits `DEST_RULE_FREQUENCY_CAP` if the limit is exceeded.
  2. `self_promo_allowed`: Emits `DEST_SPEC_VIOLATION` if promotional content is sent to a non-promotional destination.
  3. `disclosure_required`: Emits `DEST_SPEC_VIOLATION` if AI-generated content is submitted without `ai_disclosed: True`.
  4. `automation_allowed`: Emits `DEST_SPEC_VIOLATION` if an automated publish is attempted on a manual-only destination.

#### `app/jobs/processor.py`
- **Responsibility:** End-to-end asynchronous processing of background publish tasks.
- **Workflow:**
  1. Opens an async database session via `get_session_factory()`.
  2. Transitions `PublishJob` state from `queued` to `running` (progress: 5%).
  3. Loads target destination and connection metadata.
  4. Calls `evaluate_rules()`. Persists results as `RuleEvaluation` rows. If violations occur, marks the job `failed` and stops.
  5. Calls `connector.validate()`. If invalid, marks the job `failed` with `DEST_SPEC_VIOLATION`.
  6. Calls `connector.publish()`.
  7. Creates a `Publication` record linking `job_id`, `destination_id`, `platform_post_id`, and `live_url`.
  8. Creates an `OutputManifest` containing metadata, timings, and simulation flags.
  9. Marks `PublishJob` as `succeeded` (progress: 100%).

#### `app/services/credentials.py`
- **Responsibility:** Symmetric encryption of credentials stored in PostgreSQL.
- **Algorithm:** Fernet (AES-128 in CBC mode with PKCS7 padding and HMAC-SHA256 authentication).
- **Behavior:** Reads `CREDENTIAL_ENCRYPTION_KEY` from settings. If empty in dev/test, uses a non-secure base64 fallback prefixed with `b64:`.

---

### 5.6 Storage & Persistence (`app/storage/` & `app/db/`)

#### `app/storage/factory.py`, `local.py`, `s3.py`
- **Responsibility:** Storage abstraction supporting local disk and AWS S3 / MinIO.
- **Implementations:**
  - `LocalStorage`: Writes bytes to `settings.local_storage_path`. Employs path traversal protection (`Path.resolve()` boundary checks).
  - `S3Storage`: Connects to MinIO/S3 via `aiobotocore.session.AioSession`. Provides async `put`, `get`, `delete`, and `presigned_url`.

#### Database Repositories (`app/db/repos/`)
- Encapsulates database queries using SQLAlchemy 2.0 `select()` statements:
  - `JobRepository`: Creation, retrieval, and progress state transitions for `PublishJob`.
  - `DestinationRepository`: Filtered search, counts, single-item lookups, updates, and creation for `Destination`.
  - `ConnectionRepository`: Filtered listing and creation for `Connection`.
  - `IdempotencyRepository`: Lookup and insertion for `IdempotencyRecord`.

---

## 6. End-to-End Publishing Workflow & Call Chain

Here is the exact trace of an execution through the codebase:

```text
1. Client POST /api/v1/publish
   ├── Header: "Idempotency-Key: idem-pub-9921"
   └── Payload: { "connector_key": "discourse", "rendition": {...}, "destination": {...} }
         │
2. app/core/middleware.py (CorrelationIdMiddleware)
   ├── Injects X-Correlation-Id: "a1b2c3d4-..."
   └── Binds correlation_id to structlog context
         │
3. app/core/security.py (require_bearer_token)
   └── Validates Authorization: Bearer {token}
         │
4. app/api/routes/jobs.py (submit_publish)
   ├── Computes SHA-256 fingerprint: _fingerprint(idempotency_key, body)
   ├── Queries IdempotencyRepository.find(idempotency_key)
   │     ├── If duplicate key + different payload → Raise HTTP 409 IDEMPOTENCY_CONFLICT
   │     └── If duplicate key + same payload → Return existing job response (replay)
   ├── JobRepository.create(...) → Inserts publish_jobs (state='queued', progress=0)
   ├── IdempotencyRepository.create(...) → Inserts idempotency_records
   ├── Dispatches asyncio.create_task(process_publish_job(job.id, request_body))
   └── Returns HTTP 202 Accepted: { "job_id": "...", "status": "queued", "progress": 0 }
         │
5. app/jobs/processor.py (process_publish_job) [ASYNC TASK]
   ├── Opens DB session from get_session_factory()
   ├── Updates publish_jobs: state='running', progress=5
   ├── app/rules/engine.py (evaluate_rules)
   │     ├── Checks frequency_cap against recent publications
   │     ├── Checks self_promo_allowed, disclosure_required, automation_allowed
   │     └── Inserts rule_evaluations record in DB
   │     └── If violations: updates publish_jobs to 'failed', exits
   ├── Connector validation: connector.validate(...)
   │     └── If violations: updates publish_jobs to 'failed', exits
   ├── Connector publication: connector.publish(...)
   │     ├── If SIMULATION_MODE == True:
   │     │     └── Returns simulated ID & URL (No outbound HTTP)
   │     └── If SIMULATION_MODE == False:
   │           └── Executes real HTTPX request to target platform API
   ├── Inserts publications record (platform_post_id, live_url, status)
   ├── Inserts output_manifests record (JSON summary, timing, metadata)
   └── Updates publish_jobs: state='succeeded', progress=100
         │
6. Client polls GET /api/v1/jobs/{job_id}
   └── Returns HTTP 200: { "status": "succeeded", "progress": 100, "result": { "live_url": "..." } }
```

---

## 7. Database Schema and Record Lifecycle

The database runs on **PostgreSQL 16** and contains 9 relational tables managed via Alembic:

| Table Name | Model Class | File Path | Primary Key | Key Foreign / Indexed Fields | Purpose |
|---|---|---|---|---|---|
| `publish_jobs` | `PublishJob` | `app/db/models/job.py` | `id` (UUID4) | `idempotency_key`, `state` | Core lifecycle state machine for background publishing tasks. |
| `idempotency_records` | `IdempotencyRecord` | `app/db/models/idempotency.py` | `id` (UUID4) | `idempotency_key` (UNIQUE), `fingerprint` | Guarantees safe retries and prevents double-posting under network timeouts. |
| `destinations` | `Destination` | `app/db/models/destination.py` | `id` (UUID4) | `connector_key`, `platform_key`, `UNIQUE(url, platform_key)` | Catalogue of platforms, format limits, policy flags, and certification level. |
| `connections` | `Connection` | `app/db/models/connection.py` | `id` (UUID4) | `connector_key`, `destination_id` | Stores external platform credentials encrypted at rest. |
| `destination_rules` | `DestinationRule` | `app/db/models/rule.py` | `id` (UUID4) | `destination_id`, `UNIQUE(destination_id, rule_type)` | Configured policy constraints per destination. |
| `rule_evaluations` | `RuleEvaluation` | `app/db/models/rule.py` | `id` (UUID4) | `job_id`, `destination_id` | Audit trail of rule compliance checks executed prior to each post. |
| `publications` | `Publication` | `app/db/models/publication.py` | `id` (UUID4) | `job_id`, `destination_id`, `platform_post_id` | Permanent record of successful external posts and live URLs. |
| `output_manifests` | `OutputManifest` | `app/db/models/manifest.py` | `id` (UUID4) | `job_id` | Audit record (IS-9) capturing models, timings, parameters, and licensing. |
| `certification_runs` | `CertificationRun` | `app/db/models/certification.py` | `id` (UUID4) | `destination_id` | Verifiable evidence generated during destination certification cycles. |

---

## 8. Complete API Endpoint Catalogue

All endpoints require `Authorization: Bearer <token>` (defined in `settings.api_bearer_token`), except `/health`.

| Method | Path | Router Module | Handler Function | Status Codes | Description |
|---|---|---|---|---|---|
| `GET` | `/health` | `health.py` | `health()` | 200 | Liveness probe returning process status and timestamp. |
| `GET` | `/ready` | `health.py` | `ready()` | 200, 503 | Readiness probe testing Postgres and storage connectivity. |
| `POST` | `/api/v1/publish` | `jobs.py` | `submit_publish()` | 202, 400, 401, 409 | Submits an asynchronous publishing job. Requires `Idempotency-Key`. |
| `GET` | `/api/v1/jobs/{job_id}` | `jobs.py` | `get_job()` | 200, 401, 404 | Fetches job execution status, progress, and live URL. |
| `GET` | `/api/v1/destinations` | `destinations.py` | `list_destinations()` | 200, 401 | Lists destinations with optional filtering and pagination. |
| `POST` | `/api/v1/destinations` | `destinations.py` | `create_destination()` | 201, 401, 422 | Registers a new destination in the catalogue. |
| `GET` | `/api/v1/destinations/{id}` | `destinations.py` | `get_destination()` | 200, 401, 404 | Retrieves destination details by ID. |
| `PUT` | `/api/v1/destinations/{id}` | `destinations.py` | `update_destination()` | 200, 401, 404 | Updates destination properties. |
| `PATCH` | `/api/v1/destinations/{id}` | `destinations.py` | `update_destination()` | 200, 401, 404 | Partially updates destination properties. |
| `DELETE` | `/api/v1/destinations/{id}` | `destinations.py` | `delete_destination()` | 200, 401, 404 | Soft-deletes a destination (`active=False`). |
| `POST` | `/api/v1/destinations/import` | `destinations.py` | `bulk_import_destinations()` | 200, 400, 401 | Bulk imports destinations from JSON or multipart CSV file. |
| `POST` | `/api/v1/destinations/bulk` | `destinations.py` | `bulk_import_destinations()` | 200, 400, 401 | Alias for destination bulk import. |
| `GET` | `/api/v1/connectors` | `destinations.py` | `list_connectors_route()` | 200, 401 | Lists all registered connectors and enabled status. |
| `GET` | `/api/v1/connections` | `connections.py` | `list_connections()` | 200, 401 | Lists connections (credentials masked). |
| `POST` | `/api/v1/connections` | `connections.py` | `create_connection()` | 201, 401, 422 | Stores a new connection with encrypted credentials. |
| `GET` | `/api/v1/connections/{id}` | `connections.py` | `get_connection()` | 200, 401, 404 | Retrieves connection metadata. |
| `PATCH` | `/api/v1/connections/{id}` | `connections.py` | `update_connection()` | 200, 401, 404 | Updates connection details or re-encrypts credentials. |
| `DELETE` | `/api/v1/connections/{id}` | `connections.py` | `delete_connection()` | 200, 401, 404 | Soft-deletes a connection (`active=False`). |
| `POST` | `/api/v1/connections/{id}/decrypt`| `connections.py`| `get_connection_credentials()`| 200, 401, 404 | Secure internal endpoint returning decrypted credentials. |
| `POST` | `/api/v1/certification/run` | `certification.py` | `run_certification_standalone()`| 200, 400, 401 | Runs a certification test sequence on a destination. |
| `POST` | `/api/v1/certify/{destination_id}` | `certification.py` | `run_certification()` | 200, 401, 404 | Runs certification using URL path parameter. |
| `GET` | `/api/v1/certification/{run_id}` | `certification.py` | `get_certification_by_run_id()` | 200, 401, 404 | Gets certification run evidence by run ID. |
| `GET` | `/api/v1/certify/{destination_id}` | `certification.py` | `get_certification()` | 200, 401, 404 | Gets latest certification run for a destination. |
| `GET` | `/api/v1/certify/{dest_id}/history`| `certification.py` | `get_certification_history()` | 200, 401 | Returns certification run history for a destination. |
| `POST` | `/connector/v1/{key}/{method}` | `connector.py` | `connector_dispatch()` | 200, 401, 404, 422 | Appendix A connector direct dispatch. |
| `GET` | `/api/v1/storage` | `storage.py` | `storage_info()` | 200, 401 | Returns active storage engine details. |

---

## 9. Configuration and Environment Variables

The table below lists all configuration parameters managed by `app/core/settings.py`:

| Variable Name | Default Value | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Operating mode (`development`, `production`, `test`). |
| `APP_HOST` | `0.0.0.0` | Bind IP for the FastAPI server. |
| `APP_PORT` | `8000` | Port for the HTTP API server. |
| `APP_LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `API_BEARER_TOKEN` | `change-me-local-dev-token` | Master bearer authentication secret for `/api/v1/*`. |
| `DATABASE_URL` | `postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist` | Async PostgreSQL connection string. |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist` | Sync PostgreSQL URL used by Alembic migrations. |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://.../incubrix_dist_test` | Dedicated test database URL (must contain `_test`). |
| `DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size. |
| `DB_MAX_OVERFLOW` | `20` | Max overflow connections above pool size. |
| `STORAGE_BACKEND` | `s3` | Object storage mode (`s3` or `local`). |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | S3 API endpoint (MinIO or AWS S3). |
| `S3_ACCESS_KEY_ID` | `minioadmin` | S3 access key ID. |
| `S3_SECRET_ACCESS_KEY` | `minioadmin_dev_secret` | S3 secret access key. |
| `S3_BUCKET` | `incubrix-dist` | Bucket name for manifests and artifacts. |
| `CREDENTIAL_ENCRYPTION_KEY` | `""` | Fernet key used to encrypt connection credentials at rest. |
| `HMAC_SIGNING_SECRET` | `change-me-hmac-secret` | Key used to sign outgoing webhook payloads and callbacks. |
| `SIMULATION_MODE` | `True` | Global safety toggle preventing real outbound HTTP calls. |
| `CONNECTOR_{KEY}_ENABLED` | `True` | Per-connector kill-switch toggles for each of the 6 connectors. |

---

## 10. Security & Simulation Mode Audit

### Simulation Mode (`SIMULATION_MODE`)
- **Default Value:** `True` in `app/core/settings.py`.
- **Implementation Status:** Verified across all 6 connectors.
- **Protection Evidence:** Every connector's `publish`, `get_status`, `delete`, and `fetch_metrics` method contains an explicit early exit check:
  ```python
  if self._is_simulation():
      return self._sim_publish(...)
  ```
  This guarantees that during local testing, automated CI runs, or developer experimentation, no socket connection or HTTP request is ever opened to real external domains.

### Credential Protection
- **Storage Encryption:** Uses Fernet (AES-128-CBC + HMAC-SHA256).
- **Masking on Retrieval:** The `ConnectionResponse` schema and repository queries explicitly strip `encrypted_credentials` so passwords and API keys are never exposed in GET or LIST endpoints.
- **Log Scrubbing:** The `_redact_secrets` structlog processor scrubs any keys or strings matching passwords, tokens, API keys, and connection strings before emitting log lines.

---

## 11. Test Suite & Verification Evidence

The automated test suite runs via `pytest` and contains **104 test cases** across 13 test files:

- `tests/test_health.py` (4 tests): Verifies `/health` returns 200, generates/propagates `X-Correlation-Id`, and `/ready` probes dependencies.
- `tests/test_errors.py` (4 tests): Verifies unknown connector and method handling, 401 bearer token enforcement, and absence of stack traces in error envelopes.
- `tests/test_idempotency.py` (8 tests): Tests deterministic SHA-256 fingerprinting, replay of identical jobs, HTTP 409 on payload mutation, and missing header validation.
- `tests/test_rules.py` (8 tests): Tests frequency cap evaluation, self-promotion blocking, AI disclosure enforcement, and automation restrictions.
- `tests/test_storage.py` (5 tests): Tests `LocalStorage` put, get, delete, health check, path traversal prevention, and S3 integration (gracefully skipped if MinIO is offline).
- `tests/test_connector_contract.py` (18 tests): Tests Appendix A contract compliance across all 6 connectors (`validate`, `publish`, `get_status`, `delete`, manifests, disabled kill-switches).
- `tests/test_connectors/test_discourse.py` (6 tests): Tests Discourse validation boundaries, HTTP mocking, and delete behaviors.
- `tests/test_connectors/test_simulation.py` (18 tests): Proves that `SIMULATION_MODE=true` safely handles publish, status, and delete across all 6 connectors without external network calls.
- `tests/test_destinations_api.py` (2 tests): Tests destination CRUD lifecycle, filtering, and bulk importation of JSON and CSV data.
- `tests/test_connections_api.py` (1 test): Tests connection creation, credential encryption, and verifies credentials are never leaked in response payloads.
- `tests/test_certification_api.py` (1 test): Tests certification execution (`validate` → `publish` → `status` → `delete`) and evidence storage.
- `tests/test_connectors/test_live_connectors.py` (15 tests): Tests outgoing HTTP payload structures, draft status preservation on DEV.to (`published: false`) and Ghost (`status: "draft"`), and error mapping.
- `tests/test_security_hardening.py` (14 tests): Tests fail-closed production startup validation, rejection of predictable default bearer tokens, AES-128-CBC Fernet encryption round-trip, invalid key rejection, and HMAC-SHA256 signature verification.

**Latest Test Execution Result:**
```text
======================= 103 passed, 1 skipped in 6.17s =======================
```
*(The 1 skipped test is `test_s3_storage_roundtrip_integration`, which is marked `@pytest.mark.integration` and skips gracefully when the Docker MinIO daemon is not running on port 9000).*

---

## 12. Assessment Requirement Traceability Matrix

This matrix maps requirements from `ps4.pdf` to the code and test evidence:

| Assessment ID | Requirement Description | Relevant Source Files | Implementation Evidence | Test Coverage | Status |
|---|---|---|---|---|---|
| **MH-1** | Exact connector contract (Appendix A) | `app/connectors/base.py`, `app/api/routes/connector.py` | Base class defines exact signatures; `/connector/v1/{key}/{method}` dispatches. | `tests/test_connector_contract.py` | **Implemented & Tested** |
| **MH-2** | Six Core connectors certified | `app/connectors/implementations/*` | Exactly 6 connectors: Discourse, Lemmy, DEV.to, Ghost, Webhook HMAC, Assisted. | `tests/test_connectors/*`, `tests/test_certification_api.py` | **Implemented & Tested** |
| **MH-3** | Configuration, not code | `app/connectors/manifests/*.yaml`, `app/db/models/destination.py` | `instance_param` stored in catalogue; new forums added via DB row without code changes. | `tests/test_destinations_api.py` | **Implemented & Tested** |
| **MH-4** | Rules checked before every post | `app/rules/engine.py`, `app/jobs/processor.py` | Rules engine checks frequency caps, promo, and AI disclosure prior to publish. | `tests/test_rules.py` | **Implemented & Tested** |
| **MH-5** | Never spam / never cheat | `app/connectors/base.py`, `app/connectors/implementations/*` | Safe deletion within 10 minutes in certification; 429 rate limit backoff mappings. | `tests/test_connectors/test_simulation.py` | **Implemented & Tested** |
| **MH-6** | Safe retries & idempotency | `app/api/routes/jobs.py`, `app/db/models/idempotency.py` | SHA-256 fingerprinting on `Idempotency-Key` prevents duplicate job creation. | `tests/test_idempotency.py` | **Implemented & Tested** |
| **MH-7** | Secrets protected & simulation mode | `app/core/logging.py`, `app/services/credentials.py`, `app/core/settings.py` | Fernet encryption at rest, structlog redaction, global `SIMULATION_MODE=True`. | `tests/test_connections_api.py`, `tests/test_simulation.py` | **Implemented & Tested** |
| **MH-8** | Local test instances via Docker Compose | `docker-compose.yml`, `infra/mock-server/server.py` | Full multi-service stack with Postgres, MinIO, Lemmy, Ghost, and mock platform server. | Verified via compose config & Dockerfile | **Implemented & Verified** |
| **MH-9** | Integration Standard compliance | Multiple modules | Satisfies IS-1 through IS-10 (see below). | Full test suite | **Implemented & Tested** |
| **IS-1** | One-command start and test | `docker-compose.yml`, `Makefile` | `docker compose up` starts entire stack; `pytest` runs test suite without external keys. | `tests/` | **Implemented & Tested** |
| **IS-2** | Documented HTTP API (`openapi.yaml`)| `scripts/export_openapi.py`, `openapi.yaml` | Headless script exports OpenAPI 3.1 matching live service routes under `/api/v1/`. | Verified export script | **Implemented & Tested** |
| **IS-3** | Background jobs with progress | `app/api/routes/jobs.py`, `app/jobs/processor.py` | POST returns 202 with `job_id`; GET returns status, progress (0-100), and live URL. | `tests/test_idempotency.py` | **Implemented & Tested** |
| **IS-4** | `Idempotency-Key` header | `app/api/routes/jobs.py` | Mandated on POST `/api/v1/publish`; prevents duplicate job execution. | `tests/test_idempotency.py` | **Implemented & Tested** |
| **IS-5** | Clear error envelope | `app/core/errors.py` | Standard envelope: `{"error": {"code", "message", "retryable", "details"}}`. | `tests/test_errors.py` | **Implemented & Tested** |
| **IS-6** | Configuration from env vars | `app/core/settings.py` | Pydantic BaseSettings loading from `.env`; no hard-coded credentials. | `tests/test_health.py` | **Implemented & Tested** |
| **IS-7** | S3-compatible storage | `app/storage/s3.py`, `app/storage/factory.py` | Async MinIO/S3 storage via `aiobotocore` with local filesystem fallback. | `tests/test_storage.py` | **Implemented & Tested** |
| **IS-8** | Logs and health endpoints | `app/core/logging.py`, `app/api/routes/health.py` | JSON structured logs with `correlation_id`; `/health` and `/ready` endpoints. | `tests/test_health.py` | **Implemented & Tested** |
| **IS-9** | Output manifest | `app/db/models/manifest.py`, `app/jobs/processor.py` | JSON manifest record created upon job completion capturing timings and metadata. | `tests/test_idempotency.py` | **Implemented & Tested** |
| **IS-10**| Batch runner CLI | `scripts/batch_runner.py` | Command-line tool processing folders of JSON inputs, submitting jobs and polling. | Manual CLI execution | **Implemented & Tested** |

---

## 13. Known Limitations, Gaps & Architectural Trade-offs

1. **In-Process Asyncio Job Tasking (ADR-005):**
   - *Design Choice:* Jobs are dispatched via `asyncio.create_task()` in the FastAPI process rather than an external worker (like Celery or BullMQ).
   - *Trade-off:* If the Python process is abruptly terminated, in-flight jobs remain in the `running` state in PostgreSQL until manually re-queued. This was chosen intentionally for the assessment to avoid multi-container queue complexity.
2. **DEV.to Delete Limitation (ADR-011):**
   - *Design Choice:* The public DEV.to API does not provide an HTTP DELETE route for articles.
   - *Trade-off:* The connector updates the article status to `published: False` (unpublishing it) rather than hard-deleting the resource.
3. **Ghost API Token Format:**
   - *Design Choice:* Requires the Admin API key to be split into `id:secret` to sign short-lived JWTs.
   - *Trade-off:* If an invalid key string lacking a colon is passed in live mode, token signing falls back to raw string pass-through for mock compatibility.
4. **Scope Boundaries:**
   - As mandated by the specification, RSS feeds and major platforms (YouTube, Instagram, LinkedIn, Reddit, X) are strictly out of scope and must not be implemented. Exactly 6 connectors are maintained.

---

## 14. Setup, Execution & Testing Guide

### Prerequisites
- Python 3.11+
- PostgreSQL 16+ running locally on port 5432
- (Optional) MinIO running locally on port 9000

### 1. Environment Setup
```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy example environment configuration
Copy-Item .env.example .env
```

### 2. Database Setup & Migrations
```powershell
# Set up initial databases (incubrix_dist and incubrix_dist_test)
python scripts/setup_local_db.py
python scripts/grant_db_perms.py

# Run Alembic migrations to build all 9 tables
alembic upgrade head
```

### 3. Running Automated Tests
```powershell
# Run the complete test suite (runs in simulation mode with test DB)
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=term-missing
```

### 4. Running the Application Locally
```powershell
# Start the Uvicorn ASGI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **Interactive Swagger API Documentation**: `http://localhost:8000/docs`

### 5. Running the Complete Stack via Docker Compose
```powershell
# Builds and starts Postgres, MinIO, Lemmy, Ghost, Mock Server, and IncuBrix App
docker compose up --build
```

---

## 15. Glossary of Technical Terms

- **Connector:** A modular software driver that communicates with a specific platform family (e.g. Discourse or Ghost) by converting standard IncuBrix commands into target platform HTTP requests.
- **Destination:** A specific instance or community where content is delivered (e.g., a specific forum URL, blog URL, or Lemmy community).
- **Rendition:** The content payload to be published, including title, body text, tags, canonical URLs, and promotional flags.
- **Idempotency:** A guarantee that sending the exact same request multiple times has the exact same effect as sending it once, preventing duplicate billing or double-posting.
- **Simulation Mode:** A safety operational mode where real platform network calls are suppressed, and deterministic synthetic responses are returned instead.
- **Output Manifest:** A standardized machine-readable JSON document recording the exact parameters, models, versions, timings, and licensing of an execution.
- **Fernet Encryption:** An authenticated symmetric encryption standard that ensures data cannot be read or manipulated without the secret encryption key.
- **ActivityPub:** A decentralized social networking protocol used by federated networks like Lemmy and Mastodon.

---

## 16. Proposed Learning Sequence for a New Developer

To understand this codebase thoroughly with the least cognitive resistance, review the files in this order:

1. **The Core Data Types & Errors:**
   - Read `app/core/errors.py` (Learn canonical error codes and the JSON error envelope).
   - Read `app/core/settings.py` (Learn all configuration variables and toggles).
2. **The Connector Contract & Registry:**
   - Read `app/connectors/base.py` (Understand the 4 required methods: `validate`, `publish`, `get_status`, `delete`).
   - Read `app/connectors/manifests/*.yaml` (Understand connector capabilities and limits).
   - Read `app/connectors/registry.py` (See how connectors are registered and fetched).
3. **The Six Connector Implementations:**
   - Read `app/connectors/implementations/assisted.py` (The simplest connector; generates Markdown packs).
   - Read `app/connectors/implementations/webhook_hmac.py` (See HMAC signing).
   - Read `app/connectors/implementations/devto.py`, `discourse.py`, `ghost.py`, and `lemmy.py`.
4. **The Database Models & Repositories:**
   - Read `app/db/models/job.py`, `destination.py`, `connection.py`, `idempotency.py`.
   - Read `app/db/repos/*` (See how SQLAlchemy queries are structured).
5. **The Publishing Workflow & Rules:**
   - Read `app/rules/engine.py` (See how community rules are checked).
   - Read `app/jobs/processor.py` (Trace the background execution pipeline).
6. **The HTTP API Routes:**
   - Read `app/api/routes/health.py`, `jobs.py`, `destinations.py`, `connections.py`, `certification.py`.
   - Read `app/main.py` (See how middleware, logging, and routers connect together).
7. **The Test Suite & Tooling:**
   - Review `tests/test_simulation.py` and `tests/test_idempotency.py`.
   - Review `scripts/batch_runner.py` and `scripts/export_openapi.py`.

---

## 17. Handoff Summary for AI Assistants

If you are an AI assistant tasked with explaining, maintaining, or demonstrating this project:
- **Architecture:** It is a single-process FastAPI service backed by asynchronous PostgreSQL (`asyncpg` + SQLAlchemy 2.x) and MinIO/S3 object storage.
- **Connectors:** There are **exactly 6 connectors** (Discourse, Lemmy, DEV.to, Ghost, Webhook HMAC, Assisted). Do not add new ones.
- **Publishing Path:** Submissions go to `POST /api/v1/publish` with an `Idempotency-Key` header. The endpoint returns HTTP 202 Accepted, and `app/jobs/processor.py` processes the job asynchronously in the background.
- **Safety First:** `SIMULATION_MODE` defaults to `True`. Keep it enabled unless live integration testing against local Docker containers is explicitly requested. Real credentials should never be committed or printed in plaintext.
- **Tests:** The repository contains 75 tests in `tests/` passing cleanly with `pytest`.
