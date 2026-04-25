#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Tests for ``paperstore.default_workspace_dir``."""

from __future__ import annotations

from pathlib import Path

import pytest

from paperstore import WORKSPACE_ENV_VAR, default_workspace_dir


def test_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WORKSPACE_ENV_VAR, raising=False)
    assert default_workspace_dir() == Path("./data")


def test_env_var_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(WORKSPACE_ENV_VAR, str(tmp_path))
    assert default_workspace_dir() == tmp_path


def test_empty_env_var_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WORKSPACE_ENV_VAR, "   ")
    assert default_workspace_dir() == Path("./data")
