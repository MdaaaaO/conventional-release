.PHONY: help install lint format typecheck tests ci build release release-dry

help:  ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install:  ## Sync .venv from uv.lock
	uv sync --locked

lint:  ## ruff check + format check + actionlint on the workflows
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uvx --from actionlint-py actionlint

format:  ## Apply ruff fixes and formatting
	uv run --locked ruff check --fix .
	uv run --locked ruff format .

typecheck:  ## mypy --strict
	uv run --locked mypy

tests:  ## pytest with branch coverage
	uv run --locked pytest --cov --cov-report=term-missing

ci: lint typecheck tests  ## Everything CI enforces
	@echo "CI checks passed."

build:  ## sdist + wheel into dist/
	uv build

release-dry:  ## Show what the next release would contain
	uv run --locked conventional-release release --dry-run

release:  ## Release branch + PR (make release ARGS=minor). CI tags on merge.
	uv run --locked conventional-release release $(ARGS)
