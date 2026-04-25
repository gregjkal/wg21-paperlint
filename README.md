# paperflow

Paperflow is a uv-managed monorepo of four cooperating packages that fetch, convert, and lint WG21 C++ standards papers. It is part of the wider C++ Alliance / WG21 Civilization Level Reform initiative; PaperLint is the user-facing tool, and the other three packages are the seams underneath it.

## Packages

| Package | Purpose |
|---|---|
| [`paperstore`](packages/paperstore/src/paperstore/README.md) | Storage abstraction. JsonBackend today; Postgres later, without touching call sites. |
| [`mailing`](packages/mailing/src/mailing/README.md) | Scrape the open-std.org mailing index; download paper sources into the store. |
| [`tomd`](packages/tomd/src/tomd/README.md) | PDF / HTML to clean Markdown for committee papers. |
| [`paperlint`](packages/paperlint/src/paperlint/README.md) | The LLM defect-finder pipeline. The user-facing CLI. |

Dependency graph (all libraries; no circular deps):

```
paperstore                        (stdlib only)
mailing      -> paperstore        (download writes via put_source)
tomd         -> paperstore        (reads source + meta, writes paper.md)
paperlint    -> paperstore, mailing, tomd
```

## Install

Python 3.12 or newer. Paperflow uses [uv](https://docs.astral.sh/uv/) for dependency management; install it via the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) if you don't already have it.

```bash
git clone https://github.com/cppalliance/paperlint.git wg21-paperflow
cd wg21-paperflow
uv sync                              # installs all four packages + dev deps
source .venv/bin/activate            # puts paperlint, tomd, mailing, paperstore on PATH
```

`.env` and `.env.local` are auto-loaded. All examples below assume the venv is active; to run without activating, prefix any CLI command with `uv run` (e.g. `uv run paperlint convert ...`). `paperlint eval` and `paperlint run` additionally need `OPENROUTER_API_KEY` in the environment; the `mailing` and `tomd` flows do not.

## Workspace location

Every CLI defaults its workspace root to `$PAPERFLOW_WORKSPACE` if set, otherwise `./data` (cwd-relative). Override per command with `--workspace-dir <DIR>`. Pin a fixed location across shells with `export PAPERFLOW_WORKSPACE=/path/to/workspace`. Examples below omit the flag and rely on the default.

## Quickstart: iterating on tomd

This is the conversion loop, no LLM and no API key. Good entry point for anyone improving the PDF/HTML-to-Markdown path.

```bash
# One-time setup (see Install above).
uv sync && source .venv/bin/activate

# 1. Download a mailing's papers (idempotent; re-runs skip what's already staged).
mailing 2026-04

# 2. Convert the whole corpus to Markdown. Each success line prints the output path.
tomd 2026-04

# 3. Inspect the output.
ls ./data/*/paper.md
open ./data/P3642R4/paper.md                    # or your editor of choice

# 4. Score conversion quality across the corpus.
tomd 2026-04 --qa                               # ranked report to stdout
tomd 2026-04 --qa --qa-json qa.json             # + per-paper JSON for diffing
```

Outputs land at `./data/<PAPER_ID>/paper.md` (plus `<PAPER_ID>.prompts.json` when the converter flagged uncertain regions). The mailing index lives at `./data/mailings/2026-04.json`.

**Edit-rerun loop.** Change tomd source, then rerun `tomd 2026-04`; it overwrites `paper.md` in place, so you can `git diff` the workspace (or snapshot `qa.json` before and after) to see what moved. `mailing 2026-04` does not need to run again unless you want fresh source bytes; add `--refetch` to force a re-download.

## Two-step flow (paperlint)

Conversion is separated from evaluation so eval/run never duplicate work. This path needs `OPENROUTER_API_KEY` in the environment.

```bash
export OPENROUTER_API_KEY=sk-or-...

# 1) Convert a paper (no LLM, no API key).
paperlint convert 2026-04 --paper P3642R4

# 2) Evaluate the converted paper.
paperlint eval 2026-04/P3642R4
```

The open-std.org mailing index is authoritative for paper metadata and is refetched on every command. Bare paper ids and local file paths are not accepted.

## Per-package CLIs

`mailing` and `tomd` are covered in the tomd quickstart above. Two extras:

```bash
# Inspect what's stored.
paperstore list-mailings
paperstore show-paper P3642R4
```

Single-paper variants are available on both CLIs (`mailing 2026-04/P3642R4`, `tomd P3642R4`). See each package's README for the full option set: [`mailing`](packages/mailing/src/mailing/README.md), [`tomd`](packages/tomd/src/tomd/README.md), [`paperstore`](packages/paperstore/src/paperstore/README.md), [`paperlint`](packages/paperlint/src/paperlint/README.md).

## Tests

```bash
uv run pytest                                # full workspace (~545 tests + 1 integration)
uv run --package paperstore pytest           # one package in isolation
uv run --package mailing pytest
uv run --package tomd pytest
uv run --package paperlint pytest
```

The cross-package integration test (`tests/test_end_to_end_convert.py`) drives `mailing.download` -> `tomd.api.convert_paper` against a stubbed `requests.get`.

## Layout

```
wg21-paperflow/
  pyproject.toml          # workspace root
  uv.lock
  packages/
    paperstore/
    mailing/
    tomd/
    paperlint/
  tests/                  # one cross-package integration test
```

## License

Boost Software License 1.0. See `LICENSE_1_0.txt`.
