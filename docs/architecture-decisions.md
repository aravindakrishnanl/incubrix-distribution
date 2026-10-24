# Architecture Decision Log — IncuBrix Distribution

---

## ADR-001: Single FastAPI application (not microservices)

**Status:** Accepted
**Decision:** Run both the product API (`/api/v1/`) and connector contract routes (`/connector/v1/`) in a single FastAPI application.
**Rationale:** Assessment Prompt 1 explicitly mandates this. Simpler deployment, easier debugging, no network hops between services.
**Trade-offs:** All connectors run in the same process. Acceptable for assessment scale; a production version might extract connectors to separate processes.

---

## ADR-002: PostgreSQL only (no SQLite)

**Status:** Accepted
**Decision:** PostgreSQL is the sole database. No SQLite fallback, no dual-engine.
**Rationale:** Prompt 1 mandate. PostgreSQL provides the ACID guarantees needed for idempotency constraints and job state.
**Consequence:** Tests require a PostgreSQL instance. We use a separate `_test` database enforced by a settings validator.

---

## ADR-003: asyncpg + SQLAlchemy 2.x async ORM

**Status:** Accepted
**Decision:** Use `asyncpg` as the PostgreSQL driver and SQLAlchemy 2.x async ORM with `async_sessionmaker`.
**Rationale:** FastAPI is fully async; using an async ORM eliminates thread-pool overhead.

---

## ADR-004: Idempotency implementation

**Status:** Accepted
**Decision:** Fingerprint = SHA-256(idempotency_key + canonical_json(request_body)). Stored in `idempotency_records` table with a `UNIQUE(idempotency_key)` constraint. The database constraint is the last line of defence against race conditions.
**Rationale:** Database-level uniqueness prevents duplicate jobs even under concurrent requests. Process-level check avoids unnecessary DB writes.
**Limits of exactly-once:** If the application crashes after creating the job record but before committing the idempotency record, the next retry will create a new job. This window is minimised by committing the idempotency record before dispatching the async task.

---

## ADR-005: In-process asyncio job queue

**Status:** Accepted (assessment scope)
**Decision:** Use `asyncio.create_task()` for job processing instead of a separate queue (Celery, RQ, etc.).
**Rationale:** Simpler infrastructure for assessment; job state is still persisted in PostgreSQL so `GET /jobs/{id}` is always accurate. In-flight tasks are lost on restart, but the assessment does not require a durable queue.
**Production note:** For production, replace with a proper queue (e.g., Celery + Redis, or Postgres-backed BullMQ equivalent).

---

## ADR-006: Credential storage (encrypted at rest)

**Status:** Accepted
**Decision:** External API credentials are encrypted using Fernet (AES-128-CBC + HMAC-SHA256) before storing in the `connections.encrypted_credentials` column. The key is injected via `CREDENTIAL_ENCRYPTION_KEY` env var.
**Rationale:** Assessment requires secrets never appear in plaintext in the DB or logs.
**Key rotation:** Re-encrypt all rows with new key, then update env var. Document the rotation procedure.
**If CREDENTIAL_ENCRYPTION_KEY is empty:** credentials are base64-encoded only (for test/dev use; never production).

---

## ADR-007: Connector contract interpretation (Appendix A)

**Status:** Accepted
**Decision:** The HTTP body for each connector method is a flat JSON object with the method's parameters as top-level fields. For example, `validate` receives `{rendition, destination, connection}`.
**Rationale:** Appendix A specifies the method signatures but not the exact JSON wire format. This flat-object approach is the most natural REST mapping.
**Evidence:** `app/api/routes/connector.py` and `tests/test_connector_contract.py`.

---

## ADR-008: MinIO for S3-compatible storage

**Status:** Accepted
**Decision:** Use MinIO in `docker-compose.yml` for S3-compatible object storage. The `S3Storage` implementation uses `aiobotocore` which is compatible with both MinIO and AWS S3.
**Rationale:** Assessment allows MinIO in Docker Compose. Using the S3-compatible API means the same code works in production with AWS S3.

---

## ADR-009: Mock server for Discourse, Dev.to, webhook

**Status:** Accepted
**Decision:** Provide `infra/mock-server/` — a small FastAPI app that simulates Discourse posts, Dev.to articles, and webhook endpoints.
**Rationale:** Tests must not contact real platforms. The mock is deterministic and stateful within a session.

---

## ADR-010: Ghost JWT authentication

**Status:** Accepted
**Decision:** Ghost Admin API requires short-lived JWTs. We construct the JWT from the `admin_api_key` (format: `key_id:hex_secret`) using HMAC-SHA256, valid for 5 minutes.
**Rationale:** This is the documented Ghost Admin API authentication scheme. The JWT is constructed at request time so it is always fresh.

---

## ADR-011: Dev.to delete workaround

**Status:** Accepted (documented)
**Decision:** Dev.to's public API does not support `DELETE`. We implement `delete()` as unpublishing (setting `published: false`).
**Rationale:** This is the best available option without a separate admin token. The deletion certification evidence should note this limitation.
