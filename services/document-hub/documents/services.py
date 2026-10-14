"""Business logic for documents. API and web views call only these functions.

All writes run in a transaction. Files are written to storage before the
database row; if the transaction fails, the new file is removed again. Files
that become obsolete (replaced or deleted) are removed only after commit.
"""

import datetime
import hashlib
import logging
from collections.abc import Iterable
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.storage import Storage
from django.db import IntegrityError, transaction

from documents import signals
from documents.models import Document, ProcessingStatus, Tag
from documents.validators import (
    DUPLICATE_FILE,
    DetectedFileType,
    normalize_tags,
    validate_upload,
)

logger = logging.getLogger(__name__)

#: Metadata fields that `update_document` accepts.
EDITABLE_FIELDS = frozenset(
    {"title", "document_type", "source", "source_url", "published_on", "language"}
)


def compute_checksum(file: File) -> str:
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()


def _check_duplicate(checksum: str, exclude: Document | None = None) -> None:
    existing = Document.objects.filter(checksum_sha256=checksum)
    if exclude is not None:
        existing = existing.exclude(pk=exclude.pk)
    duplicate = existing.only("id", "title").first()
    if duplicate is not None:
        raise _duplicate_error(duplicate)


def _duplicate_error(duplicate: Document | None) -> ValidationError:
    if duplicate is None:
        message = "Diese Datei ist bereits als Dokument vorhanden."
        params: dict[str, Any] = {}
    else:
        message = "Diese Datei ist bereits als Dokument „%(title)s“ (%(id)s) vorhanden."
        params = {"title": duplicate.title, "id": str(duplicate.pk)}
    return ValidationError(
        {"file": [ValidationError(message, code=DUPLICATE_FILE, params=params)]}
    )


def _set_file_metadata(
    document: Document, file: File, detected: DetectedFileType, checksum: str
) -> None:
    original_name = str(file.name).replace("\\", "/").rsplit("/", 1)[-1]
    document.original_filename = original_name[:255]
    document.mime_type = detected.mime_type
    document.file_size = int(file.size)
    document.checksum_sha256 = checksum
    document.processing_status = ProcessingStatus.PENDING


def _store_file(document: Document, file: File, detected: DetectedFileType) -> str:
    """Write the file under `document_upload_to` and return its storage name."""
    document.file.save(f"upload.{detected.extension}", file, save=False)
    return document.file.name or ""


def _full_clean(document: Document) -> None:
    # The file itself is validated by `validate_upload`, duplicates by
    # `_check_duplicate` (with a clearer message than the unique check).
    document.full_clean(exclude=["file", "checksum_sha256"])


def _set_tags(document: Document, names: Iterable[str]) -> None:
    tags = [Tag.objects.get_or_create(name=name)[0] for name in names]
    document.tags.set(tags)


def _delete_file_on_commit(storage: Storage, name: str) -> None:
    def delete() -> None:
        try:
            storage.delete(name)
        except OSError:
            logger.warning("Could not delete obsolete document file %s", name)

    transaction.on_commit(delete)


def _remove_unsaved_file(storage: Storage, name: str) -> None:
    if name:
        storage.delete(name)


def _discard_new_file(
    document: Document, storage: Storage, new_name: str, old_name: str
) -> None:
    if new_name:
        storage.delete(new_name)
        document.file.name = old_name


def create_document(
    *,
    file: File,
    title: str,
    document_type: str,
    source: str,
    language: str,
    source_url: str = "",
    published_on: datetime.date | None = None,
    tags: Iterable[str] = (),
    created_by: AbstractBaseUser | None = None,
) -> Document:
    """Validate and store a new document. Raises `ValidationError`."""
    detected = validate_upload(file)
    tag_names = normalize_tags(tags)
    checksum = compute_checksum(file)
    _check_duplicate(checksum)

    document = Document(
        title=title.strip(),
        document_type=document_type,
        source=source.strip(),
        source_url=source_url,
        published_on=published_on,
        language=language,
        created_by=created_by,  # type: ignore[misc]
    )
    _set_file_metadata(document, file, detected, checksum)
    _full_clean(document)

    stored_name = _store_file(document, file, detected)
    try:
        with transaction.atomic():
            document.save()
            _set_tags(document, tag_names)
            transaction.on_commit(
                lambda: signals.document_created.send(
                    sender=Document, document=document
                )
            )
    except IntegrityError as exc:
        # Lost a race against a concurrent upload of the same file.
        _remove_unsaved_file(document.file.storage, stored_name)
        raise _duplicate_error(
            Document.objects.filter(checksum_sha256=checksum).first()
        ) from exc
    except BaseException:
        _remove_unsaved_file(document.file.storage, stored_name)
        raise
    return document


def update_document(
    document: Document,
    *,
    file: File | None = None,
    tags: Iterable[str] | None = None,
    **fields: Any,
) -> Document:
    """Update metadata and optionally replace the file. Raises `ValidationError`.

    Only the given fields change. Replacing the file resets the processing
    status to `pending`; the old file is deleted after commit.
    """
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise TypeError(f"Unknown document fields: {', '.join(sorted(unknown))}")

    tag_names = normalize_tags(tags) if tags is not None else None
    for name, value in fields.items():
        if name in {"title", "source"} and isinstance(value, str):
            value = value.strip()
        setattr(document, name, value)

    detected: DetectedFileType | None = None
    if file is not None:
        detected = validate_upload(file)
        checksum = compute_checksum(file)
        _check_duplicate(checksum, exclude=document)
        _set_file_metadata(document, file, detected, checksum)
    _full_clean(document)

    storage = document.file.storage
    old_name = document.file.name or ""
    new_name = ""
    if file is not None and detected is not None:
        new_name = _store_file(document, file, detected)
    try:
        with transaction.atomic():
            document.save()
            if tag_names is not None:
                _set_tags(document, tag_names)
            if new_name and old_name and old_name != new_name:
                _delete_file_on_commit(storage, old_name)
            file_replaced = bool(new_name)
            transaction.on_commit(
                lambda: signals.document_updated.send(
                    sender=Document, document=document, file_replaced=file_replaced
                )
            )
    except IntegrityError as exc:
        _discard_new_file(document, storage, new_name, old_name)
        raise _duplicate_error(None) from exc
    except BaseException:
        _discard_new_file(document, storage, new_name, old_name)
        raise
    return document


def delete_document(document: Document) -> None:
    """Delete the document permanently, including its file (after commit)."""
    document_id = document.pk
    storage = document.file.storage
    file_name = document.file.name or ""
    with transaction.atomic():
        document.delete()
        if file_name:
            _delete_file_on_commit(storage, file_name)
        transaction.on_commit(
            lambda: signals.document_deleted.send(
                sender=Document, document_id=document_id
            )
        )
