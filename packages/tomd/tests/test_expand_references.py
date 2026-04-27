#
# Copyright (c) 2026 Greg Kaleka (greg@gregkaleka.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Tests for ``tomd.__main__.expand_references``: year positional expansion."""

from __future__ import annotations

import pytest

from paperstore.errors import MissingMailingIndexError
from paperstore.testing import store  # noqa: F401  (pytest fixture)
from tomd.__main__ import expand_references


def _seed(store, year, paper_ids):
    store.upsert_year(
        year,
        [{"paper_id": pid, "url": f"https://x/{pid.lower()}.pdf"} for pid in paper_ids],
    )


def test_expand_paper_id_passthrough_uppercase(store):
    out = expand_references(["p3642r4", "P3700R0"], store)
    assert out == ["P3642R4", "P3700R0"]


def test_expand_year_emits_all_paper_ids(store):
    _seed(store, "2026", ["P1000R0", "P1001R0", "P1002R0"])
    out = expand_references(["2026"], store)
    assert set(out) == {"P1000R0", "P1001R0", "P1002R0"}


def test_expand_mixed_inputs_preserve_order(store):
    _seed(store, "2026", ["P1000R0", "P1001R0"])
    out = expand_references(["P3642R4", "2026", "P3700R0"], store)
    assert out[0] == "P3642R4"
    assert "P1000R0" in out
    assert "P1001R0" in out
    assert out[-1] == "P3700R0"


def test_expand_unknown_year_raises(store):
    with pytest.raises(MissingMailingIndexError):
        expand_references(["9999"], store)
