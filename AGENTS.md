# AGENTS.md

## Cursor Cloud specific instructions

### Overview

RDSAI CLI is a Python 3.13+ CLI tool for AI-powered database management. It uses `uv` as its package manager and `hatchling` as the build backend. All tests are self-contained (DuckDB is mocked in `tests/conftest.py`); no external database or API key is needed for the test suite.

### Common commands

See `CONTRIBUTING.md` for full details. Quick reference:

- **Install deps:** `uv sync --extra dev`
- **Run CLI:** `uv run rdsai`
- **Run tests:** `uv run pytest` (or `./dev/pytest.sh`)
- **Lint check:** `uv run ruff check .`
- **Format check:** `uv run ruff format --check .`
- **Auto-fix lint+format:** `./dev/code-style.sh`

### Gotchas

- The CLI uses `prompt-toolkit` and `Rich` for interactive terminal UI, so piped stdin/stdout won't render tables or prompts properly. Use a real terminal (e.g. via `computerUse` subagent) to visually test the REPL.
- AI features require a configured LLM provider (`/setup` command); without one, the CLI still starts and handles SQL queries and local file connections via DuckDB.
- `uv` must be on `PATH`. It is installed to `~/.local/bin`; the update script handles this via `PATH` export.
