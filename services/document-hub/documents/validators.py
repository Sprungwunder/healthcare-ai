"""Business rules shared by the service layer, the REST API and the web forms.

Everything here raises `django.core.exceptions.ValidationError` with a stable
`code`, so callers can map errors (e.g. the API turns `file_too_large` into 413).
Only the standard library is used to inspect file contents.
"""

import datetime
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath
from typing import IO, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

# Error codes (part of the API contract).
FILE_EMPTY = "file_empty"
FILE_TOO_LARGE = "file_too_large"
FILE_TYPE_NOT_ALLOWED = "unsupported_file_type"
FILE_CONTENT_MISMATCH = "file_content_mismatch"
DUPLICATE_FILE = "duplicate_file"
TAG_INVALID = "tag_invalid"
TOO_MANY_TAGS = "too_many_tags"
DATE_IN_FUTURE = "date_in_future"
BLANK = "blank"

TAG_MAX_LENGTH = 50
MAX_TAGS = 20

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

#: Allowed file extensions and the MIME type stored for them.
ALLOWED_FILE_TYPES: dict[str, str] = {
    "pdf": PDF_MIME,
    "docx": DOCX_MIME,
    "txt": "text/plain",
    "md": "text/markdown",
}

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class DetectedFileType:
    extension: str
    mime_type: str


def max_upload_size() -> int:
    return int(settings.DOCUMENT_HUB_MAX_UPLOAD_SIZE)


def format_size(num_bytes: int) -> str:
    """Human-readable size with a German decimal comma, e.g. "10,5 MB"."""
    for unit, factor in (("MB", 1024 * 1024), ("KB", 1024)):
        if num_bytes >= factor:
            value = f"{num_bytes / factor:.1f}".removesuffix(".0").replace(".", ",")
            return f"{value} {unit}"
    return f"{num_bytes} Bytes"


def validate_file_size(file: Any) -> None:
    size = int(file.size or 0)
    if size == 0:
        raise ValidationError("Die Datei ist leer.", code=FILE_EMPTY)
    limit = max_upload_size()
    if size > limit:
        raise ValidationError(
            "Die Datei ist zu groß (%(size)s). Erlaubt sind höchstens %(limit)s.",
            code=FILE_TOO_LARGE,
            params={"size": format_size(size), "limit": format_size(limit)},
        )


def file_extension(filename: str) -> str:
    return PurePath(filename).suffix.lower().lstrip(".")


def _read_head(stream: IO[bytes], length: int) -> bytes:
    stream.seek(0)
    head = stream.read(length)
    stream.seek(0)
    return head


def _is_pdf(stream: IO[bytes]) -> bool:
    return _read_head(stream, 5) == b"%PDF-"


def _is_docx(stream: IO[bytes]) -> bool:
    stream.seek(0)
    try:
        with zipfile.ZipFile(stream) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False
    finally:
        stream.seek(0)


def _is_utf8_text(stream: IO[bytes]) -> bool:
    stream.seek(0)
    try:
        data = stream.read()
        if b"\x00" in data:
            return False
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    finally:
        stream.seek(0)
    return True


_CONTENT_CHECKS = {
    "pdf": _is_pdf,
    "docx": _is_docx,
    "txt": _is_utf8_text,
    "md": _is_utf8_text,
}


def detect_file_type(file: Any) -> DetectedFileType:
    """Check extension and content of `file` and return its type.

    The content must match the extension, so a renamed file can't pass as an
    allowed type (e.g. an EXE renamed to `.pdf`).
    """
    extension = file_extension(file.name or "")
    if extension not in ALLOWED_FILE_TYPES:
        raise ValidationError(
            "Dateityp „%(extension)s“ ist nicht erlaubt. Erlaubt sind: %(allowed)s.",
            code=FILE_TYPE_NOT_ALLOWED,
            params={
                "extension": extension or "ohne Endung",
                "allowed": ", ".join(e.upper() for e in ALLOWED_FILE_TYPES),
            },
        )
    if not _CONTENT_CHECKS[extension](file):
        raise ValidationError(
            "Der Inhalt der Datei passt nicht zur Endung „.%(extension)s“.",
            code=FILE_CONTENT_MISMATCH,
            params={"extension": extension},
        )
    return DetectedFileType(
        extension=extension, mime_type=ALLOWED_FILE_TYPES[extension]
    )


def validate_upload(file: Any) -> DetectedFileType:
    """All file rules: size first (cheap), then type and content."""
    validate_file_size(file)
    return detect_file_type(file)


def normalize_tag(name: str) -> str:
    """Trim, collapse inner whitespace and lowercase a tag name."""
    return _WHITESPACE.sub(" ", name).strip().lower()


def validate_tag_name(name: str) -> None:
    if not 1 <= len(name) <= TAG_MAX_LENGTH:
        raise ValidationError(
            "Ein Tag muss 1 bis %(max)d Zeichen lang sein.",
            code=TAG_INVALID,
            params={"max": TAG_MAX_LENGTH},
        )


def split_tags(value: str | Iterable[str]) -> list[str]:
    """Accept "a, b" or ["a", "b, c"] and return the raw, unnormalized parts."""
    items = [value] if isinstance(value, str) else list(value)
    return [part for item in items for part in str(item).split(",")]


def normalize_tags(names: str | Iterable[str]) -> list[str]:
    """Normalize, de-duplicate (keeping order) and validate a list of tags.

    Empty entries (e.g. from "a,,b") are dropped.
    """
    result: list[str] = []
    for raw in split_tags(names):
        name = normalize_tag(raw)
        if not name:
            continue
        validate_tag_name(name)
        if name not in result:
            result.append(name)
    if len(result) > MAX_TAGS:
        raise ValidationError(
            "Höchstens %(max)d Tags pro Dokument.",
            code=TOO_MANY_TAGS,
            params={"max": MAX_TAGS},
        )
    return result


def validate_not_in_future(value: datetime.date | None) -> None:
    if value is not None and value > timezone.localdate():
        raise ValidationError(
            "Das Datum darf nicht in der Zukunft liegen.", code=DATE_IN_FUTURE
        )


def validate_not_blank(value: str) -> None:
    if not value.strip():
        raise ValidationError("Dieses Feld darf nicht leer sein.", code=BLANK)
