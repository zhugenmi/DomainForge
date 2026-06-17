.PHONY: install dev migrate test docker-up docker-down lint frontend-install frontend-dev frontend-build

install:
	pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic upgrade head

makemigration:
	alembic revision --autogenerate -m "$(msg)"

test:
	pytest -v --cov=app --cov-report=term-missing

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

lint:
	ruff check app tests
	mypy app

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npx next dev --port 3000

frontend-build:
	cd frontend && npx next build
