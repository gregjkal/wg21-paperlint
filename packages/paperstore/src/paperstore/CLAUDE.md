# paperstore - Agent Rules

## What this is

The storage abstraction for paperflow. Every other package depends on paperstore; paperstore depends only on the standard library. Adding cross-package imports here is a layering violation.

## On-disk layout (JsonBackend)

Flat, one file per artifact, lowercase paper id stem:

```text
<workspace>/
  mailings/<mailing-id>.json
  <pid>.pdf | <pid>.html | <pid>.htm   # mailing.download
  <pid>.md                              # tomd
  <pid>.prompts.json                    # tomd, only on uncertain regions; JSON array of LLM reconcile prompts
  <pid>.meta.json                       # paperlint convert
  <pid>.1-findings.json                 # paperlint eval, discovery
  <pid>.2-gate.json                     # paperlint eval, gate
  <pid>.2c-suppressed.json              # paperlint eval, suppression
  <pid>.eval.json                       # paperlint eval, final
```

Numeric prefixes on intermediates are intentional: `ls <workspace>/<pid>.*` reads top-to-bottom in pipeline order.

## Invariants

- **`JsonBackend` is currently the only backend.** A Postgres backend is planned but deferred. New methods must be added to the `StorageBackend` ABC first; do not let `JsonBackend`-specific behavior leak into call sites.
- **No path arithmetic outside the backend.** Callers must not build paths from `backend.workspace_dir / pid / "..."`. Use accessors: `get_source_path`, `get_paper_md`, `get_meta`, `get_evaluation`, `list_paper_ids`. Display sites use return values from `convert_paper` / `write_meta_json` / `write_paper_md`.
- **`get_source_path -> Path` assumes a local filesystem.** Non-local backends must materialize bytes to a temp file before returning. Document this in any new backend.
- **`get_meta` falls back to the mailing-index row** when `<pid>.meta.json` is absent. This is intentional: tomd runs after mailing but before paperlint writes meta, and it needs paper-type/title from the mailing row to fill YAML fallback. Don't remove the fallback without tracing every caller.
- **Errors are typed.** Raise `MissingSourceError` / `MissingMetaError` / `MissingPaperMdError` / `MissingEvaluationError` / `MissingMailingIndexError` (all subclasses of `PaperstoreError`), not generic `FileNotFoundError`, so callers can distinguish stages.
- **Paper id casing is normalized.** Filesystem stems are lowercase; `list_paper_ids` returns uppercase. APIs accept any input casing.
- **`mailings/` is the only top-level workspace subdirectory.** Everything else is a flat `<pid>.<suffix>` file. Don't introduce more sibling dirs without updating `list_paper_ids` and consumers that scan the workspace.

## When to bypass

Don't. Every CLI in the workspace uses `JsonBackend` (or `from_uri`); writing files directly would defeat the abstraction.
