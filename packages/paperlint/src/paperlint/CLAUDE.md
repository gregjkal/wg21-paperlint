# paperlint - Agent Rules

## What this is

The LLM defect-finding pipeline for WG21 papers. `paperlint.orchestrator.run_paper_eval` is the per-paper entry point; the per-step logic is in `paperlint.pipeline`. Storage and conversion live elsewhere (paperstore, mailing, tomd).

## Pipeline order

```
load_converted_paper            # <pid>.md + <pid>.meta.json via backend.get_paper_md/get_meta
  -> step_discovery             # LLM, Opus, JSON + thinking. Multi-pass.
  -> write <pid>.1-findings.json
  -> step_verify_quotes         # Pure Python. Drops findings whose evidence
                                # quote isn't a literal/whitespace-normalized
                                # substring of the paper markdown.
  -> step_gate                  # LLM, Opus, JSON + thinking. PASS/REJECT/REFER.
  -> write <pid>.2-gate.json
  -> step_suppress_known_fps    # Post-gate suppression of known
                                # extraction-artifact false positives.
  -> write <pid>.2c-suppressed.json
  -> step_summary_writer        # LLM, Sonnet, JSON. Prose summary only.
  -> assemble <pid>.eval.json
```

## Invariants

- **`convert` and `eval`/`run` never share work.** `run_paper_eval` reads the paper markdown and metadata via the backend (`get_paper_md` / `get_meta`); it does not refetch or re-tomd. If you find yourself adding a fetch to the eval path, reconsider.
- **Quotes are verifiable until proven otherwise.** `step_verify_quotes` does literal-substring then whitespace-normalized matching against the paper markdown. Findings with any unverifiable evidence are dropped *before* the gate sees them.
- **Gate `judgment=true` is rewritten to REJECT.** This is intentional precision tuning per the rubric's "mechanically verifiable" framing. Don't relax it without a discussion.
- **Always write the evaluation, even on failure.** Analysis-stage exceptions are caught; the orchestrator writes a `pipeline_status="partial"` skeleton with `failure_stage` / `failure_type` / `failure_message` to `<pid>.eval.json`. `PAPERLINT_ERROR_TRACEBACK=1` adds `failure_traceback`. Missing paper markdown or metadata is a different path: `FileNotFoundError` (re-raised from `MissingPaperMdError` / `MissingMetaError`), no file is written.
- **Storage goes through `StorageBackend`.** Don't write files directly from orchestrator or pipeline; don't construct paths from `backend.workspace_dir`. A future Postgres backend must work without changing call sites.
- **`prompt_hash`** is `sha256(b"".join(read_bytes for f in sorted(prompts/**/*.md) + [rubric.md]))`, truncated to 12 hex chars. Any change to a prompt or the rubric flips the hash and consumers should treat prior runs as stale. Keep prompt edits in `paperlint/prompts/` and `paperlint/rubric.md` so the hash stays accurate.

## LLM contract

`paperlint.llm.call_with_retry` retries only `RateLimitError`, `APIConnectionError`, `APITimeoutError`. Every other exception logs the response body and raises. `parse_json` / `strip_fences` tolerate OpenRouter's occasional code-fence wrapping; use them rather than reinventing JSON parsing at call sites.

## Logging

`paperlint.logutil` owns log configuration. It is idempotent: the first successful configuration in the process wins. Don't reconfigure `logging.basicConfig` from sub-modules.
