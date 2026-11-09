SHELL := /bin/bash

PY_IMPORT = optionctl

.PHONY: all
all:
	@echo "Run my targets individually!"

.PHONY: dev
dev:
	uv sync --group dev
	uv run --locked --no-config prek install
.PHONY: run
run:
	uv run --locked --no-config optionctl $(ARGS)

.PHONY: lint
lint:
	uv sync --locked --no-config --group lint
	uv run --locked --no-config ruff format --check && \
		uv run --locked --no-config ruff check && \
		uv run --locked --no-config ty check && \
		uv run --locked --no-config interrogate -c pyproject.toml .

.PHONY: format
format:
	uv sync --locked --no-config --group lint
	uv run --locked --no-config ruff format && \
		uv run --locked --no-config ruff check --fix

.PHONY: test
test:
	uv run --locked --no-config python scripts/live-e2e.py

.PHONY: check
check: lint build

.PHONY: doc
doc:
	uv run --locked --no-config pdoc -o html $(PY_IMPORT)

.PHONY: build
build:
	uv lock --check --no-config
	uv build --no-config
