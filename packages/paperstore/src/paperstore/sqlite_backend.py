#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""SQLite-backed storage implementation.

All metadata lives in ``papers.db`` (three tables: ``papers``, ``years``,
``evals``). Source files, markdown, and eval JSON remain on disk; the DB
stores paths to them.

Designed for single-threaded access from the main coroutine in ``jobs.py``.
No WAL or connection pool is needed because workers never touch the DB.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id      TEXT PRIMARY KEY,
    year          TEXT DEFAULT '',
    title         TEXT DEFAULT '',
    authors       TEXT DEFAULT '',
    target_group  TEXT DEFAULT '',
    intent        TEXT DEFAULT '',
    url           TEXT DEFAULT '',
    document_date TEXT DEFAULT '',
    mailing_date  TEXT DEFAULT '',
    source_file   TEXT DEFAULT '',
    markdown_path TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS years (
    year   TEXT PRIMARY KEY,
    added  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS evals (
    paper_id            TEXT PRIMARY KEY REFERENCES papers(paper_id),
    pipeline_status     TEXT DEFAULT '',
    eval_timestamp      TEXT DEFAULT '',
    model               TEXT DEFAULT '',
    findings_discovered INTEGER,
    findings_passed     INTEGER,
    findings_rejected   INTEGER,
    summary             TEXT DEFAULT '',
    generated           TEXT DEFAULT '',
    eval_json_path      TEXT DEFAULT ''
);
"""


def _atomic_replace(src: Path, dst: Path) -> None:
    """Rename ``src`` to ``dst``, retrying on PermissionError (Windows AV/EDR)."""
    for _ in range(10):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            time.sleep(0.1)
    os.replace(src, dst)


class SqliteBackend(StorageBackend):
    """Filesystem-backed paperstore using a SQLite database for metadata.

    Constructor creates ``workspace_dir`` and ``papers.db`` on first use.
    All read/write methods are synchronous and not thread-safe; call only
    from the main event-loop coroutine.
    """

    def __init__(self, workspace_dir: Path) -> None:
        self._workspace = Path(workspace_dir)
        self._workspace.mkdir(parents=True, exist_ok=True)
        db_path = self._workspace / "papers.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def workspace_dir(self) -> Path:
        return self._workspace

    # ---- internal helpers -------------------------------------------------

    def _patch_fields(self, paper_id: str, fields: dict) -> None:
        """Update specific columns on the papers row for ``paper_id``."""
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [paper_id.upper()]
        self._conn.execute(f"UPDATE papers SET {cols} WHERE paper_id = ?", vals)
        self._conn.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        # Decode JSON-encoded authors back to a list.
        raw = d.get("authors", "")
        if raw and raw.startswith("["):
            try:
                d["authors"] = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                d["authors"] = [a.strip() for a in raw.split(",") if a.strip()]
        else:
            d["authors"] = [a.strip() for a in raw.split(",") if a.strip()] if raw else []
        return d

    # ---- year-based mailing index -----------------------------------------

    def has_year(self, year: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM papers WHERE year = ? LIMIT 1", (year,)
        ).fetchone()
        return row is not None

    def upsert_year(self, year: str, papers: list[dict]) -> list[dict]:
        """Insert or update all papers for year. Returns merged list."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO years (year, added) VALUES (?, ?)",
            (year, now),
        )
        for p in papers:
            pid = (p.get("paper_id") or "").strip().upper()
            if not pid:
                continue
            authors_raw = p.get("authors") or []
            if isinstance(authors_raw, list):
                authors_json = json.dumps(authors_raw)
            else:
                authors_json = str(authors_raw)
            # INSERT OR IGNORE keeps existing source_file/markdown_path on updates.
            self._conn.execute(
                """
                INSERT OR IGNORE INTO papers
                    (paper_id, year, title, authors, target_group, intent,
                     url, document_date, mailing_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    year,
                    p.get("title") or "",
                    authors_json,
                    p.get("subgroup") or "",
                    p.get("intent") or "",
                    p.get("url") or "",
                    p.get("document_date") or "",
                    p.get("mailing_date") or "",
                ),
            )
            # Update non-completion fields without clobbering source_file/markdown_path.
            self._conn.execute(
                """
                UPDATE papers SET
                    year = ?, title = ?, authors = ?, target_group = ?,
                    intent = CASE WHEN intent = '' THEN ? ELSE intent END,
                    url = ?, document_date = ?, mailing_date = ?
                WHERE paper_id = ?
                """,
                (
                    year,
                    p.get("title") or "",
                    authors_json,
                    p.get("subgroup") or "",
                    p.get("intent") or "",
                    p.get("url") or "",
                    p.get("document_date") or "",
                    p.get("mailing_date") or "",
                    pid,
                ),
            )
        self._conn.commit()
        return self.list_papers_for_year(year)

    def list_papers_for_year(self, year: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM papers WHERE year = ?", (year,)
        ).fetchall()
        if not rows:
            raise MissingMailingIndexError(
                f"No papers found for year {year!r}. "
                f"Run 'paperflow mailing {year}' first."
            )
        return [self._row_to_dict(r) for r in rows]

    def list_all_paper_ids(self) -> list[str]:
        rows = self._conn.execute("SELECT paper_id FROM papers").fetchall()
        return [r["paper_id"] for r in rows]

    def resolve_year_for_paper(self, paper_id: str) -> tuple[str, dict] | None:
        row = self._conn.execute(
            "SELECT * FROM papers WHERE paper_id = ?", (paper_id.strip().upper(),)
        ).fetchone()
        if row is None:
            return None
        d = self._row_to_dict(row)
        return d["year"], d

    # ---- writes -----------------------------------------------------------

    def put_source(self, paper_id: str, content: bytes, *, suffix: str) -> Path:
        """Write source bytes atomically and record the path in the DB."""
        pid = paper_id.strip().upper()
        final_path = self._workspace / f"{pid.lower()}{suffix}"
        temp_path = final_path.with_stem(final_path.stem + ".tmp")
        if temp_path.exists():
            temp_path.unlink()
        temp_path.write_bytes(content)
        _atomic_replace(temp_path, final_path)
        # Ensure row exists before patching.
        self._conn.execute(
            "INSERT OR IGNORE INTO papers (paper_id) VALUES (?)", (pid,)
        )
        self._conn.commit()
        self._patch_fields(pid, {"source_file": str(final_path)})
        return final_path

    def write_paper_md(self, paper_id: str, markdown: str) -> Path:
        """Write markdown atomically and record the path in the DB."""
        pid = paper_id.strip().upper()
        final_path = self._workspace / f"{pid.lower()}.md"
        temp_path = final_path.with_stem(final_path.stem + ".tmp")
        if temp_path.exists():
            temp_path.unlink()
        temp_path.write_text(markdown, encoding="utf-8")
        _atomic_replace(temp_path, final_path)
        self._conn.execute(
            "INSERT OR IGNORE INTO papers (paper_id) VALUES (?)", (pid,)
        )
        self._conn.commit()
        self._patch_fields(pid, {"markdown_path": str(final_path)})
        return final_path

    def write_meta_json(self, paper_id: str, meta: dict) -> Path:
        """Upsert paper metadata into the papers table."""
        pid = paper_id.strip().upper()
        authors = meta.get("authors") or []
        if isinstance(authors, list):
            authors_json = json.dumps(authors)
        else:
            authors_json = str(authors)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO papers
                (paper_id, year, title, authors, target_group, intent,
                 url, document_date, mailing_date, source_file, markdown_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                meta.get("year") or "",
                meta.get("title") or "",
                authors_json,
                meta.get("target_group") or "",
                meta.get("intent") or "",
                meta.get("url") or "",
                meta.get("document_date") or "",
                meta.get("mailing_date") or "",
                meta.get("source_file") or "",
                meta.get("markdown_path") or "",
            ),
        )
        self._conn.commit()
        return self._workspace / f"{pid.lower()}.meta.json"  # compat path

    def write_evaluation_json(self, paper_id: str, evaluation: dict) -> Path:
        """Write eval JSON to disk and upsert summary into evals table."""
        pid = paper_id.strip().upper()
        final_path = self._workspace / f"{pid.lower()}.eval.json"
        temp_path = final_path.with_stem(final_path.stem + ".tmp")
        if temp_path.exists():
            temp_path.unlink()
        temp_path.write_text(
            json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _atomic_replace(temp_path, final_path)

        self._conn.execute(
            """
            INSERT OR REPLACE INTO evals
                (paper_id, pipeline_status, eval_timestamp, model,
                 findings_discovered, findings_passed, findings_rejected,
                 summary, generated, eval_json_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                evaluation.get("pipeline_status") or "",
                evaluation.get("generated") or "",
                evaluation.get("model") or "",
                evaluation.get("findings_discovered"),
                evaluation.get("findings_passed"),
                evaluation.get("findings_rejected"),
                evaluation.get("summary") or "",
                evaluation.get("generated") or "",
                str(final_path),
            ),
        )
        self._conn.commit()
        return final_path

    def write_intermediate(self, paper_id: str, name: str, payload: Any) -> Path:
        """Write an intermediate artifact JSON to disk."""
        pid = paper_id.strip().upper()
        path = self._workspace / f"{pid.lower()}.{name}.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path

    # ---- reads ------------------------------------------------------------

    def get_meta(self, paper_id: str) -> dict:
        row = self._conn.execute(
            "SELECT * FROM papers WHERE paper_id = ?",
            (paper_id.strip().upper(),),
        ).fetchone()
        if row is None:
            raise MissingMetaError(
                f"No metadata for {paper_id!r}. "
                f"Run 'paperflow mailing' then 'paperflow download' first."
            )
        return self._row_to_dict(row)

    def get_source_path(self, paper_id: str) -> Path:
        row = self._conn.execute(
            "SELECT source_file FROM papers WHERE paper_id = ?",
            (paper_id.strip().upper(),),
        ).fetchone()
        if row is None or not row["source_file"]:
            raise MissingSourceError(
                f"No staged source for {paper_id!r}. "
                f"Run 'paperflow download {paper_id}' first."
            )
        return Path(row["source_file"])

    def get_paper_md(self, paper_id: str) -> str:
        row = self._conn.execute(
            "SELECT markdown_path FROM papers WHERE paper_id = ?",
            (paper_id.strip().upper(),),
        ).fetchone()
        if row is None or not row["markdown_path"]:
            raise MissingPaperMdError(
                f"No converted markdown for {paper_id!r}. "
                f"Run 'paperflow convert {paper_id}' first."
            )
        path = Path(row["markdown_path"])
        if not path.exists():
            raise MissingPaperMdError(
                f"Markdown file missing for {paper_id!r}: {path}. "
                f"Run 'paperflow convert {paper_id}' again."
            )
        return path.read_text(encoding="utf-8")

    def get_evaluation(self, paper_id: str) -> dict:
        row = self._conn.execute(
            "SELECT eval_json_path FROM evals WHERE paper_id = ?",
            (paper_id.strip().upper(),),
        ).fetchone()
        if row is None or not row["eval_json_path"]:
            raise MissingEvaluationError(
                f"No evaluation for {paper_id!r}. "
                f"Run 'paperflow eval {paper_id}' first."
            )
        path = Path(row["eval_json_path"])
        if not path.exists():
            raise MissingEvaluationError(
                f"Evaluation file missing for {paper_id!r}: {path}."
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def list_years(self) -> list[tuple[str, int]]:
        """Return ``[(year, paper_count)]`` sorted by year."""
        rows = self._conn.execute(
            "SELECT year, COUNT(*) AS n FROM papers GROUP BY year ORDER BY year"
        ).fetchall()
        return [(r["year"], r["n"]) for r in rows]
