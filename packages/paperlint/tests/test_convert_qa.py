#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#

"""Smoke tests for `paperflow convert --qa`.

Mirrors the regression coverage previously held by
``packages/tomd/tests/test_cli.py::test_tomd_qa_scores_pre_converted_md``:
QA must score pre-written paper.md files without re-routing them through
the PDF pipeline (an earlier refactor crashed by calling fitz.open on
markdown input).
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


def test_paperflow_convert_qa_scores_pre_converted_md(tmp_path: Path):
    store = SqliteBackend(tmp_path)
    store.upsert_year("2026", [{"paper_id": "P1234R0", "title": "Sample"}])
    store.write_paper_md("P1234R0", _SAMPLE_MD)

    qa_json = tmp_path / "qa.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "paperlint", "--workspace-dir", str(tmp_path),
            "convert", "2026", "--qa", "--qa-json", str(qa_json),
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert qa_json.exists()
    payload = json.loads(qa_json.read_text())
    assert len(payload) == 1
    assert payload[0]["score"] > 0
    assert "pipeline error" not in " ".join(payload[0].get("issues", []))


def test_paperflow_convert_qa_skips_papers_without_md(tmp_path: Path):
    store = SqliteBackend(tmp_path)
    store.upsert_year("2026", [{"paper_id": "P9999R0", "title": "No Markdown"}])

    result = subprocess.run(
        [
            sys.executable, "-m", "paperlint", "--workspace-dir", str(tmp_path),
            "convert", "2026", "--qa",
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "no paper markdown" in result.stderr.lower()
