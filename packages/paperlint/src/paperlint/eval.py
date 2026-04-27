#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#

"""CLI command module for 'paperflow eval'."""

from __future__ import annotations

import argparse
import asyncio
import sys

from paperstore.backend import StorageBackend


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "eval",
        help="Run the LLM eval pipeline on converted papers",
        description=(
            "Evaluate papers via the LLM defect-discovery pipeline. "
            "Requires OPENROUTER_API_KEY. Run 'paperflow convert' first."
        ),
    )
    p.add_argument(
        "targets",
        nargs="+",
        metavar="TARGET",
        help='Year (2026), paper id(s) (P3642R4 ...), or "all".',
    )
    p.add_argument(
        "--refetch",
        action="store_true",
        help="Re-eval even if a complete evaluation already exists.",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=5,
        metavar="N",
        help="Number of concurrent eval workers (default: 5).",
    )
    p.add_argument(
        "--discovery-passes",
        type=int,
        default=3,
        metavar="N",
        help="Number of LLM discovery passes per paper (default: 3).",
    )
    return p


def command(args: argparse.Namespace, backend: StorageBackend) -> int:
    from paperlint.jobs import run_eval
    result = asyncio.run(run_eval(
        args.targets,
        backend,
        refetch=args.refetch,
        concurrency=args.concurrency,
        discovery_passes=args.discovery_passes,
    ))

    succeeded = result.get("succeeded", [])
    skipped = result.get("skipped", [])
    failed = result.get("failed", [])

    print(f"Eval: {len(succeeded)} complete, {len(skipped)} skipped, {len(failed)} failed.")
    if failed:
        for item in failed:
            print(f"  ERROR {item['paper_id']}: {item['error']}", file=sys.stderr)
        return 1
    return 0
