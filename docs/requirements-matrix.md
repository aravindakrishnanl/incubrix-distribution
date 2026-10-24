# Requirements Matrix — IncuBrix Distribution Assessment 4

> Source of truth: `ps4.pdf` (9 pages). Status updated as implementation progresses.
>
> Statuses: `NOT_STARTED` | `IN_PROGRESS` | `VERIFIED` | `PARTIAL` | `NOT_IMPLEMENTED`

---

## Must-Have Requirements

| ID | Requirement | Classification | Planned Implementation | Status |
|----|-------------|---------------|----------------------|--------|
| MH-1 | Exact connector contract (Appendix A) | Must-have | `app/connectors/` base + six implementations | `VERIFIED` |
| MH-2 | Six Core connectors certified | Must-have | Discourse, Lemmy, Dev.to, Ghost, HMAC webhook, Assisted | `VERIFIED` |
| MH-3 | Configuration not code | Must-have | `instance_param` in manifest + config-driven destinations | `VERIFIED` |
| MH-4 | Rules before every post | Must-have | `app/rules/engine.py` | `VERIFIED` |
| MH-5 | Never spam / never cheat | Must-have | simulation_mode flag; mock server | `VERIFIED` |
| MH-6 | Safe retries / idempotency | Must-have | `idempotency_records` table + uniqueness constraint | `VERIFIED` |
| MH-7 | Secrets protected + simulation mode | Must-have | Redaction middleware; env-only creds | `VERIFIED` |
| MH-8 | Local test instances via docker compose up | Must-have | docker-compose.yml with Lemmy, Ghost, MinIO, mock server | `VERIFIED` |
| MH-9 | Integration Standard followed | Must-have | All 10 IS points (see below) | `VERIFIED` |

## Integration Standard (IS)

| IS# | Requirement | Status |
|-----|-------------|--------|
| IS-1 | One-command start and test | `VERIFIED` |
| IS-2 | Documented HTTP API (openapi.yaml) | `VERIFIED` |
| IS-3 | Background jobs (POST→202, GET status) | `VERIFIED` |
| IS-4 | Idempotency-Key header | `VERIFIED` |
| IS-5 | Clear errors (JSON envelope) | `VERIFIED` |
| IS-6 | All configuration from env vars | `VERIFIED` |
| IS-7 | S3-compatible storage | `VERIFIED` |
| IS-8 | Structured JSON logs + /health + /ready | `VERIFIED` |
| IS-9 | Output manifest | `VERIFIED` |
| IS-10 | Batch runner CLI | `VERIFIED` |

## Level Requirements

### Core (required)
- All must-haves: `VERIFIED`
- Full certification run per connector: `VERIFIED`
- Error mapping to canonical codes: `VERIFIED`

### Advanced / Extended Capabilities
- Catalogue import CSV and JSON: `VERIFIED` (`POST /api/v1/destinations/import`)
- Connection management with encrypted credentials: `VERIFIED` (`/api/v1/connections`)
- Certification harness & evidence tracking: `VERIFIED` (`/api/v1/certification/run`)
- Metrics (`fetch_metrics` on Discourse, Lemmy, Dev.to): `VERIFIED`
- Additional connectors (Hashnode, Slack, etc.): `NOT_IMPLEMENTED` (explicit scope: exactly 6 connectors)


## Scope Decisions

| Decision | Rationale |
|----------|-----------|
| Exactly 6 connectors | Brief MH-2 names these 6 as Core; AL-5 adds more at Advanced level |
| No RSS, no major platforms | Explicitly out of scope in brief |
| PostgreSQL only | Prompt 1 mandate |
| Single FastAPI app | Prompt 1 mandate |
