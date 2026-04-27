#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Public tomd API: convert a staged paper in paperstore to markdown.

``convert_paper(paper_id, store)`` is the only supported entry point.
The converter looks up the source file and metadata in ``store`` (errors
if either is absent), converts, then writes the paper's markdown (and an
optional ``<pid>.prompts.json`` intermediate of LLM reconcile prompts)
back through the store. Returns the path of the written markdown.

YAML front-matter fallback lives here: whatever tomd could not extract
from the source paper is filled in from the mailing-index row for the
paper. Fields already present in the paper's front matter win.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from tomd.lib.html import convert_html
from tomd.lib.pdf import convert_pdf

__all__ = ["convert_paper"]


_TOC_MAX_LINES = 300
_TOC_RE = re.compile(
    r"(?m)^(?:#{1,3}\s*)?(?:Table of )?Contents\s*$\r?\n?"
    r"(.*?)"
    r"(?=\r?\n#{1,3}\s|\Z)",
    re.DOTALL | re.IGNORECASE,
)

_FALLBACK_KEY_MAP = {
    "title": "title",
    "paper_id": "document",
    "document_date": "date",
    "subgroup": "audience",       # mailing row key
    "target_group": "audience",   # DB row key (SqliteBackend)
    "authors": "reply-to",
}

_FRONT_MATTER_RE = re.compile(
    r"\A---\s*\n(?P<body>.*?)\n---\s*\n?", re.DOTALL
)


def _strip_toc_replace(m: re.Match[str]) -> str:
    span = m.group(0)
    if span.count("\n") > _TOC_MAX_LINES:
        return span
    return "\n"


def _strip_toc(text: str) -> str:
    """Remove Table of Contents sections that produce phantom findings."""
    return _TOC_RE.sub(_strip_toc_replace, text)


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_yaml_value(key: str, val) -> str:
    if isinstance(val, list):
        items = "\n".join(f'  - "{_yaml_escape(str(v))}"' for v in val)
        return f"{key}:\n{items}"
    s = str(val)
    if any(c in s for c in ':{}[]#&*?|>!%@`"\'\n\\'):
        return f'{key}: "{_yaml_escape(s)}"'
    return f"{key}: {s}"


def _present_keys(front_matter_body: str) -> set[str]:
    keys: set[str] = set()
    for line in front_matter_body.splitlines():
        if not line or line.startswith((" ", "\t", "-", "#")):
            continue
        head, sep, _ = line.partition(":")
        if sep:
            keys.add(head.strip())
    return keys


def _apply_metadata_fallback(md: str, mailing_meta: dict | None) -> str:
    """Inject any missing YAML front-matter fields from ``mailing_meta``."""
    if not mailing_meta:
        return md

    match = _FRONT_MATTER_RE.match(md)
    if match:
        body = match.group("body")
        present = _present_keys(body)
        rest = md[match.end():]
    else:
        body = ""
        present = set()
        rest = md

    additions: list[str] = []
    for src_key, yaml_key in _FALLBACK_KEY_MAP.items():
        if yaml_key in present:
            continue
        val = mailing_meta.get(src_key)
        if val in (None, "", []):
            continue
        additions.append(_format_yaml_value(yaml_key, val))

    if not additions and match:
        return md

    new_body_lines = [body.rstrip()] if body.strip() else []
    new_body_lines.extend(additions)
    new_body = "\n".join(line for line in new_body_lines if line)

    if new_body:
        return f"---\n{new_body}\n---\n\n{rest.lstrip()}"
    return md


def _convert_with_tomd(path: Path) -> tuple[str, list[str] | None]:
    """Dispatch to the appropriate tomd converter by file suffix."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return convert_pdf(path)
    if suffix in (".html", ".htm"):
        return convert_html(path)
    return convert_html(path)


_INTENT_LINE_RE = re.compile(r"^intent\s*:\s*(\S+)", re.MULTILINE)


def _extract_intent_from_front_matter(md: str) -> str:
    """Return the ``intent`` value from the markdown YAML front matter, or ``""``."""
    front_matter_match = _FRONT_MATTER_RE.match(md)
    if not front_matter_match:
        return ""
    body = front_matter_match.group("body")
    intent_match = _INTENT_LINE_RE.search(body)
    if not intent_match:
        return ""
    return intent_match.group(1).strip().strip('"\'')


def convert_paper(
    paper_id: str,
    source_path: Path,
    meta: dict,
    *,
    write_prompts: bool = True,
) -> tuple[Path, str]:
    """Convert a staged source file to markdown. No database access.

    All inputs are pre-fetched by the caller. Writes the markdown and
    optional prompts file directly to disk (same directory as source_path).
    The caller is responsible for recording the returned path in the database.

    Returns ``(md_path, extracted_intent)`` where ``extracted_intent`` is the
    ``intent`` value from the paper's YAML front matter (``""`` if absent).

    Raises:
        RuntimeError: tomd produced no usable markdown.
    """
    workspace_dir = source_path.parent
    pid_lower = paper_id.strip().upper().lower()

    md, prompts = _convert_with_tomd(source_path)

    if prompts:
        print(
            f"tomd [{paper_id}] flagged {len(prompts)} uncertain region(s)",
            file=sys.stderr,
        )

    if not md or not md.strip():
        raise RuntimeError(
            f"tomd produced empty markdown for {paper_id} (slide deck, "
            f"standards draft, or unreadable source)."
        )

    md = _apply_metadata_fallback(md, meta)
    md = _strip_toc(md)

    # Atomic write: temp → rename
    import os, time as _time
    final_path = workspace_dir / f"{pid_lower}.md"
    temp_path = final_path.with_stem(final_path.stem + ".tmp")
    if temp_path.exists():
        temp_path.unlink()
    temp_path.write_text(md, encoding="utf-8")
    for _ in range(10):
        try:
            os.replace(temp_path, final_path)
            break
        except PermissionError:
            _time.sleep(0.1)
    else:
        os.replace(temp_path, final_path)

    if write_prompts and prompts:
        prompts_path = workspace_dir / f"{pid_lower}.prompts.json"
        import json as _json
        prompts_path.write_text(
            _json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    extracted_intent = _extract_intent_from_front_matter(md)
    return final_path, extracted_intent
