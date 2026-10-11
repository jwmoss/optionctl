# AGENTS.md

## Project Overview


This is a command-line application with entry point `optionctl`.

## Stack

- Package manager: uv
- Build backend: uv_build
- Linting/formatting: ruff
- Type checking: ty
- Testing: real market-data CLI checks only
- CI: GitHub Actions (lint, build, release, docs)

## Commands

Use Makefile targets, not tool commands directly:

- `make format` - Fix formatting issues
- `make lint` - Run all static checks (ruff, ty)
- `make test` - Read current SPY market data through the CLI
- `make doc` - Generate documentation
- `make build` - Build the package
- `make run` - Run the CLI (use `ARGS="..."` for arguments)

## Verification

Run `make check` before committing. Run `make test` when the network is available.
Report live service failures as unverified. Do not add unit, mock, or fake-server tests.
Live scans can update local caches and prediction history. They cannot place trades.

## Commit Messages

- Summary line: max 50 chars (hard limit 72)
- Body lines: max 72 chars
- Use Markdown formatting in description
- Reference issues where relevant (e.g., `See #123`)

## Project Layout

- `src/optionctl/` - Source code
- `scripts/live-e2e.py` - Real market-data CLI checks
