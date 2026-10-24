# Integration Standard Evidence — IncuBrix Distribution

Each point is worth 2 marks (20 total). Links are filled in as implementation is verified.

| IS# | Requirement | Status | Evidence |
|-----|-------------|--------|---------|
| IS-1 | One-command start and test | IN_PROGRESS | `docker compose up` + `pytest -m 'not integration'` |
| IS-2 | openapi.yaml matching running service | IN_PROGRESS | `python scripts/export_openapi.py` |
| IS-3 | Background jobs with progress | IN_PROGRESS | `tests/test_idempotency.py::test_get_job_returns_correct_structure` |
| IS-4 | Idempotency-Key on every POST | IN_PROGRESS | `tests/test_idempotency.py` |
| IS-5 | JSON error envelope | IN_PROGRESS | `tests/test_errors.py` |
| IS-6 | All config from env vars | IN_PROGRESS | `app/core/settings.py` |
| IS-7 | S3-compatible storage | IN_PROGRESS | `tests/test_storage.py` |
| IS-8 | Structured JSON logs + /health + /ready | IN_PROGRESS | `tests/test_health.py` |
| IS-9 | Output manifest per result | NOT_STARTED | TBD in Prompt 2 |
| IS-10 | Batch runner CLI | IN_PROGRESS | `scripts/batch_runner.py` |
