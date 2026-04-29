#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#

"""Unit coverage for ``run_convert(..., write_prompts=...)``.

The flag's job is to gate the persistence of ``<pid>.prompts.json`` even
when the converter produced a non-empty prompt list. The QA smoke test
covers the read side; this test exercises the write-side gate so the
``--no-prompts`` CLI flag has a safety net independent of whether the
sample paper happens to have uncertain regions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from paperlint import jobs
from paperlint.models import ConvertResult
from paperstore import SqliteBackend


def _seed_paper_with_source(store: SqliteBackend, tmp_path: Path) -> str:
    pid = "P1234R0"
    store.upsert_year("2026", [{"paper_id": pid, "title": "Sample"}])
    src = tmp_path / "p1234r0.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    store.record_source(pid, src)
    return pid


def _stub_convert(_paper):
    return ConvertResult(
        paper_id="P1234R0",
        markdown="# Sample\n\nbody.\n",
        prompts=["paste me into an LLM verbatim"],
        intent="",
        title="Sample",
        status="ok",
    )


@pytest.mark.parametrize(
    "write_prompts,expect_prompts_file",
    [(True, True), (False, False)],
)
def test_run_convert_write_prompts_gate(
    tmp_path: Path, monkeypatch, write_prompts: bool, expect_prompts_file: bool
):
    monkeypatch.setattr(
        "paperlint.orchestrator.convert_one_paper", _stub_convert
    )

    store = SqliteBackend(tmp_path)
    pid = _seed_paper_with_source(store, tmp_path)

    asyncio.run(jobs.run_convert(
        [pid], store, force=True, concurrency=1, write_prompts=write_prompts,
    ))

    prompts_path = tmp_path / f"{pid.lower()}.prompts.json"
    assert prompts_path.exists() is expect_prompts_file
