"""
HTML rendering for browser preview / direct print.

Same `ctx` (placeholder dict) that the Word template engine uses is fed
to a Jinja2 environment rooted at ``templates/html/``. This means a
single source of truth for the document data — adding a new mail-merge
field automatically becomes available in both the .docx and the HTML
preview.

The HTML pages are intentionally print-friendly: they include @page
rules, hide their own toolbars during print, and use standard fonts that
Windows/Linux ship with for Devanagari (Mangal / Nirmala UI / Noto Sans
Devanagari).
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from .. import config

log = logging.getLogger(__name__)

HTML_DIR: Path = config.TEMPLATES_DIR / "html"

_env: Environment | None = None


def _get_env() -> Environment:
    global _env
    if _env is None:
        if not HTML_DIR.exists():
            HTML_DIR.mkdir(parents=True, exist_ok=True)
        _env = Environment(
            loader=FileSystemLoader(str(HTML_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=False, lstrip_blocks=False,
        )
    return _env


# Maps document `kind` to its HTML template file name. Keys mirror
# ``doc_generator.KIND_TO_TEMPLATE`` so the same kinds are valid for
# both .docx and HTML rendering.
KIND_TO_HTML: dict[str, str] = {
    "provisional_consumer": "provisional_consumer.html",
    "provisional_office":   "provisional_office.html",
    "final_notice":         "final_notice.html",
    "section3":             "section3.html",
    "section5":             "section5.html",
    "thanedari":            "thanedari.html",
    "envelope":             "envelope.html",
    "deposit_slip":         "deposit_slip.html",
    "noc":                  "noc.html",
    "compounding_order":    "compounding_order.html",
}


def render_html(kind: str, ctx: dict[str, Any]) -> str:
    """Render a document kind to a complete HTML string."""
    name = KIND_TO_HTML.get(kind)
    if not name:
        raise ValueError(f"Unknown HTML kind '{kind}'. "
                         f"Valid: {list(KIND_TO_HTML.keys())}")
    env = _get_env()
    try:
        tpl = env.get_template(name)
    except TemplateNotFound:
        raise FileNotFoundError(f"HTML template not found: {HTML_DIR / name}")
    return tpl.render(ctx=ctx)
