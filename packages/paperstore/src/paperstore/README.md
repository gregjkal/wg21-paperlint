# paperstore

Storage abstraction for paperflow artifacts. Every paperflow tool reads and writes through a `StorageBackend`; `JsonBackend` (filesystem-backed JSON) is the only implementation today.

## Layout

A `JsonBackend` rooted at `<workspace>` holds (flat; one file per artifact, lowercase paper id stem):

```
<workspace>/
  mailings/<mailing-id>.json            # one row per paper in the mailing
  <pid>.pdf | <pid>.html | <pid>.htm    # staged by mailing.download
  <pid>.md                              # written by tomd
  <pid>.prompts.json                    # tomd, only when uncertain regions; JSON array of reconcile prompts
  <pid>.meta.json                       # written by paperlint convert
  <pid>.1-findings.json                 # paperlint eval, discovery
  <pid>.2-gate.json                     # paperlint eval, gate
  <pid>.2c-suppressed.json              # paperlint eval, suppression
  <pid>.eval.json                       # paperlint eval, final
```

## Public surface

```python
from paperstore import (
    StorageBackend, JsonBackend, from_uri,
    PaperstoreError,
    MissingMetaError, MissingSourceError, MissingPaperMdError,
    MissingEvaluationError, MissingMailingIndexError,
)
```

Backend methods (see `StorageBackend` for the ABC):

- writes: `write_paper_md`, `write_meta_json`, `write_evaluation_json`, `write_intermediate`, `upsert_mailing_index`, `put_source`
- reads: `get_meta`, `get_source_path`, `get_paper_md`, `get_evaluation`, `list_mailing`, `list_paper_ids`

`from_uri(uri, *, workspace_dir=None)` resolves `None`/`file://...` to a `JsonBackend`. Other schemes (e.g. `postgres://`) are reserved for future backends.

## CLI

After `uv sync && source .venv/bin/activate` from the workspace root (or prefix with `uv run`). Workspace dir defaults to `$PAPERFLOW_WORKSPACE` or `./data`; override per command with `--workspace-dir`.

```
paperstore show-paper P3642R4
paperstore list-mailings
paperstore --workspace-dir ./scratch list-mailings   # explicit override
```

## Tests

```
uv run pytest packages/paperstore/tests
```

The shared `json_store` pytest fixture (`paperstore.testing`) returns a `JsonBackend(tmp_path)`; import it for cross-package tests.
