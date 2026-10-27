"""The embedded fonts of the PDF report (PRD FR-015 criterion 10, D-16): DejaVu Sans, free to redistribute (see ``fonts/LICENSE``).

reportlab's built-in fonts cannot print the rupee sign or typographic quotes, so the report embeds DejaVu. A character that the font
lacks is reported (``missing``), never printed as a blank box: the report is then not written (``glyph_missing``).
"""

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).resolve().parent / "fonts"
SANS, BOLD, ITALIC, MONO = "CI-Sans", "CI-Sans-Bold", "CI-Sans-Italic", "CI-Mono"
_FILES = {SANS: "DejaVuSans.ttf", BOLD: "DejaVuSans-Bold.ttf", ITALIC: "DejaVuSans-Oblique.ttf", MONO: "DejaVuSansMono.ttf"}
_registered = False


def register() -> None:
    """Register the four faces and the Sans family with reportlab (once)."""
    global _registered
    if _registered:
        return
    for name, file in _FILES.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    pdfmetrics.registerFontFamily(SANS, normal=SANS, bold=BOLD, italic=ITALIC, boldItalic=BOLD)
    _registered = True


def missing(font: str, text: str) -> set[str]:
    """The characters of ``text`` that ``font`` cannot print. Spaces and line breaks are always fine."""
    register()
    glyphs = pdfmetrics.getFont(font).face.charToGlyph
    return {ch for ch in text if ch not in " \n\t" and ord(ch) not in glyphs}
