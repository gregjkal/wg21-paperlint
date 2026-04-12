# Paperlint — Pipeline Design

_Internal design reference for audit and review. This document describes how the pipeline works — it is not part of the public-facing product._

_Last updated April 12, 2026._

---

## Pipeline Overview

```
Paper (HTML or PDF, by number or path)
  │
  ▼
Step 0: METADATA
  Model: Sonnet 4.6 via OpenRouter (JSON mode)
  Input: clean text — extract_html() for HTML, extract_pdf() for PDF
  Output: JSON {title, authors, audience, paper_type, abstract}
  │
  ▼
Step 1: DISCOVERY
  Model: Opus 4.6 via OpenRouter (JSON mode + thinking)
  Input: clean extracted text
  Prompt: prompts/1-discovery.md + rubric.md
  Output: JSON {findings: [{number, title, category, defect, correction,
          axiom, evidence: [{location, quote}]}]}
  │
  ▼
Step 1b: QUOTE VERIFICATION (compute, no model)
  Input: findings + source text
  Method: substring match — each evidence quote verified against source
  Output: findings with unverifiable evidence dropped
  │
  ▼
Step 2: GATE
  Model: Opus 4.6 via OpenRouter (JSON mode + thinking)
  Input: verified findings + paper text for context
  Prompt: prompts/2-verification-gate.md
  Output: JSON verdicts {finding_number, verdict, reason}
  │
  ▼
Step 3: EVALUATION WRITER
  Model: Opus 4.6 via OpenRouter (JSON mode + thinking)
  Input: PASSed findings + metadata
  Prompt: prompts/3-evaluation-writer.md
  Output: JSON {summary, findings[{location, description}]}
  │
  ▼
Step 4: ASSEMBLY (compute, no model)
  Input: metadata (0) + verified evidence (1b) + verdicts (2) + eval (3)
  Output: evaluation.json — single deliverable file per paper
```

---

## Evidence Model

Each finding carries an array of evidence — exact quotes from the source document with their locations:

```json
"evidence": [
  {"location": "§16.4.6.17, item (1.1)", "quote": "error category objects (19.5.3.5)"},
  {"location": "§16.4.6.17, item (1.2)", "quote": "time zone database (19.5.3.5)"}
]
```

Each quote is programmatically verified as a substring of the source text before reaching the Gate. Findings with no verifiable evidence are dropped automatically — the Gate never sees them.

---

## JSON Mode

Every pipeline step uses JSON mode (`response_format: {"type": "json_object"}` on OpenRouter). Models return structured JSON parsed with `json.loads()`. No regex parsing of LLM output anywhere in the pipeline.

**OpenRouter fence handling:** OpenRouter wraps Anthropic JSON mode responses in code fences. `_strip_fences()` removes fences before parsing.

---

## Text Extraction

| Source | Function | Library | Used by |
|--------|----------|---------|---------|
| HTML | `extract_html()` | `html.parser` (stdlib) | Metadata, Discovery |
| PDF | `extract_pdf()` | `pymupdf` | Metadata, Discovery |

Text extraction produces clean text with front matter at the top. Both Metadata and Discovery receive extracted text.

---

## Models

| Step | Model | Provider | Mode |
|------|-------|----------|------|
| Metadata | Sonnet 4.6 | OpenRouter | JSON |
| Discovery | Opus 4.6 | OpenRouter | JSON + thinking |
| Gate | Opus 4.6 | OpenRouter | JSON + thinking |
| Eval Writer | Opus 4.6 | OpenRouter | JSON + thinking |

All calls route through OpenRouter. Single API provider.

---

## Output Schema

### Per-paper: `evaluation.json`

```json
{
  "schema_version": "1",
  "paperlint_sha": "abc123def456",
  "prompt_hash": "f25b0f1067fd",
  "paper": "P3642R4",
  "title": "Carry-less product: std::clmul",
  "authors": ["Jan Schultke"],
  "audience": "LEWG",
  "paper_type": "wording",
  "abstract": "Summary of what the paper proposes...",
  "generated": "2026-04-12T...",
  "model": "anthropic/claude-opus-4.6",
  "findings_discovered": 16,
  "findings_passed": 9,
  "findings_rejected": 7,
  "summary": "Evaluation summary...",
  "findings": [
    {
      "location": "§5.2",
      "description": "plain text description of the defect",
      "reference_number": 1
    }
  ],
  "references": [
    {
      "number": 1,
      "location": "§5.2",
      "quote": "exact text from paper",
      "verified": true
    }
  ]
}
```

### Per-mailing: `index.json` (batch mode only)

```json
{
  "schema_version": "1",
  "paperlint_sha": "abc123def456",
  "prompt_hash": "f25b0f1067fd",
  "mailing_id": "2026-02",
  "generated": "2026-04-12T...",
  "total_papers": 81,
  "succeeded": 80,
  "failed": 1,
  "rooms": {
    "LEWG": {"papers": ["P3642R4"], "total_findings": 9}
  },
  "papers": [
    {"paper": "P3642R4", "audience": "LEWG", "findings_passed": 9, "findings_discovered": 16}
  ]
}
```

### Intermediate artifacts (per-paper, for debugging)

```
{output_dir}/{paper_id}/
├── evaluation.json        # the deliverable
├── meta.json              # Step 0: metadata
├── 1-findings.json        # Step 1: discovery findings with evidence
├── 2-gate.json            # Step 2: verdicts
└── 3-eval.json            # Step 3: evaluation writer output
```

---

## Versioning

Each evaluation carries two identifiers:
- **`paperlint_sha`** — git commit hash. Tracks which code produced this.
- **`prompt_hash`** — hash of prompt + rubric file contents. Changes only when evaluation logic changes.

Rerun rule: prompt_hash changed → full rerun. Unchanged → skip.

---

## Invocation

```bash
python -m paperlint eval P3642R4 --output-dir ./output/
python -m paperlint eval ./papers/p3642r4.html --output-dir ./output/
python -m paperlint run 2026-02 --output-dir ./data/ --max-cap 50 --max-processes 10
```

---

## Dependencies

```
openai             # OpenRouter API (all model calls)
python-dotenv      # .env loading
pymupdf            # PDF text extraction
beautifulsoup4     # HTML parsing (mailing page scraper)
requests           # HTTP (paper fetching, mailing scraper)
```

---

## Environment

```
OPENROUTER_API_KEY=sk-or-...
```

---

## Known Limitations

- **Context window:** Papers exceeding ~200K tokens cannot be processed in a single Discovery call.
- **PDF metadata:** `pymupdf` text extraction is good but not perfect on all WG21 PDF formats.
- **Non-determinism:** Same paper run twice may produce different findings. The Gate provides precision consistency — what passes is reliably correct, but the set of candidates varies.
- **Quote verification:** Substring matching. Handles whitespace normalization but not OCR-quality issues in PDFs where extracted text doesn't match the visual content.

---

## Prompts

| Stage | File | Role |
|-------|------|------|
| Discovery | `prompts/1-discovery.md` | Find every mechanically verifiable defect |
| Gate | `prompts/2-verification-gate.md` | Reject everything that isn't a real defect |
| Eval Writer | `prompts/3-evaluation-writer.md` | Assemble findings into evaluation |
| Rubric | `rubric.md` | 30 failure modes across 4 axes |

The prompts are the product. The orchestrator is the plumbing.
