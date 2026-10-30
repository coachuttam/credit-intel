"""The memo's CommonMark parser and a helper to read a Markdown string as plain text (shared by the typesetter, the charts and the check)."""

from markdown_it import MarkdownIt


def parser() -> MarkdownIt:
    """The memo's CommonMark parser: tables on, and ``text_join`` off so that an escaped bracket stays distinct from a genuine one."""
    return MarkdownIt("commonmark").enable("table").disable("text_join")


def plain(markdown: str) -> str:
    """``markdown`` (a short inline string, as the memo's functions write it) as the text a reader sees: escapes resolved, code marks gone."""
    tokens = parser().parseInline(markdown)
    return "".join(child.content for token in tokens for child in token.children or [])
