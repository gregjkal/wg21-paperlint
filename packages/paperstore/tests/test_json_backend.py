#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Tests for the JSON storage backend.

Covers the on-disk layout defined in :mod:`paperstore.json_backend` and the
idempotency contract for ``upsert_mailing_index``: re-running keeps each
existing entry (and its original ``added`` timestamp) and only appends new
papers.
"""

from __future__ import annotations

import json
from pathlib import Path

from paperstore import JsonBackend


def test_layout_paper_md_meta_eval_intermediate(tmp_path: Path):
    """Flat layout: one file per artifact, prefixed with the lowercase paper id."""
    backend = JsonBackend(tmp_path)

    backend.write_paper_md("P1234R0", "# Paper\n")
    backend.write_meta_json("P1234R0", {"title": "T"})
    backend.write_evaluation_json("P1234R0", {"summary": "S"})
    backend.write_intermediate("P1234R0", "1-findings", [{"n": 1}])

    assert (tmp_path / "p1234r0.md").read_text(encoding="utf-8") == "# Paper\n"
    assert json.loads((tmp_path / "p1234r0.meta.json").read_text())["title"] == "T"
    assert json.loads((tmp_path / "p1234r0.eval.json").read_text())["summary"] == "S"
    assert json.loads((tmp_path / "p1234r0.1-findings.json").read_text()) == [{"n": 1}]


def test_layout_accepts_any_case(tmp_path: Path):
    """Paper id is normalized to lowercase on disk regardless of input casing.

    Verified via the on-disk filename rather than path-existence checks
    (NTFS / HFS+ are case-insensitive, so existence alone cannot prove
    the canonical casing).
    """
    backend = JsonBackend(tmp_path)

    backend.write_paper_md("P1234R0", "# A\n")
    backend.write_paper_md("p1234r0", "# B\n")

    md_files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".md")
    assert md_files == ["p1234r0.md"]
    assert (tmp_path / "p1234r0.md").read_text(encoding="utf-8") == "# B\n"


def test_put_source_normalizes_suffix_and_writes_flat(tmp_path: Path):
    backend = JsonBackend(tmp_path)
    p = backend.put_source("P1234R0", b"%PDF-1.4\n", suffix=".PDF")
    assert p == tmp_path / "p1234r0.pdf"
    assert p.read_bytes() == b"%PDF-1.4\n"


def test_get_source_path_picks_unique_source(tmp_path: Path):
    backend = JsonBackend(tmp_path)
    backend.put_source("P1", b"x", suffix=".pdf")
    assert backend.get_source_path("P1") == tmp_path / "p1.pdf"


def test_list_paper_ids_returns_uppercase_set(tmp_path: Path):
    backend = JsonBackend(tmp_path)
    backend.put_source("P1234R0", b"%PDF\n", suffix=".pdf")
    backend.write_paper_md("N5000", "x")
    backend.write_evaluation_json("p9999r2", {"summary": ""})

    backend.upsert_mailing_index("2026-02", [{"paper_id": "P1234R0", "title": "T"}])

    assert backend.list_paper_ids() == ["N5000", "P1234R0", "P9999R2"]


def test_get_evaluation_round_trip_and_missing(tmp_path: Path):
    from paperstore.errors import MissingEvaluationError

    backend = JsonBackend(tmp_path)
    backend.write_evaluation_json("p1234r0", {"summary": "ok"})
    assert backend.get_evaluation("P1234R0") == {"summary": "ok"}

    try:
        backend.get_evaluation("p9999r9")
    except MissingEvaluationError:
        return
    raise AssertionError("expected MissingEvaluationError")


def test_upsert_mailing_index_is_idempotent(tmp_path: Path):
    """Re-scraping the same mailing twice produces the same output bytes
    (no duplicate paper rows, no shifted ``added`` timestamps)."""
    backend = JsonBackend(tmp_path)

    papers = [
        {"paper_id": "p1234r0", "title": "Foo"},
        {"paper_id": "n5000", "title": "Bar"},
    ]
    merged_v1 = backend.upsert_mailing_index("2026-02", papers)
    bytes_v1 = backend.mailing_index_path("2026-02").read_bytes()

    merged_v2 = backend.upsert_mailing_index("2026-02", papers)
    bytes_v2 = backend.mailing_index_path("2026-02").read_bytes()

    assert merged_v1 == merged_v2
    assert bytes_v1 == bytes_v2
    assert [p["paper_id"] for p in merged_v2] == ["n5000", "p1234r0"]


def test_upsert_mailing_index_preserves_added_for_known_papers(tmp_path: Path):
    """When upstream re-publishes with extra papers, prior entries keep their
    original payload + ``added`` timestamp; new papers get a fresh one."""
    backend = JsonBackend(tmp_path)

    merged_v1 = backend.upsert_mailing_index(
        "2026-02",
        [{"paper_id": "p1234r0", "title": "Foo"}],
    )
    added_orig = {p["paper_id"]: p["added"] for p in merged_v1}

    merged_v2 = backend.upsert_mailing_index(
        "2026-02",
        [
            {"paper_id": "p1234r0", "title": "Foo updated upstream"},
            {"paper_id": "p9999r0", "title": "New paper"},
        ],
    )
    by_id = {p["paper_id"]: p for p in merged_v2}
    assert set(by_id) == {"p1234r0", "p9999r0"}
    assert by_id["p1234r0"]["title"] == "Foo"
    assert by_id["p1234r0"]["added"] == added_orig["p1234r0"]
    assert "added" in by_id["p9999r0"]


def test_mailing_index_path_under_workspace_dir(tmp_path: Path):
    backend = JsonBackend(tmp_path)
    p = backend.mailing_index_path("2026-02")
    assert p == tmp_path / "mailings" / "2026-02.json"
