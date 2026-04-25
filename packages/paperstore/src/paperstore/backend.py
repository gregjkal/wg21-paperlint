#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Abstract storage interface for paperflow artifacts.

All reads and writes done by the mailing, tomd, and paperlint packages go
through a :class:`StorageBackend` instance. Only :class:`paperstore.JsonBackend`
is implemented today; the ABC exists so a future Postgres backend (or an
in-memory test double) can drop in without touching call sites.

Non-local backends must materialize bytes to a temp file inside
:meth:`StorageBackend.get_source_path` so callers can always treat the return
value as a local :class:`pathlib.Path`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class StorageBackend(ABC):
    # ---- writes (unchanged from the pre-paperstore storage.py) ----------

    @abstractmethod
    def write_paper_md(self, paper_id: str, markdown: str) -> Any:
        """Persist the converted markdown for a paper."""

    @abstractmethod
    def write_meta_json(self, paper_id: str, meta: dict) -> Any:
        """Persist per-paper metadata (mirrors ``PaperMeta.asdict()``)."""

    @abstractmethod
    def write_evaluation_json(self, paper_id: str, evaluation: dict) -> Any:
        """Persist the per-paper evaluation deliverable."""

    @abstractmethod
    def write_intermediate(self, paper_id: str, name: str, payload: Any) -> Any:
        """Persist a labeled intermediate artifact (e.g. ``1-findings``)."""

    @abstractmethod
    def upsert_mailing_index(
        self, mailing_id: str, papers: list[dict]
    ) -> list[dict]:
        """Idempotent merge. Preserves ``added`` timestamps on known papers."""

    @abstractmethod
    def put_source(
        self, paper_id: str, content: bytes, *, suffix: str
    ) -> Path:
        """Stage raw downloaded source bytes for ``paper_id``.

        ``suffix`` should start with a dot (``.pdf``, ``.html``). Returns a
        local filesystem path pointing at the stored bytes. Identical bytes
        are a no-op; differing bytes overwrite.
        """

    # ---- reads ----------------------------------------------------------

    @abstractmethod
    def get_meta(self, paper_id: str) -> dict:
        """Return per-paper metadata.

        Falls back to the row in the mailing index when a dedicated
        ``meta.json`` has not been written yet (tomd runs *after* mailing
        but *before* meta.json exists).

        Raises:
            paperstore.MissingMetaError: no meta row anywhere.
        """

    @abstractmethod
    def get_source_path(self, paper_id: str) -> Path:
        """Return a local path to the staged source file.

        Raises:
            paperstore.MissingSourceError: no source has been staged.
        """

    @abstractmethod
    def get_paper_md(self, paper_id: str) -> str:
        """Return the converted markdown as a string.

        Raises:
            paperstore.MissingPaperMdError: no markdown has been written.
        """

    @abstractmethod
    def list_mailing(self, mailing_id: str) -> list[dict]:
        """Return the persisted mailing index rows.

        Raises:
            paperstore.MissingMailingIndexError: the mailing has never been
                upserted into this store.
        """
