"""The environment of a child process that reads a document (PRD SEC-02, SEC-06; Phase 7 step 1, finding F-1).

The parse worker, the page-render worker, Tesseract and the report worker each handle bytes that came from outside. None of them needs the model key, the API
token or any other secret, and a flaw in a parser must not be able to hand one over. Each is started with **only the variables on the list below**, copied from
the parent; everything else is dropped, whatever its name. The list is what an interpreter, a shared library or Tesseract needs to start and to find its data:
no proxy, cloud or credential variable is on it, and nothing is allowed by pattern.
"""

import os
from collections.abc import Mapping

ALLOWED = (
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TMPDIR", "TMP", "TEMP", "HOME",
    "PYTHONPATH", "PYTHONHOME", "PYTHONUTF8", "PYTHONIOENCODING", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE",
    "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "TESSDATA_PREFIX", "OMP_THREAD_LIMIT",
)  # fmt: skip


def child_environment(source: Mapping[str, str] | None = None, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """``source`` (the process environment by default) reduced to ``ALLOWED``, then ``overrides`` set on top (they are the caller's own, fixed values)."""
    given = os.environ if source is None else source
    environment = {name: given[name] for name in ALLOWED if name in given}
    environment.update(overrides or {})
    return environment
