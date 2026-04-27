#
# Copyright (c) 2026 C++ Alliance (vinnie.falco@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0.
#

"""Tests for _classify_arg in the paperflow CLI."""

from __future__ import annotations

import pytest

from paperlint.__main__ import _classify_arg


def test_year():
    assert _classify_arg("2026") == "year"
    assert _classify_arg("2025") == "year"
    assert _classify_arg("1995") == "year"


def test_mailing_id():
    assert _classify_arg("2026-04") == "mailing"
    assert _classify_arg("2025-12") == "mailing"


def test_eval_ref():
    assert _classify_arg("2026-04/P3000R5") == "eval_ref"
    assert _classify_arg("2025-02/P2900R14") == "eval_ref"


def test_bare_paper_id():
    assert _classify_arg("P3000R5") == "paper"
    assert _classify_arg("p3000r5") == "paper"
    assert _classify_arg("N4950") == "paper"
    assert _classify_arg("SD-6") == "paper"


def test_invalid_raises():
    with pytest.raises(ValueError, match="Unrecognized"):
        _classify_arg("123")
    with pytest.raises(ValueError, match="Unrecognized"):
        _classify_arg("2026-4")
    with pytest.raises(ValueError, match="Unrecognized"):
        _classify_arg("/P3000R5")
