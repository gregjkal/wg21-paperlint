#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#

"""CLI command module for 'paperflow convert'."""

from __future__ import annotations

import argparse
import asyncio
import sys
from contextlib import nullcontext
from pathlib import Path

from paperstore.backend import StorageBackend


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "convert",
        help="Convert staged source files to markdown (no LLM)",
        description=(
            "Convert staged PDF/HTML sources to markdown using tomd. "
            "Hard-fails if the source is not yet staged - run 'paperflow download' first."
        ),
    )
    p.add_argument(
        "targets",
        nargs="+",
        metavar="TARGET",
        help='Year (2026), paper id(s) (P3642R4 ...), or "all".',
    )
    p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Re-convert even if markdown already exists.",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        metavar="N",
        help="Number of concurrent conversion threads (default: 4).",
    )
    p.add_argument(
        "--no-prompts",
        action="store_true",
        help="Skip writing the .prompts.json intermediate.",
    )
    p.add_argument(
        "--qa",
        action="store_true",
        help="Score existing markdown quality instead of converting (dev/debug; reads paper.md only, never reconverts).",
    )
    p.add_argument(
        "--qa-json",
        type=Path,
        metavar="PATH",
        help="Write per-paper QA metrics as JSON to PATH (implies --qa).",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="QA parallelism (default: 1).",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=120,
        metavar="SEC",
        help="QA straggler timeout in seconds (default: 120).",
    )
    return p


def command(args: argparse.Namespace, backend: StorageBackend) -> int:
    if args.qa or args.qa_json:
        return _qa_command(args, backend)
    return _convert_command(args, backend)


def _convert_command(args: argparse.Namespace, backend: StorageBackend) -> int:
    from paperlint.jobs import run_convert
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    console = Console()
    on_total = None
    on_progress = None
    progress_ctx = nullcontext()

    if console.is_terminal:
        progress = Progress(
            SpinnerColumn(style="green"),
            TextColumn("[bold]{task.description}"),
            BarColumn(complete_style="green", finished_style="bold green"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        )
        progress_ctx = progress
        task_id = progress.add_task("Converting", total=None, start=False)

        def on_total(n: int) -> None:
            progress.update(task_id, total=n)
            progress.start_task(task_id)

        def on_progress(_result: dict) -> None:
            progress.advance(task_id)

    with progress_ctx:
        result = asyncio.run(run_convert(
            args.targets,
            backend,
            force=args.force,
            concurrency=args.concurrency,
            write_prompts=not args.no_prompts,
            on_total=on_total,
            on_progress=on_progress,
        ))

    succeeded = result.get("succeeded", [])
    skipped = result.get("skipped", [])
    failed = result.get("failed", [])

    print(f"Convert: {len(succeeded)} converted, {len(skipped)} skipped, {len(failed)} failed.")
    if failed:
        for item in failed:
            print(f"  ERROR {item['paper_id']}: {item['error']}", file=sys.stderr)
        return 1
    return 0


def _qa_command(args: argparse.Namespace, backend: StorageBackend) -> int:
    from paperlint.jobs import _papers_from_scope, _validate_targets
    from paperstore.errors import MissingPaperMdError
    from tomd.lib.pdf.qa import run_qa_report

    target_type = _validate_targets(args.targets)
    rows = _papers_from_scope(args.targets, target_type, backend)

    items: list[tuple[str, str]] = []
    for row in rows:
        pid = row["paper_id"]
        if not row.get("markdown_path"):
            print(f"Skipping {pid}: no paper markdown. Run 'paperflow convert' first.", file=sys.stderr)
            continue
        try:
            md = backend.get_paper_md(pid)
        except MissingPaperMdError:
            print(f"Skipping {pid}: no paper markdown. Run 'paperflow convert' first.", file=sys.stderr)
            continue
        items.append((pid.upper(), md))

    if not items:
        print("No markdown available for QA.", file=sys.stderr)
        return 1

    run_qa_report(
        items,
        json_path=args.qa_json,
        workers=args.workers,
        timeout=args.timeout,
    )
    return 0
