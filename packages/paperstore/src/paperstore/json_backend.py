#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Filesystem-backed JSON storage for paperflow artifacts.

On-disk layout rooted at ``workspace_dir`` (flat, one file per artifact)::

    <workspace_dir>/
        mailings/<mailing-id>.json
        <pid>.pdf | <pid>.html | <pid>.htm   # mailing.download
        <pid>.md                              # tomd
        <pid>.prompts.json                    # tomd, only when uncertain regions
        <pid>.meta.json                       # paperlint convert
        <pid>.1-findings.json                 # paperlint eval, discovery
        <pid>.2-gate.json                     # paperlint eval, gate
        <pid>.2c-suppressed.json              # paperlint eval, suppression
        <pid>.eval.json                       # paperlint eval, final

Paper ids are lowercase on disk; the API normalizes any case at the boundary.
JSON is intentionally the only backend for now: artifacts stay inspectable
while conversion quality is still being iterated on.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paperstore.backend import StorageBackend
from paperstore.errors import (
    MissingEvaluationError,
    MissingMailingIndexError,
    MissingMetaError,
    MissingPaperMdError,
    MissingSourceError,
)

_SOURCE_SUFFIXES = (".pdf", ".html", ".htm")
_MAILINGS_DIR = "mailings"


class JsonBackend(StorageBackend):
    """Filesystem-backed JSON storage rooted at ``workspace_dir``."""

    def __init__(self, workspace_dir: Path | str) -> None:
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    # ---- internals ------------------------------------------------------

    def _paper_file(self, paper_id: str, suffix: str) -> Path:
        """Return the flat artifact path for a paper.

        ``suffix`` is the artifact suffix without a leading dot, e.g.
        ``"pdf"``, ``"md"``, ``"meta.json"``, ``"eval.json"``,
        ``"1-findings.json"``.
        """
        return self.workspace_dir / f"{paper_id.lower()}.{suffix}"

    def _mailings_dir(self) -> Path:
        d = self.workspace_dir / _MAILINGS_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def mailing_index_path(self, mailing_id: str) -> Path:
        """Public accessor used by tests and debugging tools."""
        return self.workspace_dir / _MAILINGS_DIR / f"{mailing_id}.json"

    # ---- writes ---------------------------------------------------------

    def write_paper_md(self, paper_id: str, markdown: str) -> Path:
        path = self._paper_file(paper_id, "md")
        path.write_text(markdown, encoding="utf-8")
        return path

    def write_meta_json(self, paper_id: str, meta: dict) -> Path:
        path = self._paper_file(paper_id, "meta.json")
        path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def write_evaluation_json(self, paper_id: str, evaluation: dict) -> Path:
        path = self._paper_file(paper_id, "eval.json")
        path.write_text(
            json.dumps(evaluation, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def write_intermediate(
        self, paper_id: str, name: str, payload: Any
    ) -> Path:
        path = self._paper_file(paper_id, f"{name}.json")
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def upsert_mailing_index(
        self, mailing_id: str, papers: list[dict]
    ) -> list[dict]:
        index_dir = self._mailings_dir()
        index_path = index_dir / f"{mailing_id}.json"

        existing_by_id: dict[str, dict] = {}
        if index_path.exists():
            for entry in json.loads(index_path.read_text(encoding="utf-8")):
                existing_by_id[entry["paper_id"]] = entry

        now = datetime.now(timezone.utc).isoformat()
        merged: list[dict] = []
        new_count = 0
        for p in papers:
            pid = p["paper_id"]
            if pid in existing_by_id:
                merged.append(existing_by_id[pid])
            else:
                p = dict(p)
                p["added"] = now
                merged.append(p)
                new_count += 1
        merged.sort(key=lambda e: e["paper_id"])

        index_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"Mailing index: {index_path} ({len(merged)} papers, {new_count} new)"
        )
        return merged

    def put_source(
        self, paper_id: str, content: bytes, *, suffix: str
    ) -> Path:
        if not suffix.startswith("."):
            raise ValueError(f"suffix must start with '.', got {suffix!r}")
        bare = suffix[1:].lower()
        path = self._paper_file(paper_id, bare)
        if path.exists() and path.read_bytes() == content:
            return path
        path.write_bytes(content)
        return path

    # ---- reads ----------------------------------------------------------

    def get_meta(self, paper_id: str) -> dict:
        meta_path = self._paper_file(paper_id, "meta.json")
        if meta_path.is_file():
            return json.loads(meta_path.read_text(encoding="utf-8"))

        pid_upper = paper_id.upper()
        for index_file in self._mailings_dir().glob("*.json"):
            try:
                rows = json.loads(index_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for row in rows:
                if row.get("paper_id", "").upper() == pid_upper:
                    return row

        raise MissingMetaError(
            f"No meta.json and no mailing-index row for {pid_upper} under {self.workspace_dir}."
        )

    def get_source_path(self, paper_id: str) -> Path:
        stem = paper_id.lower()
        matches = [
            p for p in self.workspace_dir.glob(f"{stem}.*")
            if p.suffix.lower() in _SOURCE_SUFFIXES and p.is_file()
        ]
        if not matches:
            raise MissingSourceError(
                f"No {stem}.{{pdf,html,htm}} under {self.workspace_dir}. "
                f"Run mailing.download first."
            )
        if len(matches) > 1:
            names = sorted(p.name for p in matches)
            raise MissingSourceError(
                f"Multiple sources for {stem} under {self.workspace_dir}: {names}. "
                f"Expected exactly one."
            )
        return matches[0]

    def get_paper_md(self, paper_id: str) -> str:
        path = self._paper_file(paper_id, "md")
        if not path.is_file():
            raise MissingPaperMdError(
                f"No paper markdown at {path}. Run tomd.convert_paper first."
            )
        return path.read_text(encoding="utf-8")

    def get_evaluation(self, paper_id: str) -> dict:
        path = self._paper_file(paper_id, "eval.json")
        if not path.is_file():
            raise MissingEvaluationError(
                f"No evaluation at {path}. Run paperlint eval first."
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def list_mailing(self, mailing_id: str) -> list[dict]:
        path = self.mailing_index_path(mailing_id)
        if not path.is_file():
            raise MissingMailingIndexError(
                f"No mailing index at {path}. Run mailing.fetch_papers_for_mailing first."
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def resolve_mailing_for_paper(self, paper_id: str) -> tuple[str, dict] | None:
        pid_upper = paper_id.strip().upper()
        mailings_dir = self.workspace_dir / _MAILINGS_DIR
        if not mailings_dir.is_dir():
            return None
        for index_file in sorted(mailings_dir.glob("*.json")):
            try:
                rows = json.loads(index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for row in rows:
                if row.get("paper_id", "").upper() == pid_upper:
                    mailing_id = index_file.stem
                    return mailing_id, row
        return None

    def list_paper_ids(self) -> list[str]:
        ids: set[str] = set()
        for entry in self.workspace_dir.iterdir():
            if not entry.is_file():
                continue
            name = entry.name
            stem = name.split(".", 1)[0]
            if not stem:
                continue
            ids.add(stem.upper())
        return sorted(ids)
