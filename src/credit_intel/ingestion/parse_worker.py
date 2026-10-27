"""The parse worker (PRD SEC-12, FR-001 criterion 10): the PDF libraries run here, in a process the parent can stop.

    python -m credit_intel.ingestion.parse_worker <operation> <pdf> <output.json> [<memory_mb>] [<page numbers, JSON>]

It runs one operation of ``PdfplumberExtractor`` (``inspect``, ``extract_pages``, ``extract_words``, ``image_coverage``), opens the
PDF read-only, and writes the result, or the catalogued error code, to the output file as JSON. It writes nothing else: no document
text reaches a log, the standard streams or an error message. The file is the channel (not a pipe) so a large result cannot block
the worker while the parent is watching it. The parent turns a missing output or a non-zero exit into ``E-INPUT-CORRUPT``.

A ``render_page`` operation (PRD SEC-12 step 2) renders one page for OCR with pypdfium2 and sends the PNG on the standard output, so the image
is never written to a file (FR-001A.6): one header line of JSON, then the PNG bytes. Its argument list is
``render_page <pdf> - <memory_mb> {"page": N, "dpi": D}``.

On Linux the worker also asks the system for an address-space limit as a backstop (``BACKSTOP_FACTOR`` times the memory limit,
because address space exceeds resident memory). The parent's resident-memory check is the stated mechanism on every platform:
macOS cannot enforce such a limit.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.models import PageImageCoverage, PageText, PageWords, PdfInspection, Word

OPERATIONS = ("inspect", "extract_pages", "extract_words", "image_coverage")
RENDER = "render_page"
BACKSTOP_FACTOR = 2


def set_address_space_backstop(memory_mb: int, platform: str = sys.platform, setrlimit=None) -> bool:
    """Ask for ``RLIMIT_AS`` of ``BACKSTOP_FACTOR`` x ``memory_mb`` on Linux; never raise. Returns whether a limit was set."""
    if not platform.startswith("linux"):
        return False
    try:
        if setrlimit is None:
            import resource

            def setrlimit(limit: int) -> None:
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

        setrlimit(BACKSTOP_FACTOR * memory_mb * 1024 * 1024)
    except (ImportError, OSError, ValueError):
        return False
    return True


def to_jsonable(operation: str, result: object) -> object:
    if operation == "inspect":
        return asdict(result)  # type: ignore[call-overload]
    return [asdict(item) for item in result]  # type: ignore[attr-defined, call-overload]


def from_jsonable(operation: str, data: object):
    """The inverse of ``to_jsonable``; a malformed result raises ``ValueError``/``TypeError``/``KeyError``."""
    if operation == "inspect":
        return PdfInspection(**data)  # type: ignore[arg-type]
    items = list(data)  # type: ignore[call-overload]
    if operation == "extract_pages":
        return [PageText(**item) for item in items]
    if operation == "image_coverage":
        return [PageImageCoverage(**item) for item in items]
    if operation == "extract_words":
        return [PageWords(**{**item, "words": tuple(Word(**w) for w in item["words"])}) for item in items]
    raise ValueError("unknown operation")


def render_main(pdf: Path, memory_mb: int, request: dict) -> int:
    """Render one page and write ``header line + PNG`` to the standard output."""
    set_address_space_backstop(memory_mb)
    from credit_intel.ingestion.tesseract_ocr import open_document, render_page_png

    out = sys.stdout.buffer
    try:
        document = open_document(pdf)
        try:
            png, width, height = render_page_png(document, request["page"], request["dpi"])
        finally:
            document.close()
        header: dict = {"ok": True, "width": width, "height": height}
    except IngestionError as error:
        out.write(json.dumps({"ok": False, "code": error.code.value}).encode() + b"\n")
        return 0
    except MemoryError:
        out.write(json.dumps({"ok": False, "memory": True}).encode() + b"\n")
        return 0
    out.write(json.dumps(header).encode() + b"\n" + png)
    out.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) >= 5 and args[0] == RENDER:
        return render_main(Path(args[1]), int(args[3]), json.loads(args[4]))
    if len(args) < 3 or args[0] not in OPERATIONS:
        return 2
    operation, pdf, output = args[0], Path(args[1]), Path(args[2])
    if len(args) > 3:
        set_address_space_backstop(int(args[3]))
    from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

    extractor = PdfplumberExtractor()
    try:
        if operation == "extract_words":
            result = extractor.extract_words(pdf, json.loads(args[4]))
        else:
            result = getattr(extractor, operation)(pdf)
        payload: dict = {"ok": True, "result": to_jsonable(operation, result)}
    except IngestionError as error:  # a catalogued failure: the code only, never a detail
        payload = {"ok": False, "code": error.code.value}
    except MemoryError:
        payload = {"ok": False, "memory": True}
    output.write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
