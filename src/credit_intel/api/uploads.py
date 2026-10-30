"""Receiving one upload (PRD FR-016 criteria 1 and 6, SEC-14, v0.4.59).

The request body is read as a stream and parsed as it arrives, so the size limit is enforced **while streaming** (and early from
``Content-Length``) and the whole upload is never held in memory. The PDF goes to a private temporary directory (mode 0700, a random name)
and is hashed on the way. The client's file name is **sanitised** to a safe base name and used only as the name of the file inside that
random directory, so that it is the name the manifest records (as the command line records the file's own name); no part of it is ever
joined to a path outside the directory. The directory is removed on any failure here and, by the job, when the run ends.
"""

import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.requests import ClientDisconnect, Request

from credit_intel.ingestion.errors import ErrorCode, IngestionError

SIGNATURE = b"%PDF-"
FIELD_ALLOWANCE = 1024 * 1024  # headers and fields around the file in the body
MAX_FIELD_BYTES = 16 * 1024
MAX_FIELDS = 16
MAX_NAME = 100
_SAFE = re.compile(r"[^A-Za-z0-9._ -]")


@dataclass
class Upload:
    directory: Path
    file: Path
    sha256: str
    size: int
    fields: dict[str, str] = field(default_factory=dict)

    def remove(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)


def safe_name(client_name: str | None) -> str:
    """A base name that is safe as a file name: no directory part, only ``[A-Za-z0-9._ -]``, no leading dot or space, at most 100 characters."""
    name = (client_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _SAFE.sub("_", name).lstrip(". ")[:MAX_NAME].rstrip(". ")
    return name or "upload.pdf"


def _bad() -> IngestionError:
    return IngestionError(ErrorCode.API_REQUEST)


class _Reader:
    """The callbacks of the multipart parser: one ``file`` part goes to disk, every other part is a small text field."""

    def __init__(self, directory: Path, max_file_bytes: int) -> None:
        self.directory, self.max_file_bytes = directory, max_file_bytes
        self.fields: dict[str, bytearray] = {}
        self.file_path: Path | None = None
        self.sha = hashlib.sha256()
        self.size = 0
        self._head = b""
        self._handle = None
        self._header = bytearray()
        self._value = bytearray()
        self._headers: dict[str, str] = {}
        self._target: str | None = None  # "file" or a field name
        self._seen_file = False

    # -- headers
    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def on_header_end(self) -> None:
        self._headers[bytes(self._header).decode("latin-1").lower()] = bytes(self._value).decode("utf-8", "replace")
        self._header, self._value = bytearray(), bytearray()

    def on_headers_finished(self) -> None:
        disposition = self._headers.get("content-disposition", "")
        _, params = parse_options_header(disposition.encode("utf-8"))
        name = params.get(b"name", b"").decode("utf-8", "replace")
        if not name:
            raise _bad()
        if name == "file":
            if self._seen_file or b"filename" not in params:
                raise _bad()
            self._seen_file = True
            self._target = "file"
            self.file_path = self.directory / safe_name(params[b"filename"].decode("utf-8", "replace"))
            self._handle = self.file_path.open("wb")
        else:
            if name in self.fields or len(self.fields) >= MAX_FIELDS or b"filename" in params:
                raise _bad()
            self._target = name
            self.fields[name] = bytearray()
        self._headers = {}

    # -- body
    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if self._target == "file":
            if len(self._head) < len(SIGNATURE):
                self._head += chunk[: len(SIGNATURE) - len(self._head)]
                if len(self._head) == len(SIGNATURE) and self._head != SIGNATURE:
                    raise IngestionError(ErrorCode.NOT_PDF)  # refuse at the first bytes, before the rest is read (and before the size is judged)
            self.size += len(chunk)
            if self.size > self.max_file_bytes:
                raise IngestionError(ErrorCode.TOO_LARGE)
            self.sha.update(chunk)
            self._handle.write(chunk)
        elif self._target is not None:
            buffer = self.fields[self._target]
            buffer += chunk
            if len(buffer) > MAX_FIELD_BYTES:
                raise _bad()

    def on_part_end(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        self._target = None

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()


async def receive_upload(request: Request, max_file_bytes: int) -> Upload:
    """Read ``multipart/form-data`` with one ``file`` and small text fields. Raises ``IngestionError``: ``E-INPUT-TOO-LARGE``, ``E-INPUT-NOT-PDF`` or ``E-API-REQUEST``.

    On any failure the temporary directory is removed before the error leaves.
    """
    content_type, params = parse_options_header(request.headers.get("content-type", "").encode("latin-1", "replace"))
    boundary = params.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise _bad()
    declared = request.headers.get("content-length")
    if declared is not None:
        if not declared.isdigit():
            raise _bad()
        if int(declared) > max_file_bytes + FIELD_ALLOWANCE:
            raise IngestionError(ErrorCode.TOO_LARGE)  # refused from the header, before a byte of the body is read
    directory = Path(tempfile.mkdtemp(prefix="credit-intel-upload-"))
    reader = _Reader(directory, max_file_bytes)
    parser = MultipartParser(boundary, {name: getattr(reader, name) for name in (
        "on_header_field", "on_header_value", "on_header_end", "on_headers_finished", "on_part_data", "on_part_end")},
        max_size=max_file_bytes + FIELD_ALLOWANCE)  # fmt: skip
    try:
        async for chunk in request.stream():
            parser.write(chunk)
        parser.finalize()
        reader.close()
        if reader.file_path is None:
            raise _bad()
        if reader.size < len(SIGNATURE) or reader._head != SIGNATURE:
            raise IngestionError(ErrorCode.NOT_PDF)
        fields = {name: bytes(value).decode("utf-8") for name, value in reader.fields.items()}
    except IngestionError:
        reader.close()
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except ClientDisconnect:
        reader.close()
        shutil.rmtree(directory, ignore_errors=True)
        raise _bad() from None
    except OSError:  # the disk, not the request: an internal error, reported as one
        reader.close()
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception:  # a malformed body (the parser's own errors), a field that is not UTF-8, a disk error
        reader.close()
        shutil.rmtree(directory, ignore_errors=True)
        raise _bad() from None
    return Upload(directory, reader.file_path, reader.sha.hexdigest(), reader.size, fields)
