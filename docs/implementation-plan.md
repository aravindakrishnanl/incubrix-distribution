# Implementation Plan — IncuBrix Distribution

## Prompt 1 Scope (Foundation)

### Completed in Prompt 1
1. ✅ Project structure and all package directories
2. ✅ PostgreSQL models (all 8 models: Destination, Connection, PublishJob, IdempotencyRecord, Publication, CertificationRun, DestinationRule, RuleEvaluation, OutputManifest)
3. ✅ Alembic migration environment
4. ✅ Async SQLAlchemy engine and session factory
5. ✅ Six connector implementations (Discourse, Lemmy, Dev.to, Ghost, HMAC webhook, Assisted)
6. ✅ Six connector YAML manifests with all Appendix A fields
7. ✅ Connector base class and registry
8. ✅ Connector HTTP routes (`POST /connector/v1/{key}/{method}`)
9. ✅ Canonical error codes and error envelope
10. ✅ Idempotency system (fingerprint + DB uniqueness constraint)
11. ✅ Publish job submission and status (`POST /api/v1/publish`, `GET /api/v1/jobs/{id}`)
12. ✅ Storage abstraction (S3 + local fallback)
13. ✅ MinIO in docker-compose.yml
14. ✅ Rules engine (frequency cap, self-promo, AI disclosure, automation)
15. ✅ Structured JSON logging + correlation ID middleware
16. ✅ `/health` and `/ready` endpoints
17. ✅ Test suite (health, errors, contract, idempotency, storage, rules, discourse unit tests)
18. ✅ `.env.example`, `.gitignore`, `docker-compose.yml`, `Dockerfile`
19. ✅ Mock server for local platform simulation
20. ✅ Batch runner CLI (`scripts/batch_runner.py`)

### Gaps remaining for Prompt 2
- Alembic initial migration (autogenerate and apply)
- Full certification harness and run
- Destinations endpoint with real DB records
- Output manifest (IS-9)
- Lemmy and Ghost local test setup verification
- Rate limiting middleware (slowapi)
- OpenAPI YAML export and consistency test
- Advanced: catalogue import, rules capture, relevance scoring, tailoring
- End-to-end tests using docker compose

## Prompt 2 Scope (Completeness)

### Priority order
1. Alembic migration autogenerate and verify
2. Certification harness (publish → confirm live URL → status → delete → store evidence)
3. Rate limiting
4. Output manifest builder
5. OpenAPI export and consistency test
6. REPORT.md, SOURCES.md, AI_USE.md
7. Advanced features (catalogue import, etc.) if time allows

## Commands Reference

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Apply migrations (PostgreSQL must be running)
alembic upgrade head

# Run tests (excluding integration tests requiring live services)
pytest -m 'not integration' -v

# Run all tests including integration
pytest -v

# Run tests with coverage
pytest --cov=app --cov-report=term-missing -m 'not integration'

# Export OpenAPI spec
python scripts/export_openapi.py

# Start full stack (Docker required)
docker compose up --wait

# Run batch runner
python scripts/batch_runner.py --input tests/batch_inputs/ --output results/ --base-url http://localhost:8000 --token YOUR_TOKEN
```
