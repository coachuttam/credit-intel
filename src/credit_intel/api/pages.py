"""The web page (PRD FR-017, SEC-16, v0.4.59; Phase 6 step 4): an upload form, the list of runs and a run view, server-rendered.

The page presents the files a run wrote and adds nothing to them: no number, label or sentence of analysis, only the form's own text, the catalogued
messages and the run's state. The memo is shown through the same CommonMark parser as the report, **with raw HTML, links and images switched off**, so a
label such as ``[SOURCE: p.3]`` is plain text and anything a document, analyst or profile put in the memo is escaped text. Every string that is not a constant
goes through ``esc``. There is no inline style or script (the policy of SEC-16 forbids them); one stylesheet and one small script are served from here.
When a token is set the pages need it like every other endpoint (SEC-15): a browser cannot send it, so the page is for the loopback default, or behind a
reverse proxy that adds the header.
"""

import html
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from markdown_it import MarkdownIt

from credit_intel.api.errors import NOT_FOUND
from credit_intel.config import load_llm_settings
from credit_intel.ingestion.errors import IngestionError
from credit_intel.memo.sections import DRAFT_STATEMENT
from credit_intel.send_rule import NOTICE

STATIC = Path(__file__).parent / "static"
ASSETS = {"app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
BASES = ("consolidated", "standalone")
FINAL = ("exported", "failed")
FILES = (("memo", "memo.md", "memo (Markdown)"), ("report", "report.pdf", "report (PDF)"), ("results", "results.json", "results (JSON)"),
         ("manifest", "manifest.json", "manifest (JSON)"))  # fmt: skip


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def memo_html(memo: str) -> str:
    """The memo as HTML: CommonMark with tables, and raw HTML, links, images and autolinks off, so nothing in it can load, link or run."""
    md = MarkdownIt("commonmark", {"html": False}).enable("table").disable(["html_block", "html_inline", "link", "image", "autolink"])
    return md.render(memo)


def page(title: str, body: str, *, status: int = 200) -> HTMLResponse:
    document = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        f'<title>{esc(title)}</title><link rel="stylesheet" href="/static/app.css"></head><body>'
        '<header><a href="/">AI Credit Intelligence</a><span>Draft memos from public or synthetic financial statements</span></header>'
        f'<main>{body}</main><div class="banner" role="note">{esc(DRAFT_STATEMENT)}</div><script src="/static/app.js"></script></body></html>'
    )
    return HTMLResponse(document, status_code=status)


def _select(name: str, label: str, options: tuple[tuple[str, str], ...], selected: str = "") -> str:
    items = "".join(f'<option value="{esc(value)}"{" selected" if value == selected else ""}>{esc(text)}</option>' for value, text in options)
    return f'<div><label for="{name}">{esc(label)}</label><select id="{name}" name="{name}">{items}</select></div>'


def form_html(external: bool, error: tuple[str, str] | None = None) -> str:
    problem = f'<div class="error" role="alert"><strong>{esc(error[0])}</strong> {esc(error[1])}</div>' if error else ""
    required = " required" if external else ""
    return (
        "<h1>New run</h1>"
        '<p class="muted">Upload one financial-statements PDF. The result is a draft memo for human review, with every figure traced to its page. '
        "It is not a credit decision.</p>"
        f'{problem}<form class="card" method="post" action="/ui/submit" enctype="multipart/form-data">'
        '<div><label for="file">PDF file</label><input id="file" name="file" type="file" accept="application/pdf,.pdf" required></div>'
        '<div class="row">'
        + _select("basis", "Statement basis", tuple((b, b.capitalize()) for b in BASES))
        + '<div><label for="pages">Statement pages (optional)</label><input id="pages" name="pages" type="text" placeholder="e.g. 110-115,120" autocomplete="off"></div>'
        + _select("assert_basis", "Basis of those pages (needs pages)", (("", "Not stated"), *((b, b.capitalize()) for b in BASES)))
        + "</div>"
        '<div><label for="profile">Borrower profile (optional, JSON)</label><textarea id="profile" name="profile" spellcheck="false" '
        'placeholder=\'{"borrower_name": "...", "industry": "...", "facility_requested": "...", "notes": "..."}\'></textarea>'
        '<span class="muted">Only those four keys, each a string of at most 500 characters. Shown in the memo as analyst-provided and never used as evidence.</span></div>'
        '<label class="check"><input type="checkbox" name="ocr" value="true"><span>Read image-only pages by OCR (needs pages)</span></label>'
        '<label class="check"><input type="checkbox" name="no_report" value="true"><span>Skip the PDF report</span></label>'
        f'<div class="notice">{esc(NOTICE)}'
        f'<label class="check"><input type="checkbox" name="confirm_public_document" value="true"{required}><span>This document is public or synthetic, '
        "and its statement pages may be sent to the hosted model.</span></label></div>"
        '<button type="submit">Start the run</button></form>'
    )


def _pill(state: object) -> str:
    return f'<span class="pill {esc(state)}">{esc(state)}</span>'


def list_html(runs: list[dict[str, object]]) -> str:
    if not runs:
        return '<h2>Runs</h2><p class="muted">No runs yet.</p>'
    rows = "".join(f'<tr><td><a href="/ui/runs/{esc(r["run_id"])}">{esc(r["run_id"])}</a></td><td>{_pill(r["state"])}</td></tr>' for r in runs)
    return f'<h2>Runs</h2><table class="runs"><thead><tr><th>Run</th><th>State</th></tr></thead><tbody>{rows}</tbody></table>'


def run_html(status: dict[str, object], memo: str | None) -> str:
    run_id, state = str(status["run_id"]), str(status["state"])
    final = state in FINAL
    body = (f'<h1>Run</h1><p><code>{esc(run_id)}</code></p>'
            f'<div id="run" data-run-id="{esc(run_id)}" data-final="{"true" if final else "false"}"><p>State: <strong id="state">{esc(state)}</strong></p></div>')  # fmt: skip
    if not final:
        body += '<noscript><p class="muted">This page does not update itself without its script: reload it to see the run move on.</p></noscript>'
    error = status.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        body += f'<div class="error" role="alert"><strong>{esc(code) if code else "Internal error"}</strong> {esc(error.get("message", ""))}</div>'
    files = status.get("files")
    if isinstance(files, list) and files:
        links = "".join(f'<li><a href="/runs/{esc(run_id)}/{name}">{esc(label)}</a></li>' for name, filename, label in FILES if filename in files)
        body += f'<h2>Files</h2><ul class="files">{links}</ul>'
    if memo is not None:
        body += f'<h2>Memo</h2><article class="memo card">{memo_html(memo)}</article>'
    return body


def add_pages(app: FastAPI, *, config: Path, listing: Callable[[], list[dict[str, object]]], status_of: Callable[[str], dict[str, object] | None],
              read_memo: Callable[[str], str | None], accept: Callable[[Request], Awaitable[Response]]) -> None:  # fmt: skip
    def external() -> bool:
        try:
            return load_llm_settings(config).provider != "fake"  # the confirmation is required on the form when the pages would leave the machine
        except IngestionError:
            return True

    def missing() -> HTMLResponse:
        return page("Not found", f'<h1>Not found</h1><p>{esc(NOT_FOUND)}</p><p><a href="/">Back to the form</a></p>', status=404)

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return page("AI Credit Intelligence", form_html(external()) + list_html(listing()))

    @app.post("/ui/submit", include_in_schema=False)
    async def submit(request: Request) -> Response:
        answer = await accept(request)  # the same function, the same checks and the same limits as `POST /runs`
        body = json.loads(answer.body)
        if answer.status_code == 202:
            return RedirectResponse(f"/ui/runs/{body['run_id']}", status_code=303)
        problem = (body.get("code") or "Not accepted", body.get("message", ""))
        return page("AI Credit Intelligence", form_html(external(), problem) + list_html(listing()), status=answer.status_code)

    @app.get("/ui/runs/{run_id}", include_in_schema=False)
    async def run_view(run_id: str) -> HTMLResponse:
        status = status_of(run_id)  # None for anything that is not a run ID of the fixed form, or has no folder
        if status is None:
            return missing()
        return page(f"Run {run_id}", run_html(status, read_memo(run_id)))  # only a finished run has a memo file

    def asset_route(name: str, media_type: str):  # type: ignore[no-untyped-def]
        async def asset() -> Response:
            return Response((STATIC / name).read_bytes(), media_type=media_type)

        return asset

    for asset_name, asset_type in ASSETS.items():
        app.add_api_route(f"/static/{asset_name}", asset_route(asset_name, asset_type), methods=["GET"], include_in_schema=False)
