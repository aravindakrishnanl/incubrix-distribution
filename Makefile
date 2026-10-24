.PHONY: install test test-all migrate alembic-revision export-openapi batch-runner lint

install:
	pip install -r requirements-dev.txt

test:
	pytest -m 'not integration' -v --tb=short

test-all:
	pytest -v --tb=short

test-cov:
	pytest -m 'not integration' --cov=app --cov-report=term-missing --tb=short

migrate:
	alembic upgrade head

alembic-revision:
	alembic revision --autogenerate -m "$(MSG)"

export-openapi:
	python scripts/export_openapi.py

lint:
	ruff check app/ tests/

batch-runner:
	python scripts/batch_runner.py --input tests/batch_inputs/ --output results/ --base-url $(BASE_URL) --token $(TOKEN)
