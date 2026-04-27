# CLAUDE.md

## Spellings

- **PaperLint** (prose), **paperlint** (package), **paperflow** (CLI, system, repo)
- **tomd** (lowercase always), **WG21** (no space)

## Layout

```
packages/
  paperstore/   -> storage abstraction (JsonBackend)
  mailing/      -> scrape open-std.org + download paper sources
  tomd/         -> PDF/HTML to Markdown
  paperlint/    -> LLM pipeline, hosts the `paperflow` CLI
tests/          -> cross-package integration test
```

Per-package rules: `packages/<name>/src/<name>/CLAUDE.md`. Consult those when working inside a package.

## CLI commands

```bash
paperflow mailing [YEAR ...]     # fetch indexes from open-std.org (only internet command for indexes)
paperflow convert P3642R4        # download source + convert to paper.md + meta.json (no LLM)
paperflow convert 2026-04        # batch convert all papers in a mailing
paperflow eval P3642R4           # LLM eval of one paper (needs OPENROUTER_API_KEY)
paperflow run 2026-04            # LLM eval of all papers in a mailing
```

Bare paper ids resolve from local mailing indexes. Outside a venv, prefix with `uv run`. Workspace defaults to `$PAPERFLOW_WORKSPACE` or `./data`.

## On-disk layout

```
<workspace>/
  mailings/<mailing-id>.json
  <pid>.pdf | <pid>.html
  <pid>.md
  <pid>.meta.json
  <pid>.eval.json
  <pid>.1-findings.json          # intermediate
  <pid>.2-gate.json              # intermediate
  <pid>.2c-suppressed.json       # intermediate
  <pid>.prompts.json             # tomd, uncertain regions only
```

## Invariants

- **All storage goes through `paperstore.StorageBackend`.** Never write files directly. Never construct paths from `backend.workspace_dir`.
- **`convert` and `eval`/`run` never share work.** Eval reads via the backend. It never refetches or re-converts.
- **Always write `<pid>.eval.json`, even on failure.** Partial skeleton with `pipeline_status="partial"`. Missing markdown/metadata raises `FileNotFoundError`, writes nothing.
- **`prompt_hash`** is SHA-256 (12 hex chars) over all prompts + rubric. Any edit flips the hash; prior runs are stale.

## Tests

```bash
uv run pytest                                  # full workspace
uv run --package paperstore pytest             # one package
uv run pytest tests/test_end_to_end_convert.py # integration
```

Stub seams: `paperlint.llm.call_with_retry` / `build_client` for LLM calls. `requests.get` on `mailing.download` for downloads.

## Style

- No em dashes. Use commas, periods, or colons.
- BSL-1.0 copyright headers on new `.py` files. Attribute to whoever authors the file. Leave existing headers alone.
