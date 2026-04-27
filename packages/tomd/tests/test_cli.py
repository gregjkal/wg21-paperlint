"""Smoke tests for the tomd CLI entry point.

The new CLI takes a paper id and a paperstore workspace; the old file-path
interface (``tomd input.pdf``) was removed in the 0.2 restructure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from paperstore import SqliteBackend


_SAMPLE_MD = """\
---
title: "Sample"
document: P1234R0
date: 2026-04-01
audience: LEWG
reply-to:
  - "Author <author@example.com>"
---

## 1 Introduction

Body text.

```cpp
void foo() { return; }
```

- bullet one
- bullet two
"""


def test_tomd_help_succeeds():
    result = subprocess.run(
        [sys.executable, "-m", "tomd", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "paper" in result.stdout.lower()


def test_tomd_missing_source_errors(tmp_path: Path):
    store = SqliteBackend(tmp_path)
    store.upsert_year("2026", [{"paper_id": "P1", "title": "T"}])
    result = subprocess.run(
        [sys.executable, "-m", "tomd", "P1", "--workspace-dir", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "source" in result.stderr.lower()


def test_tomd_qa_scores_pre_converted_md(tmp_path: Path):
    """`tomd <mailing> --qa` must score paper.md files without reconverting.

    Regression test: an earlier refactor routed .md paths through the PDF
    pipeline (fitz.open), which crashed on markdown input.
    """
    store = SqliteBackend(tmp_path)
    store.upsert_year("2026", [{"paper_id": "P1234R0", "title": "Sample"}])
    store.write_paper_md("P1234R0", _SAMPLE_MD)

    qa_json = tmp_path / "qa.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "tomd", "2026",
            "--qa", "--qa-json", str(qa_json),
            "--workspace-dir", str(tmp_path),
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert qa_json.exists()
    payload = json.loads(qa_json.read_text())
    assert len(payload) == 1
    assert payload[0]["score"] > 0
    assert "pipeline error" not in " ".join(payload[0].get("issues", []))
