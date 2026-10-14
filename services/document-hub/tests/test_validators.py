import datetime

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from pytest_django.fixtures import Settings

from documents import validators as v
from tests import factories


def _code(exc: pytest.ExceptionInfo[ValidationError]) -> str | None:
    return exc.value.code


class TestFileSize:
    def test_empty_file_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            v.validate_upload(SimpleUploadedFile("empty.txt", b""))
        assert _code(exc) == v.FILE_EMPTY

    def test_default_limit_is_10_mb(self, settings: Settings) -> None:
        assert v.max_upload_size() == 10 * 1024 * 1024

    def test_file_at_limit_is_accepted(self, settings: Settings) -> None:
        settings.DOCUMENT_HUB_MAX_UPLOAD_SIZE = 16
        v.validate_file_size(SimpleUploadedFile("a.txt", b"x" * 16))

    def test_file_over_configured_limit_is_rejected(self, settings: Settings) -> None:
        settings.DOCUMENT_HUB_MAX_UPLOAD_SIZE = 16
        with pytest.raises(ValidationError) as exc:
            v.validate_upload(SimpleUploadedFile("a.txt", b"x" * 17))
        assert _code(exc) == v.FILE_TOO_LARGE
        assert "16 bytes" in exc.value.messages[0]

    def test_over_default_limit_is_rejected(self) -> None:
        big = SimpleUploadedFile("a.txt", b"x" * (10 * 1024 * 1024 + 1))
        with pytest.raises(ValidationError) as exc:
            v.validate_file_size(big)
        assert "10 MB" in exc.value.messages[0]

    @pytest.mark.parametrize(
        ("size", "text"),
        [(512, "512 bytes"), (2048, "2 KB"), (1536, "1.5 KB"), (5 * 1024**2, "5 MB")],
    )
    def test_format_size(self, size: int, text: str) -> None:
        assert v.format_size(size) == text


class TestFileType:
    @pytest.mark.parametrize(
        ("upload", "extension", "mime"),
        [
            (factories.pdf_file(), "pdf", "application/pdf"),
            (factories.docx_file(), "docx", v.DOCX_MIME),
            (factories.txt_file(), "txt", "text/plain"),
            (factories.md_file(), "md", "text/markdown"),
            (factories.pdf_file("GROSS.PDF"), "pdf", "application/pdf"),
        ],
    )
    def test_allowed_types(
        self, upload: SimpleUploadedFile, extension: str, mime: str
    ) -> None:
        detected = v.validate_upload(upload)
        assert detected == v.DetectedFileType(extension, mime)
        assert upload.tell() == 0

    @pytest.mark.parametrize("name", ["image.png", "program.exe", "no_extension"])
    def test_disallowed_extensions(self, name: str) -> None:
        with pytest.raises(ValidationError) as exc:
            v.validate_upload(SimpleUploadedFile(name, b"data"))
        assert _code(exc) == v.FILE_TYPE_NOT_ALLOWED

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("fake.pdf", b"MZ\x90\x00 not a pdf"),
            ("fake.docx", b"plain text, not a zip"),
            ("fake.docx", factories.docx_bytes(include_document_xml=False)),
            ("fake.txt", b"\xff\xfe\xfa invalid utf-8"),
            ("fake.md", b"binary\x00data"),
        ],
    )
    def test_forged_content_is_rejected(self, name: str, content: bytes) -> None:
        with pytest.raises(ValidationError) as exc:
            v.validate_upload(SimpleUploadedFile(name, content))
        assert _code(exc) == v.FILE_CONTENT_MISMATCH


class TestTags:
    def test_normalize_tag(self) -> None:
        assert v.normalize_tag("  Klinische   Chemie\t") == "klinische chemie"

    def test_normalize_tags_splits_dedupes_and_drops_empty(self) -> None:
        assert v.normalize_tags("Ångström, ,ångström,  PCR ") == [
            "ångström",
            "pcr",
        ]
        assert v.normalize_tags(["a, b", "c"]) == ["a", "b", "c"]

    def test_tag_too_long(self) -> None:
        with pytest.raises(ValidationError) as exc:
            v.normalize_tags(["x" * 51])
        assert _code(exc) == v.TAG_INVALID
        assert v.normalize_tags(["x" * 50]) == ["x" * 50]

    def test_too_many_tags(self) -> None:
        v.normalize_tags([f"t{i}" for i in range(20)])
        with pytest.raises(ValidationError) as exc:
            v.normalize_tags([f"t{i}" for i in range(21)])
        assert _code(exc) == v.TOO_MANY_TAGS


class TestDatesAndText:
    def test_today_and_past_are_valid(self) -> None:
        v.validate_not_in_future(None)
        v.validate_not_in_future(timezone.localdate())
        v.validate_not_in_future(datetime.date(2000, 1, 1))

    def test_future_date_is_rejected(self) -> None:
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        with pytest.raises(ValidationError) as exc:
            v.validate_not_in_future(tomorrow)
        assert _code(exc) == v.DATE_IN_FUTURE

    def test_blank_text(self) -> None:
        with pytest.raises(ValidationError):
            v.validate_not_blank("   ")
        v.validate_not_blank("SOP")
