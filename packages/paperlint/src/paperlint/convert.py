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
    return p


def command(args: argparse.Namespace, backend: StorageBackend) -> int:
    from paperlint.jobs import run_convert
    result = asyncio.run(run_convert(
        args.targets,
        backend,
        force=args.force,
        concurrency=args.concurrency,
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
