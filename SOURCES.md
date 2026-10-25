# Sources — IncuBrix Distribution

## Libraries and Frameworks

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| FastAPI | ≥0.115 | MIT | Web framework |
| SQLAlchemy | ≥2.0 | MIT | ORM |
| asyncpg | ≥0.30 | Apache 2.0 | PostgreSQL async driver |
| Alembic | ≥1.14 | MIT | Database migrations |
| Pydantic | ≥2.9 | MIT | Data validation |
| pydantic-settings | ≥2.6 | MIT | Settings management |
| httpx | ≥0.28 | BSD 3-Clause | HTTP client |
| aiobotocore | ≥2.15 | Apache 2.0 | S3-compatible storage client |
| cryptography | ≥43.0 | Apache 2.0 / BSD | Fernet encryption |
| PyYAML | ≥6.0 | MIT | YAML parsing |
| structlog | ≥24.4 | MIT | Structured logging |
| pytest | ≥8.3 | MIT | Testing |
| pytest-asyncio | ≥0.24 | Apache 2.0 | Async test support |

## Docker Images

| Image | License | Use |
|-------|---------|-----|
| postgres:16-alpine | PostgreSQL License | Application and test database |
| minio/minio / pgsty/silo | AGPLv3 / Apache 2.0 | S3-compatible object storage (compose only, not shipped in service) |
| ghost:5.101-alpine | MIT | Local Ghost test instance |
| dessalines/lemmy | AGPLv3 | Local Lemmy test instance (compose only) |

## Data Sources
No external datasets used.

## Media
No external media used.
