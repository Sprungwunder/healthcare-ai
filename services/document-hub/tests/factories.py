"""Builders for synthetic test files and documents. No real data."""

import io
import itertools
import zipfile
from typing import Any

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile

from documents import services
from documents.models import Document, DocumentType, Language

_counter = itertools.count(1)


def unique_text(prefix: str = "Synthetic test document") -> bytes:
    return f"{prefix} #{next(_counter)}\n".encode()


def txt_file(
    name: str = "note.txt", content: bytes | None = None
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content or unique_text(), "text/plain")


def md_file(name: str = "note.md", content: bytes | None = None) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name, content or b"# Title\n\n" + unique_text(), "text/markdown"
    )


def pdf_file(name: str = "protocol.pdf") -> SimpleUploadedFile:
    body = b"%PDF-1.4\n% synthetic\n" + unique_text() + b"%%EOF\n"
    return SimpleUploadedFile(name, body, "application/pdf")


def docx_bytes(include_document_xml: bool = True) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        if include_document_xml:
            archive.writestr(
                "word/document.xml",
                "<w:document>" + unique_text().decode() + "</w:document>",
            )
    return buffer.getvalue()


def docx_file(name: str = "manual.docx") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, docx_bytes(), "application/octet-stream")


def make_document(**overrides: Any) -> Document:
    data: dict[str, Any] = {
        "file": txt_file(),
        "title": f"Test document {next(_counter)}",
        "document_type": DocumentType.SOP,
        "source": "Synthetic Lab",
        "language": Language.GERMAN,
        "tags": [],
    }
    data.update(overrides)
    return services.create_document(**data)


def make_user(username: str, role: str | None = None, **extra: Any) -> User:
    user = User.objects.create_user(username=username, password="pw", **extra)
    if role is not None:
        user.groups.add(Group.objects.get(name=role))
    return user
