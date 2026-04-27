#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Tests for ``tomd.api.convert_paper`` and the YAML-fallback helpers.

Named ``test_paper_extract`` to avoid collision with ``tomd/tests/test_extract.py``
(which covers spatial PDF extraction).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from paperstore import JsonBackend, MissingMetaError, MissingSourceError
from tomd import api


def _stage(store: JsonBackend, paper_id: str, *, suffix: str, mailing_row: dict) -> None:
    """Populate paperstore with a minimal source file + mailing-index row."""
    store.put_source(paper_id, b"ignored-by-monkeypatched-converter", suffix=suffix)
    row = {"paper_id": paper_id.lower(), **mailing_row}
    store.upsert_mailing_index("2026-02", [row])


def _patch_html(monkeypatch, md: str, prompts: list[str] | None = None):
    monkeypatch.setattr(api, "convert_html", lambda _p: (md, prompts))


def _patch_pdf(monkeypatch, md: str, prompts: list[str] | None = None):
    monkeypatch.setattr(api, "convert_pdf", lambda _p: (md, prompts))


def _convert_and_read(store: JsonBackend, paper_id: str) -> str:
    md_path = api.convert_paper(paper_id, store)
    return md_path.read_text(encoding="utf-8")


class TestDispatch:
    def test_html_path_calls_convert_html(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(store, "P1", suffix=".html", mailing_row={"title": "T"})
        _patch_html(monkeypatch, "# Body\n\ntext\n")
        _patch_pdf(monkeypatch, "PDF SHOULD NOT BE CALLED")
        md = _convert_and_read(store, "P1")
        assert "PDF SHOULD NOT BE CALLED" not in md
        assert "text" in md
        assert store.get_paper_md("P1") == md

    def test_pdf_path_calls_convert_pdf(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(store, "P1", suffix=".pdf", mailing_row={"title": "T"})
        _patch_html(monkeypatch, "HTML SHOULD NOT BE CALLED")
        _patch_pdf(monkeypatch, "# Body\n\ntext\n")
        md = _convert_and_read(store, "P1")
        assert "HTML SHOULD NOT BE CALLED" not in md
        assert "text" in md


class TestEmptyMarkdownRaises:
    def test_empty_string_raises(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(store, "P1", suffix=".pdf", mailing_row={"title": "T"})
        _patch_pdf(monkeypatch, "", ["slide-deck detected"])
        with pytest.raises(RuntimeError, match="empty markdown"):
            api.convert_paper("P1", store)

    def test_whitespace_only_raises(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(store, "P1", suffix=".pdf", mailing_row={"title": "T"})
        _patch_pdf(monkeypatch, "   \n\n\t\n")
        with pytest.raises(RuntimeError):
            api.convert_paper("P1", store)


class TestStripTocSafetyNet:
    def test_short_toc_block_is_stripped(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(store, "P1", suffix=".html", mailing_row={"title": "T"})
        body = (
            "# Paper\n\n"
            "## Contents\n"
            "1. Intro .... 1\n"
            "2. Body .... 2\n\n"
            "## Real Section\n\nText.\n"
        )
        _patch_html(monkeypatch, body)
        md = _convert_and_read(store, "P1")
        assert "Real Section" in md
        assert "1. Intro" not in md


class TestMetadataFallback:
    def test_no_front_matter_inserts_block(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(
            store, "P3642R4", suffix=".html",
            mailing_row={
                "title": "Carry-less product",
                "subgroup": "LEWG",
                "authors": ["Alice <a@x>", "Bob <b@x>"],
                "document_date": "2026-02-15",
                "paper_type": "proposal",
            },
        )
        _patch_html(monkeypatch, "Body only.\n")
        md = _convert_and_read(store, "P3642R4")
        assert md.startswith("---\n")
        assert "title:" in md
        assert "Carry-less product" in md
        assert "document: p3642r4" in md
        assert "audience: LEWG" in md
        assert "reply-to:" in md
        assert "paper-type: proposal" in md
        assert "Body only." in md

    def test_existing_field_wins_over_fallback(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(
            store, "P1", suffix=".html",
            mailing_row={"title": "Mailing Title", "subgroup": "LWG"},
        )
        body = (
            "---\n"
            'title: "Source Title"\n'
            "---\n\n"
            "Body.\n"
        )
        _patch_html(monkeypatch, body)
        md = _convert_and_read(store, "P1")
        assert '"Source Title"' in md
        assert "Mailing Title" not in md
        assert "audience: LWG" in md

    def test_empty_meta_value_skipped(self, tmp_path: Path, monkeypatch):
        store = JsonBackend(tmp_path)
        _stage(
            store, "P1", suffix=".html",
            mailing_row={"title": "T", "subgroup": "", "authors": []},
        )
        _patch_html(monkeypatch, "Body.\n")
        md = _convert_and_read(store, "P1")
        assert "title: T" in md
        assert "audience:" not in md
        assert "reply-to:" not in md


class TestErrors:
    def test_missing_source_raises(self, tmp_path: Path):
        store = JsonBackend(tmp_path)
        store.upsert_mailing_index(
            "2026-02", [{"paper_id": "p1", "title": "T"}]
        )
        with pytest.raises(MissingSourceError):
            api.convert_paper("P1", store)

    def test_missing_meta_raises(self, tmp_path: Path):
        store = JsonBackend(tmp_path)
        store.put_source("P1", b"x", suffix=".pdf")
        with pytest.raises(MissingMetaError):
            api.convert_paper("P1", store)
