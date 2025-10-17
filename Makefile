.PHONY: help test coverage lint format typecheck openapi run clean

# Use virtual environment's Python if available, otherwise use system Python
PYTHON := $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

test: ## Run tests
	$(PYTHON) -m pytest

coverage: ## Run tests with coverage report
	$(PYTHON) -m pytest --cov --cov-report=html --cov-report=term

lint: ## Run linting checks
	$(PYTHON) -m ruff check .

format: ## Format code
	$(PYTHON) -m ruff format .

typecheck: ## Run type checking
	$(PYTHON) -m mypy src

openapi: ## Export OpenAPI specification to openapi.json
	$(PYTHON) scripts/export_openapi.py

run: ## Run the development server
	$(PYTHON) -m token_bowl_chat_server

clean: ## Clean up generated files
	rm -rf htmlcov
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -f .coverage
	rm -f chat.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

.DEFAULT_GOAL := help
