"""The two charts of the PDF report (PRD FR-015 criterion 4, D-16, v0.4.56; step 4 of its build).

Each chart is first a small list of data, built from ``results.json`` alone (``build_charts``); only then is it drawn (``flowables``),
with reportlab's own graphics (vector, real text, no image). Every number a chart prints is a string that the memo prints too:

* A slot is one field or one metric of one period. Its drawn height is the stored value of that record (a Decimal read as a number for
  drawing only: the chart computes nothing); the number printed on it is **the memo's own displayed string** for that record, made by the
  memo's own functions, and its origin label is the memo's (``[SOURCE: p.N]`` for a field, ``[CALCULATED: id]`` for a metric).
* **Not plotted:** a field whose status is not ``extracted``, any field read by OCR, a metric that is not defined, and a metric any of whose
  inputs is excluded by these rules. The slot says "not plotted" with the memo's own words for why. This is the rule that an OCR value never
  feeds a derived metric, extended to what is drawn.
* No axis carries numbers (a tick label would be a number the memo does not print). A source line under each chart names the records and
  labels that it plots.

``traceability`` checks the data list against the memo and the results: every plotted slot has a row in the memo's tables with the same
ID, the same displayed string and the same label, and its height equals the stored value. ``expected_text`` is the text a chart prints,
for the report check to compare with the PDF.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable, KeepTogether, Paragraph

from credit_intel.memo import sections
from credit_intel.report import fonts
from credit_intel.report.mdparse import plain

COMPARATIVE, CURRENT = "comparative", "current"
TITLE_BARS = "Revenue and net profit, comparative period to current period"
TITLE_DOTS = "Current ratio and interest coverage, comparative period to current period"
HEADING = "Charts"
NOTHING = "Nothing is plotted."
SOURCE_PREFIX = "Plotted:"
BAR_FIELDS = (("revenue", "Revenue"), ("net_profit", "Net profit"))
DOT_METRICS = ("MET-03", "MET-05")


@dataclass(frozen=True)
class Slot:
    """One field or metric of one period: plotted (with ``shown``, ``label`` and ``height``) or not (with ``note``)."""

    role: str
    caption: str  # the period end and the role, as printed under the slot
    record_id: str
    shown: str | None = None  # the memo's displayed string for the record
    label: str | None = None  # the memo's origin label for the record
    height: float | None = None  # the stored value, for drawing only
    note: str | None = None  # "not plotted: ..." when it is not plotted

    @property
    def plotted(self) -> bool:
        return self.height is not None


@dataclass(frozen=True)
class Panel:
    name: str
    slots: tuple[Slot, ...]  # comparative, then current


@dataclass(frozen=True)
class Chart:
    kind: str  # "bars" (one scale for both panels) or "dots" (a scale of its own for each panel)
    title: str
    panels: tuple[Panel, ...]

    def plotted(self) -> list[Slot]:
        return [slot for panel in self.panels for slot in panel.slots if slot.plotted]

    def source_text(self) -> str:
        slots = self.plotted()
        if not slots:
            return NOTHING
        return f"{SOURCE_PREFIX} " + "; ".join(f"{s.record_id} {s.label}" for s in slots)


# --- building the data from the results ---------------------------------------------------------------------------------------------


def _slot_caption(period_end: str | None, role: str) -> str:
    """The period end and the role as printed under a slot; just the role when the run found no period end."""
    return f"{period_end} {role}" if period_end else role


def _records(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["field_id"]: r for r in [*results["fields"], *results["derived_fields"]]}


def _currency(results: dict[str, Any]) -> str | None:
    return (sections._attribute(results, "reporting_currency") or {}).get("normalised_value")


def _usable(record: dict[str, Any]) -> bool:
    return record["status"] == "extracted" and record.get("evidence_source") != "ocr" and record["value"] is not None


def _field_slot(results: dict[str, Any], records: dict[str, dict[str, Any]], name: str, role: str) -> Slot:
    record = next((r for r in records.values() if r["field_name"] == name and r["period_role"] == role), None)
    if record is None:
        return Slot(role, role, f"{name}.{role}", note="not plotted: not found")
    caption = _slot_caption(record.get("period_end"), role)
    if not _usable(record):
        return Slot(role, caption, record["field_id"], note=f"not plotted: {sections.words(record['status'])}")
    return Slot(
        role, caption, record["field_id"], shown=plain(sections._printed(record, _currency(results))), label=plain(sections._field_label(record)),
        height=float(Decimal(record["value"])),
    )  # fmt: skip


def _metric_slot(results: dict[str, Any], records: dict[str, dict[str, Any]], metric_id: str, role: str) -> Slot:
    metric = next((m for m in results["metrics"] if m["metric_id"] == metric_id and m["period_role"] == role), None)
    if metric is None:
        return Slot(role, role, f"{metric_id}.{role}", note="not plotted: not defined")
    caption = _slot_caption((metric.get("period_ends") or [None])[0], role)
    if metric["value"] is None:
        return Slot(role, caption, metric["id"], note=f"not plotted: {plain(sections._metric_value(metric))}")
    if any(i not in records or not _usable(records[i]) for i in metric["input_field_ids"]):  # rests on an excluded value
        return Slot(role, caption, metric["id"], note="not plotted: an input is not verified")
    return Slot(role, caption, metric["id"], shown=plain(sections._metric_value(metric)), label=plain(sections.calculated(metric["id"])), height=float(Decimal(metric["value"])))


def build_charts(results: dict[str, Any]) -> list[Chart]:
    """The two charts of a run, from its ``results.json`` data."""
    records = _records(results)
    bars = Chart("bars", TITLE_BARS, tuple(Panel(label, tuple(_field_slot(results, records, name, role) for role in (COMPARATIVE, CURRENT))) for name, label in BAR_FIELDS))
    names = {m["metric_id"]: m["name"] for m in results["metrics"]}
    dots = Chart("dots", TITLE_DOTS, tuple(Panel(names.get(mid, mid), tuple(_metric_slot(results, records, mid, role) for role in (COMPARATIVE, CURRENT))) for mid in DOT_METRICS))
    return [bars, dots]


# --- what a chart prints, and the check against the memo -----------------------------------------------------------------------------------


def _split_unit(shown: str) -> tuple[str, str | None]:
    """A displayed string as two printed lines: the number, and its unit in brackets if it has one."""
    head, sep, tail = shown.partition(" (")
    return (head, f"({tail}") if sep else (shown, None)


def expected_text(chart: Chart) -> str:
    """Every string that the chart prints (its title, panel names, captions, values, notes and source line)."""
    parts = [chart.title]
    for panel in chart.panels:
        parts.append(panel.name)
        for slot in panel.slots:
            parts.append(slot.caption)
            parts.extend(line for line in (_split_unit(slot.shown) if slot.shown else (slot.note,)) if line)
    parts.append(chart.source_text())
    return "\n".join(parts)


def charts_text(charts: list[Chart]) -> str:
    """Everything the charts section prints: its heading and each chart's text."""
    return "\n".join([HEADING, *(expected_text(chart) for chart in charts)])


def _memo_rows(memo: str, parse) -> list[str]:
    """The plain text of every row of every table of the memo, its cells joined by a bar."""
    rows, cells, inside = [], [], False
    for token in parse(memo):
        if token.type == "tr_open":
            cells, inside = [], True
        elif token.type == "tr_close":
            rows.append(" | ".join(cells))
            inside = False
        elif inside and token.type == "inline":
            cells.append("".join(c.content for c in token.children or []))
    return rows


def traceability(charts: list[Chart], memo: str, results: dict[str, Any], parse) -> list[str]:
    """What is wrong with the charts: a plotted slot with no matching row in the memo's tables, or a height that is not the stored value.

    Messages say which chart and slot by position and never quote the memo.
    """
    problems = []
    rows = _memo_rows(memo, parse)
    records = _records(results)
    metrics = {m["id"]: m for m in results["metrics"]}
    for c, chart in enumerate(charts, start=1):
        for panel in chart.panels:
            for slot in panel.slots:
                if not slot.plotted:
                    continue
                where = f"chart {c}, {slot.role} slot of panel {chart.panels.index(panel) + 1}"
                if not any(slot.record_id in row and slot.shown in row and slot.label in row for row in rows):
                    problems.append(f"{where}: no row of the memo has its ID, its value and its label")
                stored = records[slot.record_id]["value"] if slot.record_id in records else metrics.get(slot.record_id, {}).get("value")
                if stored is None or slot.height != float(Decimal(stored)):
                    problems.append(f"{where}: its height is not the stored value")
    return problems


# --- drawing -------------------------------------------------------------------------------------------------------------------------------


WIDTH = 493.0  # the width of the page's text area (see typeset.CONTENT_WIDTH)
INK, MUTED, GRID = colors.HexColor("#14202e"), colors.HexColor("#5a6877"), colors.HexColor("#c8d0d9")
FILL = {COMPARATIVE: colors.HexColor("#9fb4c9"), CURRENT: colors.HexColor("#1d5c78")}


def _wrap(text: str, size: float, width: float, face: str = fonts.SANS) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(trial, face, size) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    return [*lines, current] if current else lines


def _text(drawing: Drawing, x: float, y: float, text: str, *, size: float = 7, face: str = fonts.SANS, anchor: str = "middle", fill=INK) -> None:
    drawing.add(String(x, y, text, fontName=face, fontSize=size, textAnchor=anchor, fillColor=fill))


def _note(drawing: Drawing, x: float, y: float, text: str, width: float) -> None:
    drawing.add(Rect(x - width / 2, y, width, 30, strokeColor=GRID, strokeDashArray=[2, 2], fillColor=None, strokeWidth=0.6))
    for k, line in enumerate(_wrap(text, 6.2, width - 4)[:3]):
        _text(drawing, x, y + 21 - 7 * k, line, size=6.2, fill=MUTED)


def _caption(drawing: Drawing, x: float, y: float, slot: Slot, width: float) -> None:
    for k, line in enumerate(_wrap(slot.caption, 6.2, width)):
        _text(drawing, x, y - 7 * k, line, size=6.2, fill=MUTED)


def _value(drawing: Drawing, x: float, y: float, shown: str, *, up: bool) -> None:
    number, unit = _split_unit(shown)
    lines = [number, unit] if unit else [number]
    for k, line in enumerate(lines):
        _text(drawing, x, y + (len(lines) - 1 - k) * 7.4 if up else y - 7.4 * k, line, size=6.8, face=fonts.BOLD if k == 0 else fonts.SANS)


def _bars(chart: Chart) -> Drawing:
    height, base_area = 190.0, 78.0
    drawing = Drawing(WIDTH, height)
    heights = [s.height for s in chart.plotted()]
    scale = max((abs(h) for h in heights), default=0.0)
    negative = any(h < 0 for h in heights)
    axis = 50.0 + (base_area * 0.4 if negative else 0.0) + 14
    span = base_area * (0.6 if negative else 1.0)
    for g, panel in enumerate(chart.panels):
        centre = WIDTH * (0.27 + 0.46 * g)
        _text(drawing, centre, height - 12, panel.name, size=8.5, face=fonts.BOLD)
        for k, slot in enumerate(panel.slots):
            x = centre + (-1 if k == 0 else 1) * 40
            if slot.plotted and scale:
                bar = slot.height / scale * span
                drawing.add(Rect(x - 17, axis if bar >= 0 else axis + bar, 34, abs(bar), fillColor=FILL[slot.role], strokeWidth=0))
                _value(drawing, x, axis + bar + 3, slot.shown, up=True) if bar >= 0 else _value(drawing, x, axis + bar - 9, slot.shown, up=False)
            else:
                _note(drawing, x, axis + 4, slot.note or "", 66)
            _caption(drawing, x, axis - 12 - (base_area * 0.4 if negative else 0), slot, 70)
    drawing.add(Line(WIDTH * 0.05, axis, WIDTH * 0.95, axis, strokeColor=GRID, strokeWidth=0.8))
    return drawing


def _dots(chart: Chart) -> Drawing:
    height, base = 128.0, 40.0
    drawing = Drawing(WIDTH, height)
    for p, panel in enumerate(chart.panels):
        left, half = WIDTH * 0.5 * p, WIDTH * 0.5
        _text(drawing, left + half / 2, height - 12, panel.name, size=8.5, face=fonts.BOLD)
        values = [s.height for s in panel.slots if s.plotted]
        low, high = min([0.0, *values]), max([0.0, *values])
        span = (high - low) or 1.0
        area = 56.0
        y = lambda v: base + (v - low) / span * area  # noqa: E731 - drawing position only
        drawing.add(Line(left + half * 0.12, y(0.0), left + half * 0.88, y(0.0), strokeColor=GRID, strokeWidth=0.8))
        points = []
        for k, slot in enumerate(panel.slots):
            x = left + half * (0.32 if k == 0 else 0.68)
            if slot.plotted:
                points.append((x, y(slot.height)))
                drawing.add(Rect(x - 3, y(slot.height) - 3, 6, 6, fillColor=FILL[slot.role], strokeWidth=0))
                _text(drawing, x, y(slot.height) + 7, slot.shown, size=7.2, face=fonts.BOLD)
            else:
                _note(drawing, x, base + 8, slot.note or "", 70)
            _caption(drawing, x, base - 12, slot, 74)
        if len(points) == 2:
            drawing.add(Line(*points[0], *points[1], strokeColor=MUTED, strokeWidth=0.7))
    return drawing


def flowables(charts: list[Chart], styles: dict[str, Any], label_styled) -> tuple[list[Flowable], list[tuple[str, str]]]:
    """The charts as page elements, and the (face, text) pairs they print, for the font check.

    ``label_styled(face, text)`` is the typesetter's escaping and label styling for the source line, so that a label there is styled
    as it is everywhere else and the text is escaped like all text.
    """
    out: list[Flowable] = [Paragraph(HEADING, styles["h2"])]
    printed: list[tuple[str, str]] = [(fonts.BOLD, HEADING)]
    for chart in charts:
        parts = [Paragraph(label_styled(fonts.BOLD, chart.title), styles["h3"]), _bars(chart) if chart.kind == "bars" else _dots(chart)]
        parts.append(Paragraph(label_styled(fonts.SANS, chart.source_text()), styles["cell"]))
        out.append(KeepTogether(parts))
        printed.append((fonts.SANS, expected_text(chart)))
    return out, printed
