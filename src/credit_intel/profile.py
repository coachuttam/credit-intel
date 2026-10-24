"""The analyst's borrower profile (PRD FR-014.7; Phase 5 step 5b).

A profile is a small JSON object with up to four optional keys, ``borrower_name``, ``industry``,
``facility_requested`` and ``notes``, each a string of at most 500 characters. Its values appear
only in memo section 1, labelled ``[ANALYST-PROVIDED]``. They are never financial evidence, never an
input to a calculation and never an input to a risk rule: nothing in the extraction, calculation or
risk packages imports this module (a test checks).

Anything else is refused with ``E-INPUT-PROFILE-INVALID``: a file that cannot be read, is too large,
is not UTF-8 or not valid JSON; a value that is not an object; an unknown key; a repeated key; a
value that is not a string; or one longer than 500 characters. The detail names the problem and, for
a known key, the key. It never echoes a value or an unknown key.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from credit_intel.ingestion.errors import ErrorCode, IngestionError

PROFILE_KEYS = ("borrower_name", "industry", "facility_requested", "notes")
MAX_VALUE_CHARACTERS = 500
MAX_FILE_BYTES = 64 * 1024  # four values of 500 characters need far less; a larger file is not a profile
LABEL = "[ANALYST-PROVIDED]"


@dataclass(frozen=True)
class Profile:
    file_name: str  # the file's name only, for the manifest (FR-012.1)
    borrower_name: str | None = None
    industry: str | None = None
    facility_requested: str | None = None
    notes: str | None = None

    def items(self) -> tuple[tuple[str, str], ...]:
        """The values that were supplied, in the fixed key order."""
        return tuple((key, getattr(self, key)) for key in PROFILE_KEYS if getattr(self, key) is not None)


def _invalid(detail: str) -> IngestionError:
    return IngestionError(ErrorCode.PROFILE_INVALID, detail)


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key")
        seen[key] = value
    return seen


def load_profile(path: Path) -> Profile:
    """Read and validate a profile file. Raises ``IngestionError`` (``E-INPUT-PROFILE-INVALID``)."""
    try:
        if not path.is_file():
            raise OSError("not a regular file")
        raw = path.read_bytes() if path.stat().st_size <= MAX_FILE_BYTES else None
    except OSError as exc:
        raise _invalid("the file cannot be read") from exc
    if raw is None:
        raise _invalid(f"the file is larger than {MAX_FILE_BYTES} bytes")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except UnicodeDecodeError as exc:
        raise _invalid("the file is not UTF-8") from exc
    except ValueError as exc:  # json.JSONDecodeError, and the duplicate-key check
        raise _invalid("the file is not valid JSON or repeats a key") from exc
    if not isinstance(data, dict):
        raise _invalid("the profile must be a JSON object")
    if any(key not in PROFILE_KEYS for key in data):
        raise _invalid("the profile has a key that is not allowed")
    for key, value in data.items():
        if not isinstance(value, str):
            raise _invalid(f"the value of {key} is not a string")
        if len(value) > MAX_VALUE_CHARACTERS:
            raise _invalid(f"the value of {key} is longer than {MAX_VALUE_CHARACTERS} characters")
    return Profile(path.name, **data)
