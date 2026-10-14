import datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import IntegrityError
from django.utils import timezone
from pytest_django.fixtures import DjangoCaptureOnCommitCallbacks

from documents import services, signals
from documents.models import Document, DocumentType, Language, ProcessingStatus, Tag
from documents.validators import DUPLICATE_FILE, FILE_CONTENT_MISMATCH
from tests import factories

pytestmark = pytest.mark.django_db


def _stored_files(media_root: Path) -> list[Path]:
    return (
        [p for p in media_root.rglob("*") if p.is_file()] if media_root.exists() else []
    )


class SignalRecorder:
    def __init__(self, signal: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        signal.connect(self, weak=False)
        self._signal = signal

    def __call__(self, sender: Any, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    def disconnect(self) -> None:
        self._signal.disconnect(self)


@pytest.fixture
def recorder() -> Any:
    created: list[SignalRecorder] = []

    def make(signal: Any) -> SignalRecorder:
        rec = SignalRecorder(signal)
        created.append(rec)
        return rec

    yield make
    for rec in created:
        rec.disconnect()


class TestCreate:
    def test_creates_document_with_derived_file_metadata(
        self, media_root: Path
    ) -> None:
        upload = factories.pdf_file("Befund Labor.pdf")
        document = factories.make_document(
            file=upload,
            title="  Laborprotokoll Blutbild ",
            document_type=DocumentType.LAB_PROTOCOL,
            language=Language.ENGLISH,
            tags=["Hämatologie", " blutbild ", "hämatologie"],
            published_on=datetime.date(2024, 5, 1),
            source_url="https://example.org/sop",
        )
        document.refresh_from_db()
        assert document.title == "Laborprotokoll Blutbild"
        assert document.original_filename == "Befund Labor.pdf"
        assert document.mime_type == "application/pdf"
        assert document.file_size == upload.size
        assert len(document.checksum_sha256) == 64
        assert document.processing_status == ProcessingStatus.PENDING
        assert sorted(document.tag_names()) == ["blutbild", "hämatologie"]
        name = document.file.name or ""
        assert name.startswith("documents/")
        assert name.endswith(f"{document.id}.pdf")
        assert len(_stored_files(media_root)) == 1

    def test_reuses_existing_tags(self) -> None:
        factories.make_document(tags=["pcr"])
        factories.make_document(tags=["PCR"])
        assert Tag.objects.filter(name="pcr").count() == 1

    def test_invalid_file_is_rejected_without_storing(self, media_root: Path) -> None:
        with pytest.raises(ValidationError) as exc:
            factories.make_document(file=factories.txt_file("x.pdf"))
        assert exc.value.code == FILE_CONTENT_MISMATCH
        assert not _stored_files(media_root)
        assert not Document.objects.exists()

    def test_invalid_metadata_does_not_store_file(self, media_root: Path) -> None:
        future = timezone.localdate() + datetime.timedelta(days=3)
        with pytest.raises(ValidationError) as exc:
            factories.make_document(published_on=future, document_type="memo")
        assert set(exc.value.message_dict) == {"published_on", "document_type"}
        assert not _stored_files(media_root)

    def test_duplicate_file_is_rejected_with_reference(self, media_root: Path) -> None:
        content = b"identical synthetic content"
        first = factories.make_document(
            file=factories.txt_file(content=content), title="Original"
        )
        with pytest.raises(ValidationError) as exc:
            factories.make_document(file=factories.txt_file("kopie.txt", content))
        error = exc.value.error_dict["file"][0]
        assert error.code == DUPLICATE_FILE
        assert str(first.id) in exc.value.message_dict["file"][0]
        assert "Original" in exc.value.message_dict["file"][0]
        assert len(_stored_files(media_root)) == 1

    def test_race_on_unique_checksum_removes_new_file(self, media_root: Path) -> None:
        with (
            mock.patch.object(Document, "save", side_effect=IntegrityError),
            pytest.raises(ValidationError) as exc,
        ):
            factories.make_document()
        assert exc.value.error_dict["file"][0].code == DUPLICATE_FILE
        assert not _stored_files(media_root)

    def test_unexpected_error_removes_new_file(self, media_root: Path) -> None:
        with (
            mock.patch.object(Document, "save", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            factories.make_document()
        assert not _stored_files(media_root)

    def test_signal_sent_after_commit(
        self,
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
        recorder: Callable[[Any], SignalRecorder],
    ) -> None:
        rec = recorder(signals.document_created)
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            document = factories.make_document()
        assert rec.calls == []
        for callback in callbacks:
            callback()
        assert rec.calls == [{"signal": signals.document_created, "document": document}]


class TestUpdate:
    def test_updates_metadata_and_tags(self) -> None:
        document = factories.make_document(tags=["alt"])
        services.update_document(
            document, title=" Neuer Titel ", language=Language.ENGLISH, tags=["Neu"]
        )
        document.refresh_from_db()
        assert document.title == "Neuer Titel"
        assert document.language == Language.ENGLISH
        assert document.tag_names() == ["neu"]

    def test_tags_unchanged_when_not_given(self) -> None:
        document = factories.make_document(tags=["bleibt"])
        services.update_document(document, source="Andere Quelle")
        assert document.tag_names() == ["bleibt"]

    def test_unknown_field_is_a_programming_error(self) -> None:
        document = factories.make_document()
        with pytest.raises(TypeError):
            services.update_document(document, checksum_sha256="x")

    def test_replacing_file_deletes_old_file_after_commit(
        self,
        media_root: Path,
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
        recorder: Callable[[Any], SignalRecorder],
    ) -> None:
        document = factories.make_document()
        document.processing_status = ProcessingStatus.PROCESSED
        document.save()
        old_path = Path(document.file.path)
        rec = recorder(signals.document_updated)

        with django_capture_on_commit_callbacks(execute=True):
            services.update_document(document, file=factories.docx_file("neu.docx"))

        document.refresh_from_db()
        assert not old_path.exists()
        assert Path(document.file.path).exists()
        assert document.original_filename == "neu.docx"
        assert document.mime_type.endswith("wordprocessingml.document")
        assert document.processing_status == ProcessingStatus.PENDING
        assert rec.calls[0]["file_replaced"] is True
        assert len(_stored_files(media_root)) == 1

    def test_replacing_with_same_extension_keeps_new_file(
        self,
        media_root: Path,
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    ) -> None:
        document = factories.make_document()
        with django_capture_on_commit_callbacks(execute=True):
            services.update_document(document, file=factories.txt_file("v2.txt"))
        document.refresh_from_db()
        assert Path(document.file.path).read_bytes().startswith(b"Synthetisch")
        assert len(_stored_files(media_root)) == 1

    def test_replacing_with_duplicate_of_other_document_fails(self) -> None:
        content = b"shared synthetic content"
        factories.make_document(file=factories.txt_file(content=content))
        document = factories.make_document()
        with pytest.raises(ValidationError) as exc:
            services.update_document(document, file=factories.txt_file(content=content))
        assert exc.value.error_dict["file"][0].code == DUPLICATE_FILE

    def test_reuploading_own_file_is_allowed(self) -> None:
        content = b"own synthetic content"
        document = factories.make_document(file=factories.txt_file(content=content))
        services.update_document(document, file=factories.txt_file(content=content))

    def test_failed_update_keeps_old_file(self, media_root: Path) -> None:
        document = factories.make_document()
        old_name = document.file.name
        with (
            mock.patch.object(Document, "save", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            services.update_document(document, file=factories.txt_file())
        assert document.file.name == old_name
        assert len(_stored_files(media_root)) == 1

    def test_update_integrity_error_becomes_duplicate_error(self) -> None:
        document = factories.make_document()
        with (
            mock.patch.object(Document, "save", side_effect=IntegrityError),
            pytest.raises(ValidationError) as exc,
        ):
            services.update_document(document, file=factories.txt_file())
        assert exc.value.error_dict["file"][0].code == DUPLICATE_FILE


class TestDelete:
    def test_delete_removes_row_and_file_and_signals(
        self,
        media_root: Path,
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
        recorder: Callable[[Any], SignalRecorder],
    ) -> None:
        document = factories.make_document(tags=["x"])
        document_id = document.id
        rec = recorder(signals.document_deleted)
        with django_capture_on_commit_callbacks(execute=True):
            services.delete_document(document)
        assert not Document.objects.filter(pk=document_id).exists()
        assert not _stored_files(media_root)
        assert rec.calls[0]["document_id"] == document_id
        assert Tag.objects.filter(name="x").exists()

    def test_missing_file_on_disk_does_not_break_delete(
        self,
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    ) -> None:
        document = factories.make_document()
        Path(document.file.path).unlink()
        with django_capture_on_commit_callbacks(execute=True):
            services.delete_document(document)
        assert not Document.objects.exists()

    def test_storage_error_is_logged_not_raised(
        self,
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        document = factories.make_document()
        with (
            mock.patch.object(FileSystemStorage, "delete", side_effect=OSError),
            django_capture_on_commit_callbacks(execute=True),
        ):
            services.delete_document(document)
        assert "Could not delete" in caplog.text
        assert "Synthetisch" not in caplog.text
