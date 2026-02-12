# SignalForge local development
# Usage: make help

.PHONY: help install dev migrate upgrade test lint

help:
	@echo "SignalForge local development"
	@echo ""
	@echo "  make install    - Create venv and install dependencies"
	@echo "  make dev       - Run development server"
	@echo "  make migrate   - Create new Alembic migration"
	@echo "  make upgrade   - Run database migrations"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run ruff"

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	@echo "Copy .env.example to .env and configure"
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --reload-exclude '.venv' --reload-exclude '.git'

migrate:
	alembic -c $(CURDIR)/alembic.ini revision --autogenerate -m "migration"

upgrade:
	alembic -c $(CURDIR)/alembic.ini upgrade head

test:
	pytest tests/ -v

lint:
	ruff check app tests
