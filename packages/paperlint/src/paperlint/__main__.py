#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Paperflow CLI - WG21 paper ingestion, conversion, and evaluation.

Three-step flow:

1. **mailing** - fetch mailing indexes from open-std.org (the only internet
   step for index metadata). Accepts years or no args (all years).
2. **convert** - download paper source and convert to markdown. Resolves
   papers from local mailing indexes. No LLM calls.
3. **eval** (one paper) or **run** (batch) - load converted artifacts and
   run the LLM pipeline to ``evaluation.json``.

Example::

    paperflow mailing 2026
    paperflow convert P3642R4
    paperflow eval P3642R4

``--workspace-dir`` (alias: ``--output-dir``) is the JSON-backend root. It
defaults to ``$PAPERFLOW_WORKSPACE`` or ``./data``.
"""

import argparse
import json
import os
import re
import sys
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from paperlint.logutil import configure_paperlint_console_logging
from paperlint.models import (
    SCHEMA_VERSION,
    FailureEntry,
    IndexPaperEntry,
    MailingIndex,
    RoomEntry,
    to_dict,
)
from paperlint.orchestrator import (
    convert_one_paper,
    git_sha,
    prompt_hash,
    run_paper_eval,
)
from paperstore import WORKSPACE_ENV_VAR, JsonBackend, default_workspace_dir
from paperstore.errors import MissingMailingIndexError

_WORKSPACE_DIR_HELP = (
    "Workspace directory: mailings/<id>.json plus flat per-paper artifacts "
    "(<pid>.pdf|.html, <pid>.md, <pid>.meta.json, <pid>.eval.json, ...). "
    "Same path is read and written. Alias: --output-dir. "
    f"Default: ${WORKSPACE_ENV_VAR} or ./data."
)

_YEAR_RE = re.compile(r"^\d{4}$")
_MAILING_ID_RE = re.compile(r"^\d{4}-\d{2}$")
_EVAL_REF_RE = re.compile(r"^(?P<mailing>\d{4}-\d{2})/(?P<paper>[A-Za-z][A-Za-z0-9\-]*)$")
_BARE_PAPER_RE = re.compile(r"^[A-Za-z]")


def _add_workspace_dir_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--workspace-dir",
        "--output-dir",
        dest="workspace_dir",
        metavar="DIR",
        default=default_workspace_dir(),
        help=_WORKSPACE_DIR_HELP,
    )


def _backend_for(workspace_dir: Path) -> JsonBackend:
    """Construct the default JSON storage backend rooted at ``workspace_dir``."""
    return JsonBackend(workspace_dir)


def _classify_arg(arg: str) -> str:
    """Classify a positional argument as 'year', 'mailing', 'eval_ref', or 'paper'."""
    if _YEAR_RE.match(arg):
        return "year"
    if _MAILING_ID_RE.match(arg):
        return "mailing"
    if _EVAL_REF_RE.match(arg):
        return "eval_ref"
    if _BARE_PAPER_RE.match(arg):
        return "paper"
    raise ValueError(
        f"Unrecognized argument format: {arg!r}. Expected a year (2026), "
        f"mailing id (2026-04), paper id (P2900R15), or eval ref (2026-04/P2900R15)."
    )


def _resolve_paper_locally(
    paper_id: str, backend: JsonBackend
) -> tuple[str, dict]:
    """Resolve a bare paper ID from local mailing indexes.

    Returns ``(mailing_id, paper_row)``. Raises ``SystemExit`` on failure.
    """
    result = backend.resolve_mailing_for_paper(paper_id)
    if result is None:
        print(
            f"Error: {paper_id.upper()} not found in local mailing indexes.\n"
            f"Run 'paperflow mailing' to fetch indexes from open-std.org first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return result


# ---------------------------------------------------------------------------
# Helper wrappers (unchanged from prior version)
# ---------------------------------------------------------------------------

def _eval_one_paper(
    paper_ref: str,
    workspace_dir: Path,
    source_url: str = "",
    mailing_meta: dict | None = None,
    *,
    discovery_passes: int = 3,
) -> dict:
    try:
        result = run_paper_eval(
            paper_ref,
            workspace_dir=workspace_dir,
            source_url=source_url,
            mailing_meta=mailing_meta,
            discovery_passes=discovery_passes,
        )
        return {"paper": paper_ref, "status": "ok", "result": result}
    except Exception as e:
        traceback.print_exc()
        return {"paper": paper_ref, "status": "error", "error": str(e)}


def _convert_one(
    paper_ref: str,
    workspace_dir: Path,
    source_url: str,
    mailing_meta: dict,
) -> dict:
    try:
        result = convert_one_paper(
            paper_ref,
            workspace_dir=workspace_dir,
            source_url=source_url,
            mailing_meta=mailing_meta,
        )
        return {
            "paper": paper_ref,
            "status": "ok",
            "paper_md": str(result["paper_md_path"]),
            "meta_path": str(result["meta_path"]),
        }
    except Exception as e:
        traceback.print_exc()
        return {"paper": paper_ref, "status": "error", "error": str(e)}


def _failure_entry(r: dict) -> FailureEntry:
    if r["status"] == "error":
        return FailureEntry(paper=r["paper"], error=r.get("error", ""))
    res = r.get("result") or {}
    return FailureEntry(
        paper=res.get("paper", r["paper"]),
        pipeline_status=res.get("pipeline_status"),
        summary=res.get("summary", ""),
        failure_stage=res.get("failure_stage"),
        failure_type=res.get("failure_type"),
        failure_message=res.get("failure_message"),
        failure_traceback=res.get("failure_traceback"),
    )


def _build_index(workspace_dir: Path, mailing_id: str, results: list[dict]) -> dict:
    succeeded = [
        r for r in results
        if r["status"] == "ok"
        and r.get("result", {}).get("pipeline_status") == "complete"
    ]
    failed = [
        r for r in results
        if r["status"] == "error"
        or r.get("result", {}).get("pipeline_status") in ("failed", "partial")
    ]
    partial_count = sum(
        1 for r in results
        if r.get("result", {}).get("pipeline_status") == "partial"
    )

    rooms: dict[str, RoomEntry] = defaultdict(RoomEntry)
    papers_summary: list[IndexPaperEntry] = []

    for r in succeeded:
        ev = r["result"]
        paper_id = ev.get("paper", r["paper"])
        audience = ev.get("audience", "Unknown")
        n_findings = ev.get("findings_passed", 0)

        for room in [a.strip() for a in audience.split(",")]:
            if room:
                rooms[room].papers.append(paper_id)
                rooms[room].total_findings += n_findings

        papers_summary.append(
            IndexPaperEntry(
                paper=paper_id,
                title=ev.get("title", ""),
                audience=audience,
                findings_passed=n_findings,
                findings_discovered=ev.get("findings_discovered", 0),
            )
        )

    index = MailingIndex(
        schema_version=SCHEMA_VERSION,
        paperlint_sha=git_sha(),
        prompt_hash=prompt_hash(),
        mailing_id=mailing_id,
        generated=datetime.now(timezone.utc).isoformat(),
        total_papers=len(results),
        succeeded=len(succeeded),
        failed=len(failed),
        partial=partial_count,
        rooms={k: rooms[k] for k in sorted(rooms)},
        papers=sorted(papers_summary, key=lambda p: p.findings_passed),
        failed_papers=[_failure_entry(r) for r in failed] if failed else None,
    )

    return to_dict(index)


def _parse_papers_filter(papers_arg: str | None) -> set[str] | None:
    """Return uppercase paper ids, or None if the argument is empty."""
    if not papers_arg or not str(papers_arg).strip():
        return None
    return {p.strip().upper() for p in str(papers_arg).split(",") if p.strip()}


def _merge_paper_selectors(
    single: str | None, comma_list: str | None
) -> str | None:
    """Join ``--paper`` and ``--papers`` into a comma string."""
    parts: list[str] = []
    if single and str(single).strip():
        parts.append(str(single).strip())
    if comma_list and str(comma_list).strip():
        parts.extend(
            p.strip() for p in str(comma_list).split(",") if p and str(p).strip()
        )
    if not parts:
        return None
    return ",".join(parts)


def _filter_papers_list(
    papers: list[dict], mailing_id: str, want: set[str] | None, *, what: str
) -> list[dict]:
    """If *want* is set, keep only matching paper_ids and warn on unknowns."""
    if not want:
        return list(papers)
    have = {p["paper_id"].upper() for p in papers}
    missing = sorted(want - have)
    if missing:
        print(
            f"Warning: {what} {mailing_id!r} has no paper_id(s): {', '.join(missing)}",
            file=sys.stderr,
        )
    return [p for p in papers if p["paper_id"].upper() in want]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_mailing(args: argparse.Namespace) -> int:
    """Fetch mailing indexes from open-std.org and persist locally.

    The only command that fetches index metadata from the internet. Idempotent:
    re-running preserves existing entries and their ``added`` timestamps.
    """
    from mailing.scrape import discover_years, fetch_all_mailings_for_year

    workspace_dir = Path(args.workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    backend = _backend_for(workspace_dir)

    years = args.years if args.years else None
    if not years:
        print("Discovering available years from open-std.org...")
        years = discover_years()
        if not years:
            print("No years found on open-std.org.", file=sys.stderr)
            return 1
        print(f"Found {len(years)} years: {years[0]}-{years[-1]}")

    total_mailings = 0
    total_papers = 0
    for year in years:
        if not _YEAR_RE.match(year):
            print(f"Error: {year!r} is not a valid year. Expected 4-digit year (e.g. 2026).", file=sys.stderr)
            return 2
        print(f"Fetching {year}...")
        all_mailings = fetch_all_mailings_for_year(year)
        if not all_mailings:
            print(f"  No mailings found for {year}.")
            continue
        for mailing_id, papers in sorted(all_mailings.items()):
            merged = backend.upsert_mailing_index(mailing_id, papers)
            total_mailings += 1
            total_papers += len(merged)

    print(f"\n{'=' * 60}")
    print(f"Mailing sync complete: {total_mailings} mailings, {total_papers} papers")
    print(f"{'=' * 60}")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    """Download and convert papers to markdown. No LLM calls.

    Reads the local mailing index to find paper source URLs. Does not fetch
    mailing indexes from the internet. Run ``paperflow mailing`` first to
    populate the local index.
    """
    workspace_dir = Path(args.workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    backend = _backend_for(workspace_dir)
    max_cap = args.max_cap
    max_workers = args.max_workers

    target = args.target
    kind = _classify_arg(target)

    if kind == "paper":
        mailing_id, meta = _resolve_paper_locally(target, backend)
        print(f"Resolved {target.upper()} to mailing {mailing_id}")
        r = _convert_one(target.upper(), workspace_dir, meta.get("url", ""), meta)
        status = "OK" if r["status"] == "ok" else "FAILED"
        print(f"  [{status}] {target.upper()}")
        return 0 if r["status"] == "ok" else 1

    if kind == "mailing":
        mailing_id = target
        try:
            papers = backend.list_mailing(mailing_id)
        except MissingMailingIndexError:
            print(
                f"Error: No local mailing index for {mailing_id}.\n"
                f"Run 'paperflow mailing {mailing_id.split('-')[0]}' first.",
                file=sys.stderr,
            )
            return 1

        meta_by_id = {p["paper_id"]: p for p in papers}
        sel = _merge_paper_selectors(
            getattr(args, "paper", None), getattr(args, "papers", None)
        )
        pf = _parse_papers_filter(sel)
        if pf:
            papers = _filter_papers_list(papers, mailing_id, pf, what="mailing")
            if not papers:
                print("No papers to convert after filter.", file=sys.stderr)
                return 1
        if max_cap > 0:
            papers = papers[:max_cap]

        print(f"Converting {len(papers)} papers from {mailing_id}...")
        results: list[dict] = []
        if max_workers == 1:
            for p in papers:
                pid = p["paper_id"]
                pm = meta_by_id.get(pid, p)
                r = _convert_one(pid, workspace_dir, pm.get("url", ""), pm)
                results.append(r)
                status = "OK" if r["status"] == "ok" else "FAILED"
                print(f"  [{status}] {pid}")
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for p in papers:
                    pid = p["paper_id"]
                    pm = meta_by_id.get(pid, p)
                    f = executor.submit(
                        _convert_one, pid, workspace_dir, pm.get("url", ""), pm,
                    )
                    futures[f] = pid
                for future in as_completed(futures):
                    pid = futures[future]
                    r = future.result()
                    results.append(r)
                    status = "OK" if r["status"] == "ok" else "FAILED"
                    print(f"  [{status}] {pid}")

        succeeded = sum(1 for r in results if r["status"] == "ok")
        failed = len(results) - succeeded
        print(f"\n{'=' * 60}")
        print(f"Convert {mailing_id}: {succeeded}/{len(results)} succeeded, {failed} failed")
        print(f"{'=' * 60}")
        return 0 if failed == 0 else 1

    print(
        f"Error: convert expects a paper id (P2900R15) or mailing id (2026-04), "
        f"got {target!r}.",
        file=sys.stderr,
    )
    return 2


def cmd_eval(args: argparse.Namespace) -> int:
    """Evaluate a single paper via the LLM pipeline.

    Accepts a bare paper id (P2900R15) or a mailing/paper ref (2026-04/P2900R15).
    Reads paper.md and meta.json from the workspace. Run ``paperflow convert``
    first if missing.
    """
    workspace_dir = Path(args.workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    backend = _backend_for(workspace_dir)

    ref = args.paper
    kind = _classify_arg(ref)

    if kind == "eval_ref":
        m = _EVAL_REF_RE.match(ref.strip())
        mailing_id = m.group("mailing")
        paper_id = m.group("paper").upper()
        try:
            papers = backend.list_mailing(mailing_id)
        except MissingMailingIndexError:
            print(
                f"Error: No local mailing index for {mailing_id}.\n"
                f"Run 'paperflow mailing {mailing_id.split('-')[0]}' first.",
                file=sys.stderr,
            )
            return 1
        meta = next((p for p in papers if p["paper_id"].upper() == paper_id), None)
        if not meta:
            print(f"Error: {paper_id} not found in mailing {mailing_id}.", file=sys.stderr)
            return 1
    elif kind == "paper":
        paper_id = ref.upper()
        mailing_id, meta = _resolve_paper_locally(ref, backend)
        print(f"Resolved {paper_id} to mailing {mailing_id}")
    else:
        print(
            f"Error: eval expects a paper id (P2900R15) or eval ref (2026-04/P2900R15), "
            f"got {ref!r}.",
            file=sys.stderr,
        )
        return 2

    try:
        run_paper_eval(
            paper_id,
            workspace_dir=workspace_dir,
            source_url=meta.get("url", ""),
            mailing_meta=meta,
            discovery_passes=args.discovery_passes,
        )
        return 0
    except FileNotFoundError as e:
        print(
            f"Error: {e}\n"
            f"Run 'paperflow convert {paper_id}' first.",
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    """Evaluate all papers in a mailing via the LLM pipeline.

    Reads from the local mailing index. Run ``paperflow mailing`` and
    ``paperflow convert`` first.
    """
    workspace_dir = Path(args.workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    backend = _backend_for(workspace_dir)

    mailing_id = args.mailing_id
    max_cap = args.max_cap
    max_processes = args.max_processes if args.max_processes is not None else args.max_workers

    try:
        papers = backend.list_mailing(mailing_id)
    except MissingMailingIndexError:
        print(
            f"Error: No local mailing index for {mailing_id}.\n"
            f"Run 'paperflow mailing {mailing_id.split('-')[0]}' first.",
            file=sys.stderr,
        )
        return 1

    meta_by_id = {p["paper_id"]: p for p in papers}

    sel = _merge_paper_selectors(
        getattr(args, "paper", None), getattr(args, "papers", None)
    )
    pf = _parse_papers_filter(sel)
    if pf:
        papers = _filter_papers_list(papers, mailing_id, pf, what="mailing")
        if not papers:
            print("No papers to process after --papers filter.", file=sys.stderr)
            return 1
    if max_cap > 0:
        papers = papers[:max_cap]

    print(f"Processing {len(papers)} papers with {max_processes} workers...")

    results: list[dict] = []

    if max_processes == 1:
        for p in papers:
            pid = p["paper_id"]
            pm = meta_by_id.get(pid, p)
            result = _eval_one_paper(
                pid,
                workspace_dir,
                source_url=pm.get("url", ""),
                mailing_meta=pm,
                discovery_passes=args.discovery_passes,
            )
            results.append(result)
            status = "OK" if result["status"] == "ok" else "FAILED"
            print(f"\n  [{status}] {pid}")
    else:
        with ThreadPoolExecutor(max_workers=max_processes) as executor:
            futures = {}
            for p in papers:
                pid = p["paper_id"]
                pm = meta_by_id.get(pid, p)
                f = executor.submit(
                    _eval_one_paper,
                    pid,
                    workspace_dir,
                    pm.get("url", "") if pm else "",
                    pm,
                    discovery_passes=args.discovery_passes,
                )
                futures[f] = pid
            for future in as_completed(futures):
                pid = futures[future]
                result = future.result()
                results.append(result)
                status = "OK" if result["status"] == "ok" else "FAILED"
                print(f"\n  [{status}] {pid}")

    index = _build_index(workspace_dir, mailing_id, results)
    index_path = workspace_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    succeeded = index["succeeded"]
    failed = index["failed"]
    total = index["total_papers"]
    print(f"\n{'=' * 60}")
    print(f"Mailing {mailing_id} complete: {succeeded}/{total} succeeded, {failed} failed")
    print(f"Rooms: {', '.join(index['rooms'].keys())}")
    print(f"Index: {index_path}")
    print(f"{'=' * 60}")

    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Argument parsing and main
# ---------------------------------------------------------------------------

def main() -> int:
    prog_name = os.path.basename(sys.argv[0]) if sys.argv else "paperflow"
    if "paperlint" in prog_name and "paperflow" not in prog_name:
        print(
            "Note: 'paperlint' has been renamed to 'paperflow'. "
            "The old name still works.",
            file=sys.stderr,
        )

    parser = argparse.ArgumentParser(
        prog="paperflow",
        description="WG21 paper ingestion, conversion, and evaluation",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v = INFO, -vv = DEBUG). Default is WARNING.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- mailing --
    mailing_parser = subparsers.add_parser(
        "mailing",
        help="Fetch mailing indexes from open-std.org (idempotent)",
        description=(
            "Fetch mailing indexes from open-std.org and persist locally. "
            "With no arguments, discovers and fetches all available years. "
            "With year arguments, fetches only those years."
        ),
    )
    mailing_parser.add_argument(
        "years",
        nargs="*",
        metavar="YEAR",
        help="One or more years to fetch (e.g. 2026 2025). Omit for all years.",
    )
    _add_workspace_dir_arg(mailing_parser)

    # -- convert --
    convert_parser = subparsers.add_parser(
        "convert",
        help="Download and convert papers to markdown (no LLM)",
        description=(
            "Download paper source and convert to markdown. Resolves papers "
            "from local mailing indexes (run 'paperflow mailing' first). "
            "Accepts a bare paper id (P2900R15) or a mailing id (2026-04)."
        ),
    )
    convert_parser.add_argument(
        "target",
        help="Paper id (P2900R15) or mailing id (2026-04)",
    )
    _add_workspace_dir_arg(convert_parser)
    convert_parser.add_argument("--max-cap", type=int, default=0, help="Max papers (0 = all)")
    convert_parser.add_argument("--max-workers", type=int, default=10, help="Parallel workers")
    convert_parser.add_argument(
        "--paper",
        default=None,
        metavar="PAPER",
        help="Filter to one paper id (when target is a mailing id)",
    )
    convert_parser.add_argument(
        "--papers",
        default=None,
        metavar="IDS",
        help="Comma-separated paper ids to convert (when target is a mailing id)",
    )

    # -- eval --
    eval_parser = subparsers.add_parser(
        "eval",
        help="Evaluate a single paper via the LLM pipeline",
        description=(
            "Evaluate a single paper. Accepts a bare paper id (P2900R15) or "
            "a mailing/paper ref (2026-04/P2900R15). Reads paper.md and "
            "meta.json from the workspace; run 'paperflow convert' first."
        ),
    )
    eval_parser.add_argument(
        "paper",
        help="Paper id (P2900R15) or eval ref (2026-04/P2900R15)",
    )
    _add_workspace_dir_arg(eval_parser)
    eval_parser.add_argument(
        "--discovery-passes",
        type=int,
        default=3,
        help=(
            "Number of LLM discovery passes (default: 3). Each pass after the first is "
            "shown prior findings and asked to add only new ones."
        ),
    )

    # -- run --
    run_parser = subparsers.add_parser(
        "run",
        help="Evaluate all papers in a mailing via the LLM pipeline",
        description=(
            "Evaluate all papers in a mailing. Reads from the local mailing "
            "index. Run 'paperflow mailing' and 'paperflow convert' first."
        ),
    )
    run_parser.add_argument("mailing_id", help="Mailing identifier (e.g. 2026-04)")
    _add_workspace_dir_arg(run_parser)
    run_parser.add_argument("--max-cap", type=int, default=0, help="Max papers (0 = all)")
    run_parser.add_argument("--max-workers", type=int, default=10, help="Parallel workers")
    run_parser.add_argument(
        "--paper",
        default=None,
        metavar="PAPER",
        help="One paper id (convenience; can combine with --papers)",
    )
    run_parser.add_argument(
        "--papers",
        default=None,
        metavar="IDS",
        help="Comma-separated paper ids to evaluate, then --max-cap",
    )
    run_parser.add_argument("--max-processes", type=int, default=None, help=argparse.SUPPRESS)
    run_parser.add_argument(
        "--discovery-passes",
        type=int,
        default=3,
        help=(
            "Number of LLM discovery passes (default: 3). Each pass after the first is "
            "shown prior findings and asked to add only new ones."
        ),
    )

    args = parser.parse_args()
    configure_paperlint_console_logging(args.verbose)

    if args.command == "mailing":
        return cmd_mailing(args)
    elif args.command == "convert":
        return cmd_convert(args)
    elif args.command == "eval":
        return cmd_eval(args)
    elif args.command == "run":
        return cmd_run(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
