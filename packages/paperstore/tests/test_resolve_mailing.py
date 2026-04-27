#
# Copyright (c) 2026 C++ Alliance (vinnie.falco@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0.
#

"""Tests for JsonBackend.resolve_mailing_for_paper."""

from __future__ import annotations

import json
from pathlib import Path

from paperstore import JsonBackend


def _make_mailing(tmp_path: Path, mailing_id: str, papers: list[dict]) -> None:
    mailings_dir = tmp_path / "mailings"
    mailings_dir.mkdir(exist_ok=True)
    (mailings_dir / f"{mailing_id}.json").write_text(
        json.dumps(papers), encoding="utf-8"
    )


def test_resolve_hit(tmp_path: Path):
    _make_mailing(tmp_path, "2026-04", [
        {"paper_id": "p3000r5", "url": "https://example.com/p3000r5.pdf", "title": "Contracts"},
        {"paper_id": "p3100r1", "url": "https://example.com/p3100r1.html", "title": "Reflection"},
    ])
    backend = JsonBackend(tmp_path)
    result = backend.resolve_mailing_for_paper("P3000R5")
    assert result is not None
    mailing_id, row = result
    assert mailing_id == "2026-04"
    assert row["paper_id"] == "p3000r5"
    assert row["url"] == "https://example.com/p3000r5.pdf"


def test_resolve_case_insensitive(tmp_path: Path):
    _make_mailing(tmp_path, "2026-02", [
        {"paper_id": "p2900r14", "url": "https://example.com/p2900r14.pdf"},
    ])
    backend = JsonBackend(tmp_path)
    assert backend.resolve_mailing_for_paper("p2900r14") is not None
    assert backend.resolve_mailing_for_paper("P2900R14") is not None
    assert backend.resolve_mailing_for_paper("P2900r14") is not None


def test_resolve_miss(tmp_path: Path):
    _make_mailing(tmp_path, "2026-04", [
        {"paper_id": "p3000r5", "url": "https://example.com/p3000r5.pdf"},
    ])
    backend = JsonBackend(tmp_path)
    assert backend.resolve_mailing_for_paper("P9999R0") is None


def test_resolve_no_mailings_dir(tmp_path: Path):
    backend = JsonBackend(tmp_path)
    assert backend.resolve_mailing_for_paper("P3000R5") is None


def test_resolve_multiple_mailings(tmp_path: Path):
    _make_mailing(tmp_path, "2026-02", [
        {"paper_id": "p2900r14", "url": "https://example.com/p2900r14.pdf"},
    ])
    _make_mailing(tmp_path, "2026-04", [
        {"paper_id": "p3000r5", "url": "https://example.com/p3000r5.pdf"},
    ])
    backend = JsonBackend(tmp_path)

    mid1, row1 = backend.resolve_mailing_for_paper("P2900R14")
    assert mid1 == "2026-02"

    mid2, row2 = backend.resolve_mailing_for_paper("P3000R5")
    assert mid2 == "2026-04"
