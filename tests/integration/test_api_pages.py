"""The web page (PRD FR-017, SEC-16, v0.4.59; Phase 6 step 4): form, list, run view, the memo as HTML, and what the page must never do.

Synthetic and offline. The helpers of ``test_api.py`` are reused.
"""

import html as html_lib
import json
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)
from credit_intel.api.pages import ASSETS, STATIC, memo_html
from credit_intel.api.security import SECURITY_HEADERS
from credit_intel.memo.sections import DRAFT_STATEMENT
from credit_intel.send_rule import NOTICE

LABEL = re.compile(r"\[(?:SOURCE|CALCULATED|RULE|UNVERIFIED|ANALYST-PROVIDED|OCR)[^\]]*\]")
RUN = "20261030T101530.123456Z-abcdef12"


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def text_of(document: str) -> str:
    document = re.sub(r"<(script|style)\b.*?</\1>", "", document, flags=re.S)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", document))


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.found.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


MEMO_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "thead", "tbody", "tr", "th", "td", "blockquote", "ul", "ol", "li", "em", "strong", "code", "pre", "hr", "br"}


def tags_of(document: str):
    parser = _Tags()
    parser.feed(document)
    return parser.found


def assert_inert(document: str, allowed: set[str] | None = None, *, own_script_allowed: bool = False):
    """No tag outside ``allowed``, no event handler, no inline style, and every reference points at this service."""
    for tag, attrs in tags_of(document):
        assert allowed is None or tag in allowed, tag
        for name, value in attrs.items():
            assert not name.startswith("on") and name != "style", (tag, name)
            if name in ("href", "src", "action"):
                assert value and value.startswith(("/", "#")) and not value.startswith("//"), (tag, name, value)
        if tag == "script":
            assert own_script_allowed and attrs == {"src": "/static/app.js"}, attrs


def submit(client, pdf_bytes, name="statement.pdf", **fields):
    return client.post("/ui/submit", files={"file": (name, pdf_bytes, "application/pdf")}, data=fields, follow_redirects=False)


def finished_page(client, pdf, **fields):
    answer = submit(client, pdf.read_bytes(), **fields)
    assert answer.status_code == 303
    location = answer.headers["location"]
    run_id = location.rsplit("/", 1)[1]
    base.wait(client, run_id)
    return run_id, client.get(location)


def write_run(settings, run_id=RUN, memo="# Memo\n\nbody\n", state="exported", files=("memo.md", "results.json", "manifest.json"), **manifest):
    folder = settings.output_dir / run_id
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"final_state": state, **manifest}), encoding="utf-8")
    if "memo.md" in files:
        (folder / "memo.md").write_text(memo, encoding="utf-8")
    if "results.json" in files:
        (folder / "results.json").write_text("{}", encoding="utf-8")
    return folder


# --- the form and the list ---------------------------------------------------------------------------------------------------------------------


def test_the_front_page_has_the_form_with_every_option_and_the_notice_beside_the_confirmation(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = client.get("/")
    page = answer.text
    assert answer.status_code == 200 and answer.headers["content-type"] == "text/html; charset=utf-8"
    assert re.search(r'<form[^>]*method="post"[^>]*action="/ui/submit"[^>]*enctype="multipart/form-data"', page)
    for name in ("file", "basis", "pages", "assert_basis", "profile", "ocr", "no_report", "confirm_public_document"):
        assert f'name="{name}"' in page, name
    assert re.search(r'<input id="file" name="file" type="file"[^>]*required', page)
    notice = page.index(html_lib.escape(NOTICE, quote=True))
    assert notice < page.index('name="confirm_public_document"') < notice + len(NOTICE) + 400  # the notice and its checkbox are one block
    assert "No runs yet." in page and DRAFT_STATEMENT in page


def test_the_confirmation_is_required_on_the_form_only_when_the_provider_is_external(pdf, tmp_path):
    for provider, required in (("fake", False), ("openai", True)):
        app, _ = base.build(tmp_path, pdf, provider=provider)
        with TestClient(app) as client:
            box = re.search(r'<input type="checkbox" name="confirm_public_document"[^>]*>', client.get("/").text).group(0)
        assert (" required" in box) is required, provider


def test_the_list_shows_runs_with_links_to_their_pages_newest_first(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    older, newer = "20261029T101530.123456Z-aaaaaaaa", "20261030T101530.123456Z-bbbbbbbb"
    write_run(settings, older)
    write_run(settings, newer, state="failed", error_code="E-INPUT-CORRUPT", failed_stage="validated")
    with TestClient(app) as client:
        page = client.get("/").text
    assert page.index(newer) < page.index(older)
    assert f'<a href="/ui/runs/{newer}">' in page and 'class="pill failed"' in page and 'class="pill exported"' in page


# --- submitting from the form -----------------------------------------------------------------------------------------------------------------


def test_the_form_starts_a_run_and_sends_the_browser_to_its_page_which_shows_the_memo(pdf, tmp_path, real_report):
    app, settings = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = submit(client, pdf.read_bytes(), basis="consolidated", pages="", assert_basis="", profile="")
        assert answer.status_code == 303 and re.fullmatch(rf"/ui/runs/{base.RUN_ID}", answer.headers["location"])
        run_id = answer.headers["location"].rsplit("/", 1)[1]
        base.wait(client, run_id)
        view = client.get(f"/ui/runs/{run_id}")
    page = view.text
    assert view.status_code == 200 and 'data-final="true"' in page and "<strong id=\"state\">exported</strong>" in page
    memo = (settings.output_dir / run_id / "memo.md").read_text(encoding="utf-8")
    assert '<article class="memo card">' in page and "<h1>" in page
    for name, label in (("memo", "memo (Markdown)"), ("report", "report (PDF)"), ("results", "results (JSON)"), ("manifest", "manifest (JSON)")):
        assert f'<a href="/runs/{run_id}/{name}">{label}</a>' in page
    shown = text_of(page)
    assert DRAFT_STATEMENT in shown and page.count(html_lib.escape(DRAFT_STATEMENT)) >= 2  # in the memo and in the fixed footer
    assert sorted(LABEL.findall(shown)) == sorted(LABEL.findall(memo)) and LABEL.findall(memo)  # every label in place, none added


def test_section_nine_of_the_memo_is_on_the_page_whole(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        run_id, view = finished_page(client, pdf, no_report="true")
    memo = (settings.output_dir / run_id / "memo.md").read_text(encoding="utf-8")
    section = re.split(r"^## ", memo, flags=re.M)[-1]
    shown = re.sub(r"\s+", " ", text_of(view.text))
    for line in section.splitlines()[1:]:
        plain = re.sub(r"\s+", " ", re.sub(r"[*`]|^\s*(?:>|-|\d+\.)\s+", "", line)).strip()
        if len(plain) > 12:
            assert plain in shown, plain


def test_options_of_the_form_reach_the_run(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    profile = json.dumps({"borrower_name": "Acme Industries Limited"})
    with TestClient(app) as client:
        run_id, view = finished_page(client, pdf, basis="consolidated", pages="1", assert_basis="consolidated", profile=profile, no_report="true")
    assert "Acme Industries Limited" in view.text and not (settings.output_dir / run_id / "report.pdf").exists()


@pytest.mark.parametrize("make, status, code", [
    (lambda c, pdf: submit(c, b"not a pdf"), 422, "E-INPUT-NOT-PDF"),
    (lambda c, pdf: submit(c, pdf.read_bytes(), profile="{bad"), 422, "E-INPUT-PROFILE-INVALID"),
    (lambda c, pdf: submit(c, pdf.read_bytes(), pages="9-1"), 422, "E-INPUT-PAGE-RANGE"),
    (lambda c, pdf: submit(c, pdf.read_bytes(), assert_basis="standalone"), 422, "E-API-REQUEST"),
    (lambda c, pdf: c.post("/ui/submit", data={"basis": "consolidated"}), 422, "E-API-REQUEST")])  # fmt: skip
def test_a_refused_submission_shows_the_form_again_with_the_catalogued_code_and_message_and_creates_no_run(pdf, tmp_path, make, status, code):
    app, settings = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = make(client, pdf)
    assert answer.status_code == status and 'role="alert"' in answer.text and f"<strong>{code}</strong>" in answer.text and 'name="file"' in answer.text
    assert not settings.output_dir.exists()


def test_a_submission_over_the_limit_or_while_the_queue_is_full_is_shown_with_its_status(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "base.pdf")
    app, _ = base.build(tmp_path, pdf, max_file_bytes=1000)
    with TestClient(app) as client:
        answer = submit(client, pdf.read_bytes())
    assert answer.status_code == 413 and "<strong>E-INPUT-TOO-LARGE</strong>" in answer.text
    gate = base.Gate(pdf)
    app, _ = base.build(tmp_path, pdf, concurrent=1, queued=0, factory=gate)
    with TestClient(app) as client:
        assert submit(client, pdf.read_bytes(), no_report="true").status_code == 303
        assert gate.entered.acquire(timeout=30)
        busy = submit(client, pdf.read_bytes() + b"\n%2", no_report="true")
        gate.release.set()
    assert busy.status_code == 429 and "Too many runs are waiting" in busy.text and "Not accepted" in busy.text


def test_a_send_refusal_is_shown_with_its_reason_word(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf, provider="openai")
    with TestClient(app) as client:
        answer = submit(client, pdf.read_bytes())
    assert answer.status_code == 403 and "<strong>E-INPUT-SEND-REFUSED</strong>" in answer.text and "not_recorded" in answer.text


# --- the run view for every state ---------------------------------------------------------------------------------------------------------------


def test_a_run_in_flight_shows_its_state_and_the_polling_script_and_not_a_final_state(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "base.pdf")
    gate = base.Gate(pdf)
    app, _ = base.build(tmp_path, pdf, factory=gate)
    with TestClient(app) as client:
        location = submit(client, pdf.read_bytes(), no_report="true").headers["location"]
        assert gate.entered.acquire(timeout=30)
        page = client.get(location).text
        gate.release.set()
    assert 'data-final="false"' in page and "<noscript>" in page and '<script src="/static/app.js"></script>' in page
    assert re.search(r'<strong id="state">(received|validated|text_extracted|statements_located|fields_extracted)</strong>', page) and "<h2>Memo</h2>" not in page


def test_a_failed_run_shows_its_code_and_message_and_only_the_files_that_exist(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "base.pdf")
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot really\n")
    app, _ = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        run_id, view = finished_page(client, bad)
    page = view.text
    assert 'data-final="true"' in page and "<strong>E-INPUT-CORRUPT</strong>" in page and "Re-download" in page and "<h2>Memo</h2>" not in page
    assert f'href="/runs/{run_id}/manifest"' in page and f'href="/runs/{run_id}/memo"' not in page


def test_a_run_from_before_a_restart_is_shown_from_its_files(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    write_run(settings, memo="# A memo from an earlier process\n\nText.\n")
    with TestClient(app) as client:
        page = client.get(f"/ui/runs/{RUN}").text
    assert "A memo from an earlier process" in page and 'data-final="true"' in page


@pytest.mark.parametrize("path", [f"/ui/runs/{RUN}", "/ui/runs/x", "/ui/runs/%3Cscript%3Ealert(1)%3C%2Fscript%3E", "/ui/runs/..%2f..%2fetc", "/ui/nothing"])
def test_an_unknown_run_or_page_is_a_404_page_that_does_not_echo_the_request(pdf, tmp_path, path):
    app, _ = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = client.get(path)
    assert answer.status_code == 404 and "There is no such run or file." in answer.text
    assert_inert(answer.text, own_script_allowed=True)
    assert "alert" not in answer.text and "%3C" not in answer.text and "..%2f" not in answer.text


# --- the memo as HTML: nothing in it can load, link or run -----------------------------------------------------------------------------------------

HOSTILE = "\n".join([
    "# Memo", "", "> **" + DRAFT_STATEMENT + "**", "",
    "Borrower <script>alert(1)</script> and <img src=x onerror=alert(2)> and <a href=\"http://evil.example\">a</a> &lt;b&gt; &amp; \"quoted\" 'single'",
    "", "[click me](javascript:alert(3)) and [other](http://evil.example/x) and ![pic](http://evil.example/p.png) and <http://evil.example/auto>",
    "", "<div onclick=\"alert(4)\">raw block</div>", "", "| a | b |", "|---|---|", "| <b>x</b> | [SOURCE: p.3] |", "",
    "Revenue 1,234 [SOURCE: p.3] and [CALCULATED: MET-01] and [UNVERIFIED]", "",
])  # fmt: skip


def test_the_memo_html_has_no_raw_html_no_link_no_image_and_no_script_and_shows_every_label_as_text():
    out = memo_html(HOSTILE)
    found = tags_of(out)
    assert {tag for tag, _ in found} <= MEMO_TAGS and all(attrs == {} for _, attrs in found)  # only the memo's own structure, with no attribute at all
    shown = text_of(out)
    for needle in ("<script>alert(1)</script>", "<img src=x onerror=alert(2)>", "[click me](javascript:alert(3))", "![pic](http://evil.example/p.png)", "[SOURCE: p.3]", "[CALCULATED: MET-01]", "[UNVERIFIED]"):
        assert needle in shown, needle
    assert {"table", "blockquote", "h1"} <= {tag for tag, _ in found}


def test_a_hostile_memo_is_shown_as_text_on_the_run_page_under_the_policy(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    write_run(settings, memo=HOSTILE)
    with TestClient(app) as client:
        answer = client.get(f"/ui/runs/{RUN}")
    assert_inert(answer.text, own_script_allowed=True)
    shown = text_of(answer.text)
    assert "<script>alert(1)</script>" in shown and "[click me](javascript:alert(3))" in shown and "<div onclick=\"alert(4)\">raw block</div>" in shown
    for name, value in SECURITY_HEADERS.items():
        assert answer.headers[name] == value


def test_a_profile_with_markup_goes_through_the_whole_path_and_is_text_on_the_page(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf)
    profile = json.dumps({"borrower_name": "<img src=x onerror=alert(1)>", "notes": "<script>alert(2)</script> [x](javascript:alert(3))"})
    with TestClient(app) as client:
        run_id, view = finished_page(client, pdf, profile=profile, no_report="true")
    assert_inert(view.text, own_script_allowed=True)
    shown = text_of(view.text)
    assert "<img src=x onerror=alert(1)>" in shown and "<script>alert(2)</script>" in shown and "javascript:alert(3)" in shown


def test_whatever_a_manifest_on_disk_says_is_escaped_where_the_page_prints_it(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    hostile = '"><script>alert(1)</script><b onmouseover="x'
    write_run(settings, state=hostile, error_code=hostile, failed_stage=hostile)
    with TestClient(app) as client:
        pages = [client.get("/").text, client.get(f"/ui/runs/{RUN}").text]
    for page in pages:
        assert_inert(page, own_script_allowed=True)
        assert "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in page


# --- the page, its files and the policy --------------------------------------------------------------------------------------------------------------


def test_no_page_has_an_inline_style_or_script_or_event_handler_or_an_external_reference(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    write_run(settings, memo=HOSTILE)
    with TestClient(app) as client:
        pages = [client.get("/").text, client.get(f"/ui/runs/{RUN}").text, client.get("/ui/runs/x").text, submit(client, b"nope").text]
    for page in pages:
        assert_inert(page, own_script_allowed=True)
        assert [attrs["href"] for tag, attrs in tags_of(page) if tag == "link"] == ["/static/app.css"]


@pytest.mark.parametrize("name, media", list(ASSETS.items()))
def test_the_stylesheet_and_the_script_are_served_with_their_type_and_the_policy(pdf, tmp_path, name, media):
    app, _ = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = client.get(f"/static/{name}")
    assert answer.status_code == 200 and answer.headers["content-type"] == media and answer.content == (STATIC / name).read_bytes()
    for header, value in SECURITY_HEADERS.items():
        assert answer.headers[header] == value


def test_the_script_writes_text_only_and_uses_nothing_that_runs_or_loads_strings():
    code = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "textContent" in code
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacent", "document.write", "eval(", "Function(", "setTimeout(\"", "setInterval(\"", "XMLHttpRequest", "localStorage", "cookie"):
        assert forbidden not in code, forbidden
    assert re.findall(r'fetch\("([^"]+)"', code) == ["/runs/"]  # only to this service


def test_the_stylesheet_loads_nothing_and_defines_both_themes():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert "url(" not in css and "@import" not in css and "expression(" not in css and "prefers-color-scheme: dark" in css


def test_the_routes_beyond_the_api_are_exactly_the_pages_and_the_two_static_files_and_none_is_in_the_api_document(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf)
    pages = {(route.path, tuple(sorted(route.methods))) for route in app.routes if getattr(route, "include_in_schema", True) is False and hasattr(route, "methods")}
    assert pages == {("/", ("GET",)), ("/ui/submit", ("POST",)), ("/ui/runs/{run_id}", ("GET",)), ("/static/app.css", ("GET",)), ("/static/app.js", ("GET",))}
    assert not [p for p in app.openapi()["paths"] if p.startswith(("/ui", "/static")) or p == "/"]


def test_a_cross_origin_form_post_is_refused_before_anything_is_read(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = client.post("/ui/submit", files={"file": ("a.pdf", pdf.read_bytes())}, headers={"Origin": "http://evil.example"}, follow_redirects=False)
    assert answer.status_code == 403 and not settings.output_dir.exists()


def test_with_a_token_the_pages_need_it_like_every_other_endpoint(pdf, tmp_path):
    token = "p" * 40
    app, _ = base.build(tmp_path, pdf, env={"CREDIT_INTEL_API_TOKEN": token})
    with TestClient(app) as client:
        for path in ("/", f"/ui/runs/{RUN}", "/static/app.js", "/static/app.css"):
            assert client.get(path).status_code == 401, path
        assert client.post("/ui/submit", files={"file": ("a.pdf", b"%PDF-")}).status_code == 401
        assert client.get("/", headers={"Authorization": f"Bearer {token}"}).status_code == 200
