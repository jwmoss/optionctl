# AGENTS.md

## Project Overview


This is a command-line application with entry point `optionctl`.

## Stack

- Package manager: uv
- Build backend: uv_build
- Linting/formatting: ruff
- Type checking: ty
- Testing: pytest
- CI: GitHub Actions (lint, test, release, docs)

## Commands

Use Makefile targets, not tool commands directly:

- `make format` - Fix formatting issues
- `make lint` - Run all static checks (ruff, ty)
- `make test` - Run tests with coverage
- `make doc` - Generate documentation
- `make build` - Build the package
- `make run` - Run the CLI (use `ARGS="..."` for arguments)

## Verification

Run `make lint && make test` before committing.

## Commit Messages

- Summary line: max 50 chars (hard limit 72)
- Body lines: max 72 chars
- Use Markdown formatting in description
- Reference issues where relevant (e.g., `See #123`)

## Project Layout

- `src/optionctl/` - Source code
- `test/` - Test files
