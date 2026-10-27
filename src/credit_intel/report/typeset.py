"""Typesetting the memo as a PDF (PRD FR-015, v0.4.56; step 2 of its build).

``build_pdf(memo)`` takes the memo text that is also written as ``memo.md`` and returns the bytes of a PDF. It reads nothing else.
Every element of the memo is typeset as it is; nothing is added to a value and no sentence of analysis is written. The additions are a
cover block (the memo's own header), a running footer that repeats the memo's draft statement on **every** page with the run ID and
the page number, and styling of the origin labels.

**Untrusted text (SEC-13, FR-015 criterion 6).** Text from the document, the analyst or the model-free template reaches this module.
The PDF library's paragraph markup can load images and links, so no text is ever passed to it as markup: the memo is parsed as
CommonMark, and every piece of text is escaped before it goes into a paragraph. The only tags in a paragraph are the ones built here
(bold, italic, a font for code, a style for a label, a line break). An image or a link in the memo is printed as its plain text and
nothing is loaded. A character that the embedded font lacks stops the build (``glyph_missing``) instead of printing a blank box.

The same memo gives byte-identical bytes (reportlab's fixed-date mode).
"""

import io
import re
from collections.abc import Callable
from xml.sax.saxutils import escape

from markdown_it import MarkdownIt
from markdown_it.token import Token
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, HRFlowable, ListFlowable, ListItem, PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle

from credit_intel.memo.sections import DRAFT_STATEMENT
from credit_intel.memo.trace import FORMS
from credit_intel.report import fonts
from credit_intel.report.errors import ReportError

PAGE = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE[0] - 2 * MARGIN
INK, MUTED, RULE = colors.HexColor("#14202e"), colors.HexColor("#5a6877"), colors.HexColor("#c8d0d9")
LABEL_COLOURS = {"ocr": ("#8a5a00", "#fbefd2"), "label": ("#1d3557", "#dbe7f3")}
_LABEL = re.compile(r"\[([^\]]*)\]")
_RUN_ID = re.compile(r"\*\*Run ID:\*\* `([^`]+)`")
_COLLAPSED = re.compile(r"\s+")


def _styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName=fonts.SANS, textColor=INK, fontSize=9, leading=12.6, spaceAfter=4)
    return {
        "body": ParagraphStyle("body", **base),
        "h1": ParagraphStyle("h1", **{**base, "fontName": fonts.BOLD, "fontSize": 21, "leading": 25, "spaceAfter": 8}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": fonts.BOLD, "fontSize": 13, "leading": 16, "spaceBefore": 12, "spaceAfter": 3, "keepWithNext": 1}),
        "h3": ParagraphStyle("h3", **{**base, "fontName": fonts.BOLD, "fontSize": 10.5, "leading": 13, "spaceBefore": 6, "keepWithNext": 1}),
        "cover": ParagraphStyle("cover", **{**base, "fontSize": 9.5, "leading": 14, "spaceAfter": 1}),
        "banner": ParagraphStyle("banner", **{**base, "fontName": fonts.BOLD, "fontSize": 10, "leading": 14, "backColor": colors.HexColor("#fbe8d6"),
                                              "textColor": colors.HexColor("#7a3b00"), "borderPadding": (7, 8, 7, 8), "spaceBefore": 8, "spaceAfter": 14}),  # fmt: skip
        "quote": ParagraphStyle("quote", **{**base, "fontSize": 8.4, "leading": 11.6, "leftIndent": 10, "backColor": colors.HexColor("#f2f5f8"),
                                            "borderPadding": (3, 4, 3, 6), "spaceAfter": 5}),  # fmt: skip
        "cell": ParagraphStyle("cell", **{**base, "fontSize": 7.8, "leading": 10, "spaceAfter": 0}),
        "head": ParagraphStyle("head", **{**base, "fontName": fonts.BOLD, "fontSize": 7.8, "leading": 10, "spaceAfter": 0}),
    }


class _Typesetter:
    def __init__(self) -> None:
        fonts.register()
        self.styles = _styles()
        self.used: list[tuple[str, str]] = []  # (face, text) printed, for the glyph check
        self.banner: str | None = None
        self.quotes_seen = False

    # --- inline ------------------------------------------------------------------------------------------------

    def _text(self, face: str, text: str) -> str:
        self.used.append((face, text))
        return escape(text)

    def _label_styled(self, face: str, text: str) -> str:
        """Escaped ``text`` with each genuine origin label (bracketed, one of the memo's forms) in the label style."""
        out, last = [], 0
        for match in _LABEL.finditer(text):
            if not any(form.fullmatch(match.group(1)) for form in FORMS):
                continue
            ink, back = LABEL_COLOURS["ocr" if match.group(1).startswith("OCR") else "label"]
            out.append(self._text(face, text[last : match.start()]))
            shown = match.group(0).replace(" ", "\u00a0")  # a label is never split across lines (the text stays whole when it is read back)
            out.append(f'<font color="{ink}" backColor="{back}">{self._text(face, shown)}</font>')
            last = match.end()
        out.append(self._text(face, text[last:]))
        return "".join(out)

    def inline(self, children: list[Token] | None) -> str:
        """Paragraph markup for inline tokens. Only tags built here appear in it."""
        out, bold, italic = [], 0, 0
        for child in children or []:
            face = fonts.BOLD if bold else fonts.ITALIC if italic else fonts.SANS
            kind = child.type
            if kind == "text":
                out.append(self._label_styled(face, child.content))  # an escaped bracket is a text_special token, never a label
            elif kind == "text_special":
                out.append(self._text(face, child.content))
            elif kind == "softbreak":
                out.append(" ")
            elif kind == "hardbreak":
                out.append("<br/>")
            elif kind == "code_inline":
                out.append(f'<font name="{fonts.MONO}">{self._text(fonts.MONO, child.content)}</font>')
            elif kind == "strong_open":
                bold += 1
                out.append("<b>")
            elif kind == "strong_close":
                bold -= 1
                out.append("</b>")
            elif kind == "em_open":
                italic += 1
                out.append("<i>")
            elif kind == "em_close":
                italic -= 1
                out.append("</i>")
            elif kind in ("link_open", "link_close"):
                continue  # never a link: its text is printed and nothing is loaded
            elif kind == "image":
                out.append(self._text(face, child.content))  # the alt text only; the image is never loaded
            else:  # html_inline and anything unforeseen: printed as plain text
                out.append(self._text(face, child.content or ""))
        return "".join(out)

    def plain(self, children: list[Token] | None) -> str:
        return "".join(c.content for c in children or [] if c.type in ("text", "text_special", "code_inline"))

    # --- blocks ------------------------------------------------------------------------------------------------

    def blocks(self, tokens: list[Token], start: int = 0, end: str | None = None, ctx: str = "body") -> tuple[list[Flowable], int]:
        out: list[Flowable] = []
        i = start
        while i < len(tokens):
            t = tokens[i]
            if t.type == end:
                return out, i + 1
            handler = getattr(self, f"_{t.type}", None)
            if handler is None:
                raise ReportError("render_error")  # a token the memo format does not use
            produced, i = handler(tokens, i, ctx)
            out.extend(produced)
        if end is not None:
            raise ReportError("render_error")
        return out, i

    def _heading_open(self, tokens, i, ctx):
        level = int(tokens[i].tag[1])
        flows: list[Flowable] = [Paragraph(self.inline(tokens[i + 1].children), self.styles["h1" if level == 1 else "h2" if level == 2 else "h3"])]
        if level == 2:
            rule = HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=0, spaceAfter=5)
            rule.keepWithNext = 1  # the heading, its rule and what follows stay together
            flows.append(rule)
        return flows, i + 3

    def _paragraph_open(self, tokens, i, ctx):
        markup = self.inline(tokens[i + 1].children)
        style = {"cell": "cell", "quote": "quote", "banner": "banner", "cover": "cover"}.get(ctx, "body")
        return [Paragraph(markup, self.styles[style])], i + 3

    def _blockquote_open(self, tokens, i, ctx):
        first = not self.quotes_seen and ctx == "body"
        self.quotes_seen = self.quotes_seen or ctx == "body"
        if first:  # the memo's first block quote is its draft statement (K.0)
            level = tokens[i].level
            inside = []
            for t in tokens[i + 1 :]:
                if t.type == "blockquote_close" and t.level == level:
                    break
                if t.type == "inline":
                    inside.append(_COLLAPSED.sub(" ", self.plain(t.children)).strip())
            self.banner = " ".join(inside)
        inner, nxt = self.blocks(tokens, i + 1, "blockquote_close", "banner" if first else "quote")
        return inner, nxt

    def _list(self, tokens, i, ctx, ordered: bool):
        close = "ordered_list_close" if ordered else "bullet_list_close"
        items, j = [], i + 1
        while tokens[j].type != close:
            if tokens[j].type != "list_item_open":
                raise ReportError("render_error")
            inner, j = self.blocks(tokens, j + 1, "list_item_close", ctx)
            items.append(ListItem(inner, leftIndent=14))
        start = tokens[i].attrGet("start") if ordered else None
        flow = ListFlowable(
            items, bulletType="1" if ordered else "bullet", start=int(start) if start is not None else ("1" if ordered else "•"),
            bulletFontName=fonts.SANS, bulletFontSize=9, leftIndent=14, bulletDedent=12, spaceAfter=3, bulletFormat="%s." if ordered else None,
        )  # fmt: skip
        return [flow], j + 1

    def _bullet_list_open(self, tokens, i, ctx):
        return self._list(tokens, i, ctx, False)

    def _ordered_list_open(self, tokens, i, ctx):
        return self._list(tokens, i, ctx, True)

    def _hr(self, tokens, i, ctx):
        return [HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=4, spaceAfter=4)], i + 1

    def _fence(self, tokens, i, ctx):
        self.used.append((fonts.MONO, tokens[i].content))
        return [Preformatted(tokens[i].content.rstrip("\n"), ParagraphStyle("pre", fontName=fonts.MONO, fontSize=7.8, leading=10, textColor=INK))], i + 1

    _code_block = _fence

    def _html_block(self, tokens, i, ctx):
        return [Paragraph(self._text(fonts.SANS, tokens[i].content.strip()), self.styles["body"])], i + 1  # printed, never interpreted

    def _table_open(self, tokens, i, ctx):
        cells: list[list[str]] = []  # the paragraph markup of each cell
        header_rows, j = 0, i + 1
        while tokens[j].type != "table_close":
            if tokens[j].type == "tr_open":
                row, j, head = [], j + 1, False
                while tokens[j].type != "tr_close":
                    head = tokens[j].type == "th_open"
                    row.append(self.inline(tokens[j + 1].children))
                    j += 3
                cells.append(row)
                header_rows += 1 if head else 0
            j += 1
        if not cells or len({len(r) for r in cells}) != 1:
            raise ReportError("render_error")
        size, widths = self._fit(cells)
        body = ParagraphStyle("cell-fit", parent=self.styles["cell"], fontSize=size, leading=size * 1.28)
        head_style = ParagraphStyle("head-fit", parent=self.styles["head"], fontSize=size, leading=size * 1.28)
        rows = [[Paragraph(markup, head_style if r < header_rows else body) for markup in row] for r, row in enumerate(cells)]
        table = Table(rows, colWidths=widths, repeatRows=min(header_rows, 1), hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, min(header_rows, 1) - 1), colors.HexColor("#e9eef3")),
            ("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))  # fmt: skip
        return [table, Spacer(1, 6)], j + 1

    @staticmethod
    def _fit(cells: list[list[str]]) -> tuple[float, list[float]]:
        """The font size and column widths for a table.

        Each column needs the width of its longest word, so an ID or a label is not broken in the middle. The largest size from
        7.8 pt down to 5.6 pt at which every column gets that is used; the rest of the width is shared in proportion to how much text
        a column holds. If even 5.6 pt is not enough, the columns are narrowed in proportion and a word that is still too wide breaks.
        """
        count = len(cells[0])
        texts = [[re.sub(r"<[^>]+>", "", row[c]) for row in cells] for c in range(count)]
        longest = [max((len(w) for t in col for w in t.split(" ")), default=1) for col in texts]  # a label's spaces are non-breaking
        widest = [max(len(t) for t in col) for col in texts]
        padding, floor = 6.5, 10 * mm
        for size in (7.8, 7.2, 6.6, 6.0, 5.6):
            per_char = size * 0.62  # the widest face used (the monospaced one), in points
            needed = [max(floor, n * per_char + padding) for n in longest]
            if sum(needed) <= CONTENT_WIDTH or size == 5.6:
                break
        if sum(needed) >= CONTENT_WIDTH:
            return size, [CONTENT_WIDTH * n / sum(needed) for n in needed]
        # What is left goes first to the columns whose longest cell would otherwise wrap, up to what it takes to print that cell on one line.
        spare = CONTENT_WIDTH - sum(needed)
        deficit = [max(0.0, min(w * per_char + padding, CONTENT_WIDTH * 0.5) - n) for w, n in zip(widest, needed)]
        if sum(deficit) <= spare:
            widths = [n + d for n, d in zip(needed, deficit)]
            rest = spare - sum(deficit)
            return size, [w + rest * n / sum(needed) for w, n in zip(widths, needed)]
        return size, [n + spare * d / sum(deficit) for n, d in zip(needed, deficit)]


def parser() -> MarkdownIt:
    """The memo's CommonMark parser: tables on, and ``text_join`` off so that an escaped bracket stays distinct from a genuine one."""
    return MarkdownIt("commonmark").enable("table").disable("text_join")


def _canvas_class(banner: str, run_id: str) -> type[Canvas]:
    """A canvas that, once the pages are known, draws the footer of every page: the draft statement, the run ID and 'Page n of N'."""

    class Numbered(Canvas):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict] = []

        def showPage(self) -> None:  # noqa: N802 - reportlab's name
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._footer(total)
                super().showPage()
            super().save()

        def _footer(self, total: int) -> None:
            self.setStrokeColor(RULE)
            self.setLineWidth(0.5)
            self.line(MARGIN, 17 * mm, PAGE[0] - MARGIN, 17 * mm)
            self.setFillColor(colors.HexColor("#7a3b00"))
            self.setFont(fonts.BOLD, 7)
            y = 13.2 * mm
            for line in _wrap(banner, fonts.BOLD, 7, CONTENT_WIDTH):
                self.drawString(MARGIN, y, line)
                y -= 8.4
            self.setFillColor(MUTED)
            self.setFont(fonts.SANS, 7)
            self.drawString(MARGIN, 7.5 * mm, f"Run ID {run_id}")
            self.drawRightString(PAGE[0] - MARGIN, 7.5 * mm, f"Page {self._pageNumber} of {total}")

    return Numbered


def _wrap(text: str, face: str, size: float, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(trial, face, size) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    return [*lines, current] if current else lines


def build_pdf(memo: str) -> bytes:
    """The PDF of ``memo``, or ``ReportError`` (``glyph_missing`` or ``render_error``). Document text is never in the error."""
    try:
        tokens = parser().parse(memo)
        typesetter = _Typesetter()
        story, _ = typesetter.blocks(tokens)
        run = _RUN_ID.search(memo)
        if typesetter.banner != DRAFT_STATEMENT or run is None or not story:  # the footer repeats the memo's own draft statement, in its words
            raise ReportError("render_error")
        typesetter.used.append((fonts.BOLD, typesetter.banner))
        typesetter.used.append((fonts.SANS, f"Run ID {run.group(1)} Page of 0123456789"))
        if any(fonts.missing(face, text) for face, text in typesetter.used):
            raise ReportError("glyph_missing")
        out = io.BytesIO()
        doc = BaseDocTemplate(
            out, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=29 * mm,
            title="Draft credit memo", author="", subject=f"Run {run.group(1)}", creator="credit-intel", invariant=1,
        )  # fmt: skip
        doc.addPageTemplates([PageTemplate(id="memo", frames=[Frame(MARGIN, 29 * mm, CONTENT_WIDTH, PAGE[1] - MARGIN - 29 * mm, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)])])  # fmt: skip
        doc.build(story, canvasmaker=_canvas_class(typesetter.banner, run.group(1)))
        return out.getvalue()
    except ReportError:
        raise
    except Exception as exc:
        raise ReportError("render_error") from exc
