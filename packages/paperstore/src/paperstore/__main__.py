#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Paperstore CLI: inspect what's stored under a workspace.

Read-only. Useful during development to confirm what mailing, tomd, and
paperlint have written. No network calls, no writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paperstore import JsonBackend
from paperstore.errors import MissingMailingIndexError, MissingMetaError


def _cmd_list_mailings(backend: JsonBackend) -> int:
    mailings_dir = backend.workspace_dir / "mailings"
    if not mailings_dir.is_dir():
        print(f"No mailings directory under {backend.workspace_dir}", file=sys.stderr)
        return 1
    for p in sorted(mailings_dir.glob("*.json")):
        rows = json.loads(p.read_text(encoding="utf-8"))
        print(f"{p.stem}\t{len(rows)} papers")
    return 0


def _cmd_show_mailing(backend: JsonBackend, mailing_id: str) -> int:
    try:
        rows = backend.list_mailing(mailing_id)
    except MissingMailingIndexError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    for row in rows:
        pid = row.get("paper_id", "?")
        title = row.get("title", "")
        print(f"{pid}\t{title}")
    return 0


def _cmd_ls_papers(backend: JsonBackend, mailing_id: str | None) -> int:
    if mailing_id:
        try:
            rows = backend.list_mailing(mailing_id)
        except MissingMailingIndexError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        ids = [row["paper_id"].upper() for row in rows]
    else:
        ids = [
            p.name
            for p in sorted(backend.workspace_dir.iterdir())
            if p.is_dir() and p.name != "mailings"
        ]
    for pid in ids:
        pdir = backend.workspace_dir / pid
        have_src = any(pdir.glob("source.*"))
        have_md = (pdir / "paper.md").is_file()
        have_eval = (pdir / "evaluation.json").is_file()
        marks = "".join(
            m for m, present in [("s", have_src), ("m", have_md), ("e", have_eval)] if present
        ) or "-"
        print(f"{pid}\t{marks}")
    return 0


def _cmd_show_paper(backend: JsonBackend, paper_id: str) -> int:
    try:
        meta = backend.get_meta(paper_id)
    except MissingMetaError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="paperstore",
        description="Inspect paperflow artifacts in a workspace directory.",
    )
    parser.add_argument(
        "--workspace-dir",
        required=True,
        metavar="DIR",
        type=Path,
        help="Paperstore JSON backend root.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-mailings", help="List stored mailing ids with paper counts.")

    show_m = sub.add_parser("show-mailing", help="List paper ids + titles in a mailing.")
    show_m.add_argument("mailing_id")

    ls = sub.add_parser(
        "ls-papers",
        help="List staged papers. Marks: s=source, m=paper.md, e=evaluation.json.",
    )
    ls.add_argument("mailing_id", nargs="?", default=None)

    show_p = sub.add_parser("show-paper", help="Print a paper's metadata JSON.")
    show_p.add_argument("paper_id")

    args = parser.parse_args()
    backend = JsonBackend(args.workspace_dir)

    if args.command == "list-mailings":
        return _cmd_list_mailings(backend)
    if args.command == "show-mailing":
        return _cmd_show_mailing(backend, args.mailing_id)
    if args.command == "ls-papers":
        return _cmd_ls_papers(backend, args.mailing_id)
    if args.command == "show-paper":
        return _cmd_show_paper(backend, args.paper_id)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
