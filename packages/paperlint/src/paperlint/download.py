#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#

"""CLI command module for 'paperflow download'."""

from __future__ import annotations

import argparse
import asyncio
import sys

from paperstore.backend import StorageBackend


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "download",
        help="Download paper source files (PDF/HTML)",
        description=(
            "Download source files for papers. Reads URLs from the local index. "
            "Idempotent: skips papers already staged unless --refetch is given."
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
        help="Re-download even if source is already staged.",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="HEAD-check staged files against Content-Length; re-download on mismatch.",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=10,
        metavar="N",
        help="Number of concurrent downloads (default: 10).",
    )
    return p


def command(args: argparse.Namespace, backend: StorageBackend) -> int:
    from paperlint.jobs import run_download
    result = asyncio.run(run_download(
        args.targets,
        backend,
        refetch=args.refetch,
        verify=args.verify,
        concurrency=args.concurrency,
    ))

    succeeded = result.get("succeeded", [])
    skipped = result.get("skipped", [])
    failed = result.get("failed", [])

    print(f"Download: {len(succeeded)} downloaded, {len(skipped)} skipped, {len(failed)} failed.")
    if failed:
        for item in failed:
            print(f"  ERROR {item['paper_id']}: {item['error']}", file=sys.stderr)
        return 1
    return 0
