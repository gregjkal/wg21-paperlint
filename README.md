# paperflow

Paperflow fetches WG21 C++ standards papers from open-std.org, converts them to markdown, and runs an LLM pipeline that finds mechanically verifiable defects in each paper. It is a uv-managed monorepo of four packages that share a common SQLite storage backend.

## Commands

```bash
# Full pipeline for a year (scrape + download + convert + eval)
paperflow 2026

# Individual stages
paperflow mailing 2026          # scrape mailing indexes (no downloads)
paperflow mailing all           # scrape all years >= 2011
paperflow download 2026         # fetch source files (PDF/HTML)
paperflow download P3642R4      # fetch a specific paper
paperflow convert 2026          # convert staged sources to markdown
paperflow eval 2026             # LLM eval (requires OPENROUTER_API_KEY)
paperflow eval P3642R4          # eval a single paper
paperflow full 2026             # all four stages
paperflow full all              # everything not yet done

# Idempotency: re-running any command skips already-complete work
paperflow download all          # downloads only what's not yet staged
paperflow convert all           # converts only what's not yet converted
paperflow eval all              # evals only what's not yet complete
```

### Flags

| Flag | Commands | Description |
|------|----------|-------------|
| `--refetch` | download, convert, eval, full | Redo stage even if already complete |
| `--verify` | download, full | HEAD-check staged files against Content-Length |
| `--concurrency N` | download, convert, eval, full | Parallel workers (defaults vary) |
| `--discovery-passes N` | eval, full | LLM discovery passes per paper (default: 3) |
| `--workspace-dir DIR` | all | Backend root (default: `$PAPERFLOW_WORKSPACE` or `./data`) |

All commands and flags are shown by running `paperflow` with no arguments.

## Install

```bash
uv sync && source .venv/bin/activate
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Outside an activated venv, prefix commands with `uv run`.

Set `OPENROUTER_API_KEY` for the `eval` and `full` commands.

## Tests

```bash
uv run pytest
```

## Packages

- **paperstore** - SQLite storage backend (`SqliteBackend`). All metadata in `papers.db`; source files, markdown, and eval JSON on disk.
- **mailing** - Scrapes the open-std.org mailing index and downloads paper sources.
- **tomd** - Converts paper PDFs and HTML to clean markdown.
- **paperlint** - LLM defect-finder pipeline and the user-facing CLI (`paperflow`).

## License

Boost Software License 1.0
