# paperflow

Paperflow fetches WG21 C++ standards papers from open-std.org, converts them to markdown, and runs an LLM pipeline that finds mechanically verifiable defects in each paper. It is a uv-managed monorepo of four packages that share a common storage backend.

## Packages

- **paperstore** - Storage abstraction. JsonBackend today, Postgres later, without touching call sites.
- **mailing** - Scrapes the open-std.org mailing index and downloads paper sources into the store.
- **tomd** - Converts paper PDFs and HTML to clean markdown.
- **paperlint** - LLM defect-finder pipeline and the user-facing CLI (`paperflow`).

## Install

```bash
uv sync && source .venv/bin/activate
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Outside an activated venv, prefix commands with `uv run`.

## Commands

```bash
# Fetch mailing indexes from open-std.org (all years)
paperflow mailing

# Fetch specific year(s)
paperflow mailing 2026
paperflow mailing 2025 2026

# Convert a single paper to markdown (downloads PDF, no LLM)
paperflow convert P3642R4

# Convert all papers in a mailing
paperflow convert 2026-04

# Evaluate a single paper (requires OPENROUTER_API_KEY)
paperflow eval P3642R4

# Evaluate all papers in a mailing
paperflow run 2026-04
```

`paperflow mailing` is the only command that fetches index metadata from the internet. `convert` resolves papers from the local index and downloads the paper source. `eval` and `run` are purely local (LLM calls aside).

All commands default their workspace to `$PAPERFLOW_WORKSPACE` or `./data`. Override with `--workspace-dir`.

## Tests

```bash
uv run pytest
```

## License

Boost Software License 1.0
