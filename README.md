# IncuBrix Distribution

**Long-Tail Destination Network & Unified Publishing Layer**

IncuBrix Distribution is a backend service designed to manage, validate, and publish content across niche, long-tail destinations. While major platforms provide centralized APIs, high-intent audience engagement often takes place across distributed community forums, developer publication feeds, federated platforms, and creator blogs.

This service standardizes cross-platform publishing through **exactly six connectors**, enforces community rules before any request leaves the system, guarantees idempotency under Integration Standard IS-3, encrypts credentials at rest, and defaults to a safe simulation mode to prevent unintended live posts.

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │    FastAPI Application (/api/v1)       │
                      └──────────────────┬─────────────────────┘
                                         │
                 ┌───────────────────────┼────────────────────────┐
                 ▼                       ▼                        ▼
      ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
      │ Destination Store  │   │ Connection Manager │   │ Background Engine  │
      │ (Catalogue & Spec) │   │ (Fernet Encrypted) │   │ (IS-3 Idempotency) │
      └────────────────────┘   └────────────────────┘   └─────────┬──────────┘
                                                                  │
                                       ┌──────────────────────────┴───────────┐
                                       ▼                                      ▼
                            ┌─────────────────────┐               ┌─────────────────────┐
                            │ Rules Engine        │               │ Simulation Guard    │
                            │ (Caps, Policy, AI)  │               │ (SIMULATION_MODE)   │
                            └──────────┬──────────┘               └──────────┬──────────┘
                                       │                                     │
                                       └──────────────────┬──────────────────┘
                                                          ▼
                                            ┌───────────────────────────┐
                                            │ Exactly 6 Core Connectors │
                                            └─────────────┬─────────────┘
                                                          │
          ┌─────────────────┬─────────────────┬───────────┴─────┬─────────────────┬─────────────────┐
          ▼                 ▼                 ▼                 ▼                 ▼                 ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │  Discourse  │   │    Lemmy    │   │   DEV.to    │   │    Ghost    │   │ Webhook HMAC│   │  Assisted   │
   │  (Native)   │   │ (Protocol)  │   │  (Native)   │   │  (Native)   │   │  (Bridge)   │   │ (Pack Gen)  │
   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
```

### Core Components
1. **Connector Layer ("One connector, many destinations"):** A single connector implementation communicates with an entire platform family. New forums, blogs, or webhook partners require only catalog configuration, not new code.
2. **Community Rules Engine (`app/rules/engine.py`):** Automatically enforces frequency caps, self-promotion prohibitions, link density policies, and AI disclosure requirements before dispatching to connectors.
3. **Asynchronous Job Processor (`app/jobs/processor.py`):** Follows Integration Standard IS-3. Ingestion yields an immediate HTTP 202 with a tracking `job_id`. Background tasks transition state (`QUEUED` → `RUNNING` → `SUCCEEDED` / `FAILED`) and persist execution manifests.
4. **Idempotency Engine (`app/api/routes/jobs.py`):** Requires a client-supplied `Idempotency-Key`. Replays identical payloads safely and rejects altered payloads with HTTP 409 Conflict.
5. **Credential Security at Rest (`app/services/credentials.py`):** Encrypts credentials using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256). Plaintext or Base64-as-encryption storage is rejected.
6. **Simulation Guard (`SIMULATION_MODE=true`):** Prevents accidental live publishing by returning deterministic synthetic outputs (`_simulated: true`) across all connectors.

---

## The Exactly Six Supported Connectors

| Connector Key | Platform & Tier | Authentication Mechanism | Target API / Functionality |
| :--- | :--- | :--- | :--- |
| **`discourse`** | Discourse Forums<br>`native` | `Api-Key` + `Api-Username` HTTP headers | Topic and reply creation via `/posts.json`. Respects categories and character limits. |
| **`lemmy`** | Lemmy ActivityPub<br>`protocol` | Short-lived JWT obtained via username/password | Federated forum posts via Lemmy HTTP API v3 (`/api/v3/post`) to target communities. |
| **`devto`** | DEV.to Articles<br>`native` | `api-key` HTTP header | Markdown publishing via `https://dev.to/api/articles`. Preserves explicit `published: false` draft flags. |
| **`ghost`** | Ghost Creator Blogs<br>`native` | Short-lived HS256 JWT generated from Admin API Key | Publication via Ghost Admin API (`/ghost/api/admin/posts/`). Preserves explicit `status: "draft"`. |
| **`webhook_hmac`** | Generic Partner Endpoints<br>`bridge` | HMAC-SHA256 signature in `X-IncuBrix-Signature` | Sends authenticated JSON payloads with SHA-256 signatures to arbitrary partner URLs. |
| **`assisted`** | Assisted Publishing<br>`assisted` | None (human-in-the-loop) | Generates structured human-posting packages (`files`, `caption`, `deep_link`, `checklist`). Non-network. |

---

## Technology Stack & Prerequisites

* **Runtime:** Python 3.11+ (Python 3.15 supported; pure-Python SQLAlchemy fallback active for Windows compatibility)
* **Framework:** FastAPI, Starlette, Pydantic v2, `pydantic-settings`
* **Database:** PostgreSQL 16 (via `asyncpg` for runtime queries, `psycopg2` for Alembic migrations)
* **Migrations:** Alembic
* **HTTP Client:** HTTPX (async client with timeout and retry configuration)
* **Logging:** Structlog (structured JSON format with automatic secret redaction)
* **Cryptography:** Cryptography (`Fernet` AES-128-CBC + HMAC-SHA256)
* **Testing:** Pytest, pytest-asyncio, AnyIO

---

## Setup & Installation (Windows)

All commands should be executed from the repository root: `C:\Users\aravi\python\incubrix-distribution`.

### 1. Virtual Environment
The repository contains a pre-configured virtual environment in `.\venv`:
```powershell
# Activate the existing virtual environment in PowerShell:
.\venv\Scripts\Activate.ps1

# Or run commands directly using the interpreter:
.\venv\Scripts\python.exe -m pip --version
```

If dependencies ever need to be restored:
```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Generate a secure 32 url-safe base64-encoded Fernet key:
```powershell
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Edit `.env` and set:
```dotenv
# General Application
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
APP_LOG_LEVEL=INFO

# API Authentication (Choose a private bearer token, min 16 chars)
API_BEARER_TOKEN=your-private-api-bearer-token-16-chars

# Database Configuration
DATABASE_URL=postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist
DATABASE_URL_SYNC=postgresql+psycopg2://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist
TEST_DATABASE_URL=postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist_test

# Security Keys (Paste the Fernet key generated above)
CREDENTIAL_ENCRYPTION_KEY=<PASTE_GENERATED_FERNET_KEY_HERE>
HMAC_SIGNING_SECRET=your-private-hmac-secret-16-chars

# Safety Switch (Keep true for simulated evaluations)
SIMULATION_MODE=true
```

> [!IMPORTANT]
> Never commit `.env` to Git. Default tokens like `change-me-local-dev-token` or `change-me-hmac-secret` are rejected automatically by application security validation.

### 3. Database Migrations
Verify PostgreSQL is running, then run migrations to the latest revision:
```powershell
.\venv\Scripts\python.exe -m alembic upgrade head
```

Verify current migration head:
```powershell
.\venv\Scripts\python.exe -m alembic current
# Expected output: c66fc5ebae72 (head)
```

---

## Running the API & Documentation

Start the development server bound strictly to the loopback interface:
```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

* **Interactive Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **ReDoc Documentation:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
* **OpenAPI Specification JSON:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)
* **Liveness Probe:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
* **Readiness Probe:** [http://127.0.0.1:8000/ready](http://127.0.0.1:8000/ready)

---

## Publishing Workflow API Guide

Publishing follows the asynchronous Integration Standard IS-3 protocol.

### Step 1: Submit a Publish Request (`POST /api/v1/publish`)
Submit a publish job with a mandatory `Idempotency-Key` and `Authorization` header:

```powershell
$headers = @{
    "Authorization"   = "Bearer your-private-api-bearer-token-16-chars"
    "Idempotency-Key" = [System.Guid]::NewGuid().ToString()
    "Content-Type"    = "application/json"
}

$body = @{
    connector_key = "devto"
    rendition     = @{
        title     = "Getting Started with IncuBrix"
        body      = "This is the body of the article in markdown."
        tags      = @("python", "api", "tutorial")
        published = $false   # Explicitly request draft status
    }
} | ConvertTo-Json -Depth 5

$response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/publish" -Method Post -Headers $headers -Body $body
$response
```

**Immediate Response (`HTTP 202 Accepted`):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "connector_key": "devto",
  "state": "queued",
  "progress": 0,
  "created_at": "2026-10-24T18:00:00Z"
}
```

### Step 2: Poll Job Status (`GET /api/v1/jobs/{job_id}`)
Poll the job endpoint until the state reaches `succeeded` or `failed`:

```powershell
$jobId = $response.job_id
$jobStatus = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/jobs/$jobId" -Headers $headers
$jobStatus
```

**Completed Response (`HTTP 200 OK`):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "connector_key": "devto",
  "state": "succeeded",
  "progress": 100,
  "platform_post_id": "sim-devto-a1b2c3d4",
  "live_url": "https://sim.example.com/sim-devto-a1b2c3d4",
  "error_code": null,
  "error_message": null
}
```

---

## Running the Automated Test Suite

Run the full pytest suite:
```powershell
.\venv\Scripts\python.exe -m pytest
```

### Verified Test Results
```text
======================= 103 passed, 1 skipped in 6.17s =======================
```
* **Passed (103):** Covers API contracts, connector implementations, live payload formats, idempotency guarantees, rules engine evaluation, error envelopes, and Phase 2 security hardening.
* **Skipped (1):** `tests/test_storage.py:80` (`test_s3_storage_roundtrip_integration`), which requires a live MinIO container. Local filesystem storage tests pass completely.

---

## Known Limitations & Production Considerations

1. **In-Memory Background Task Durability:** Publishing jobs are dispatched using in-process `asyncio.create_task`. In the event of an ungraceful process crash or worker reboot, any job in `QUEUED` or `RUNNING` status is not automatically re-queued upon startup. A persistent distributed queue (e.g. Celery / ARQ with Redis) should be introduced for multi-worker production deployments.
2. **Transient Network Retries:** While `http_max_retries: 3` is configured in application settings, the background processor currently fails jobs immediately upon the first unhandled connector exception. Automatic exponential backoff retries for transient HTTP errors (`PlatformUnavailableError`, `503`) are planned for a subsequent release.
3. **Mocked Tests vs. Live Outbound Publishing:** Automated tests use mocks and simulation mode to verify request structures and draft flag preservation. Live credentials configured in `.env` are verified via read-only connectivity endpoints (`check_connectivity`) and have not made real public posts to external networks during this evaluation.
