"""Tests for the index-authoritative metadata contract.

Covers:
- _classify_arg: argument type detection for the paperflow CLI.
- _infer_paper_type: the deterministic paper_type rules derived from the mailing index.

These are pure-function tests; no network, no LLM, no filesystem.
"""

import pytest

from paperlint.__main__ import _classify_arg, _EVAL_REF_RE
from mailing.scrape import _infer_paper_type


class TestClassifyArg:
    def test_eval_ref_canonical(self):
        assert _classify_arg("2026-02/P3642R4") == "eval_ref"
        m = _EVAL_REF_RE.match("2026-02/P3642R4")
        assert m.group("mailing") == "2026-02"
        assert m.group("paper") == "P3642R4"

    def test_eval_ref_lowercase(self):
        m = _EVAL_REF_RE.match("2026-02/p3642r4")
        assert m.group("paper") == "p3642r4"

    def test_eval_ref_n_paper(self):
        assert _classify_arg("2026-02/N5035") == "eval_ref"

    def test_eval_ref_sd_paper(self):
        assert _classify_arg("2026-02/SD-4") == "eval_ref"

    def test_bare_paper_id_accepted(self):
        assert _classify_arg("P3642R4") == "paper"

    def test_local_path_rejected(self):
        with pytest.raises(ValueError):
            _classify_arg("/tmp/paper.pdf")

    def test_relative_path_rejected(self):
        with pytest.raises(ValueError):
            _classify_arg("./some/paper.pdf")

    def test_year_slash_paper_not_eval_ref(self):
        with pytest.raises(ValueError):
            _classify_arg("26-02/P3642R4")


class TestInferPaperType:
    def test_info_prefix_wins(self):
        assert _infer_paper_type("Info: Some Informational Topic", "P3999R0") == "informational"

    def test_ask_prefix_maps_to_proposal(self):
        assert _infer_paper_type("Ask: Should we do X?", "P3999R0") == "proposal"

    def test_white_paper_pattern(self):
        t = "ISO/IEC JTC1/SC22/WG21 White Paper, Extensions to C++ for Transactional Memory"
        assert _infer_paper_type(t, "N5036") == "white-paper"

    def test_n_paper_default_informational(self):
        assert _infer_paper_type("2026-03 WG21 admin telecon meeting", "N5035") == "informational"

    def test_sd_default_standing_document(self):
        assert _infer_paper_type("WG21 Practices and Procedures", "SD-4") == "standing-document"

    def test_p_paper_default_proposal(self):
        assert _infer_paper_type("Carry-less product: std::clmul", "P3642R4") == "proposal"

    def test_unknown_prefix_defaults_proposal(self):
        # Silence is authoritative — default to proposal.
        assert _infer_paper_type("Some Title", "Q999") == "proposal"

    def test_case_insensitive_paper_id(self):
        assert _infer_paper_type("admin", "n5035") == "informational"
        assert _infer_paper_type("title", "p3642r4") == "proposal"

    def test_info_prefix_beats_paper_id_letter(self):
        # Hypothetical: P-paper marked informational in the index.
        assert _infer_paper_type("Info: Design update", "P3999R0") == "informational"

    def test_white_paper_beats_n_default(self):
        # N-paper with White Paper in title should be white-paper, not informational.
        assert _infer_paper_type("WG21 White Paper on foo", "N5999") == "white-paper"
