#
# Copyright (c) 2026 Will Pak (will@cppalliance.org)
#
# Distributed under the Boost Software License, Version 1.0.
#

"""Tests for failed pipeline paths: structured failure fields in evaluation output."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from paperlint.models import PaperMeta
from paperlint.orchestrator import run_paper_eval
from paperstore import SqliteBackend


def _seed_converted(
    tmp_path: Path, paper_id: str, meta: PaperMeta, body: str = "paper body"
) -> SqliteBackend:
    """Seed a SqliteBackend so load_converted_paper can find the artifacts."""
    store = SqliteBackend(tmp_path)
    store.upsert_year("2026", [{"paper_id": paper_id, "title": meta.title}])
    # write_meta_json first (INSERT OR REPLACE), then write_paper_md to set markdown_path
    store.write_meta_json(paper_id, {
        "paper": paper_id,
        "title": meta.title,
        "authors": meta.authors,
        "target_group": meta.target_group,
        "source_file": meta.source_file,
        "run_timestamp": meta.run_timestamp,
        "model": meta.model,
        "intent": meta.intent,
        "year": "2026",
    })
    store.write_paper_md(paper_id, body)
    return store


def test_run_paper_eval_missing_artifacts_raises(tmp_path: Path) -> None:
    mailing = {
        "title": "T",
        "authors": ["A"],
        "subgroup": "G",
        "url": "",
    }
    with (
        patch("paperlint.orchestrator.ensure_api_keys"),
        patch("paperlint.orchestrator.build_client"),
        pytest.raises(FileNotFoundError),
    ):
        run_paper_eval(
            "N1234R0",
            workspace_dir=tmp_path,
            mailing_meta=mailing,
        )


def test_run_paper_eval_analysis_failure_writes_failure_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = PaperMeta(
        paper="N1234R0",
        title="Title",
        authors=["A"],
        target_group="LEWG",
        source_file="f",
        run_timestamp="2026-01-01T00:00:00+00:00",
        model="m",
    )
    store = _seed_converted(tmp_path, "N1234R0", meta)
    monkeypatch.delenv("PAPERLINT_ERROR_TRACEBACK", raising=False)
    with (
        patch("paperlint.orchestrator.step_discovery", side_effect=RuntimeError("LLM timeout")),
        patch("paperlint.orchestrator.ensure_api_keys"),
        patch("paperlint.orchestrator.build_client"),
    ):
        out = run_paper_eval(
            "N1234R0",
            storage=store,
            mailing_meta={"title": "T", "authors": ["A"], "subgroup": "G", "url": ""},
        )
    assert out.get("pipeline_status") == "partial"
    assert out.get("failure_stage") == "analysis"
    assert "timeout" in (out.get("failure_message") or "")


def test_run_paper_eval_includes_traceback_in_json_when_env_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = PaperMeta(
        paper="N1234R0",
        title="Title",
        authors=[],
        target_group="G",
        source_file="f",
        run_timestamp="2026-01-01T00:00:00+00:00",
        model="m",
    )
    store = _seed_converted(tmp_path, "N1234R0", meta)
    monkeypatch.setenv("PAPERLINT_ERROR_TRACEBACK", "1")
    with (
        patch("paperlint.orchestrator.step_discovery", side_effect=RuntimeError("e")),
        patch("paperlint.orchestrator.ensure_api_keys"),
        patch("paperlint.orchestrator.build_client"),
    ):
        out = run_paper_eval(
            "N1234R0",
            storage=store,
            mailing_meta={"title": "T", "authors": [], "subgroup": "G", "url": ""},
        )
    assert "failure_traceback" in out
    assert "RuntimeError" in out["failure_traceback"]
