"""HTML to Markdown converter for WG21 papers."""

import logging
import os
from pathlib import Path

from .. import format_front_matter
from . import extract as _extract
from . import render as _render

_log = logging.getLogger(__name__)


def convert_html(path: Path | os.PathLike[str]) -> tuple[str, list[str] | None]:
    """Convert an HTML file to Markdown.

    Reads the file as UTF-8 (with replacement for decode errors). Returns
    ``(markdown_text, prompts_or_none)`` where ``prompts_or_none`` is a
    list of self-contained LLM reconcile prompts (one per flagged HTML
    conversion issue) or ``None`` when conversion was fully clean.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    soup = _extract.parse_html(text)
    generator = _extract.detect_generator(soup)
    _log.debug("Generator: %s", generator)

    metadata = _extract.extract_metadata(soup, generator)
    problems = _extract.strip_boilerplate(soup, generator)
    # Suppress the "unknown generator" warning when extraction produced usable
    # metadata - the generic extractor handled it well enough.
    if generator == "unknown" and metadata:
        problems = [p for p in problems if "Unrecognized" not in p]

    body_md = _render.render_body(soup, generator)

    parts = []
    if metadata:
        parts.append(format_front_matter(metadata))

    if body_md.strip():
        parts.append(body_md.strip())

    md = "\n\n".join(parts)
    md = md.rstrip() + "\n"

    prompts: list[str] | None = None
    if problems:
        prompts = [
            (
                "The HTML-to-Markdown conversion encountered the following issue. "
                "Review and correct the affected region in the converted "
                "Markdown.\n\n"
                f"{problem}"
            )
            for problem in problems
        ]

    return md, prompts
