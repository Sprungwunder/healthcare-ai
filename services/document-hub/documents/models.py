import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from documents.validators import (
    TAG_MAX_LENGTH,
    validate_not_blank,
    validate_not_in_future,
    validate_tag_name,
)


class DocumentType(models.TextChoices):
    LAB_PROTOCOL = "lab_protocol", "Laborprotokoll"
    SOP = "sop", "SOP"
    GUIDELINE = "guideline", "Leitlinie"
    TECHNICAL_MANUAL = "technical_manual", "Technisches Handbuch"


class Language(models.TextChoices):
    """ISO 639-1 codes. Add a member (and a migration) to support more."""

    GERMAN = "de", "Deutsch"
    ENGLISH = "en", "Englisch"


class ProcessingStatus(models.TextChoices):
    """State of the (future) text-extraction/indexing pipeline."""

    PENDING = "pending", "Ausstehend"
    PROCESSING = "processing", "In Bearbeitung"
    PROCESSED = "processed", "Verarbeitet"
    FAILED = "failed", "Fehlgeschlagen"


class Tag(models.Model):
    name = models.CharField(
        "Name", max_length=TAG_MAX_LENGTH, unique=True, validators=[validate_tag_name]
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Tag"
        verbose_name_plural = "Tags"

    def __str__(self) -> str:
        return self.name


def document_upload_to(instance: "Document", filename: str) -> str:
    """`documents/<yyyy>/<mm>/<uuid>.<ext>`: never reuse the client's filename."""
    now = timezone.now()
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    suffix = f".{extension}" if extension else ""
    return f"documents/{now:%Y}/{now:%m}/{instance.id}{suffix}"


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField("Titel", max_length=255, validators=[validate_not_blank])
    document_type = models.CharField(
        "Dokumenttyp", max_length=32, choices=DocumentType.choices
    )
    source = models.CharField("Quelle", max_length=255, validators=[validate_not_blank])
    source_url = models.URLField("Quell-URL", max_length=500, blank=True)
    published_on = models.DateField(
        "Veröffentlicht am",
        null=True,
        blank=True,
        validators=[validate_not_in_future],
    )
    language = models.CharField("Sprache", max_length=8, choices=Language.choices)
    tags = models.ManyToManyField(
        Tag, related_name="documents", blank=True, verbose_name="Tags"
    )

    file = models.FileField("Datei", upload_to=document_upload_to, max_length=255)
    # Derived from the uploaded file by the service layer.
    original_filename = models.CharField("Originaler Dateiname", max_length=255)
    mime_type = models.CharField("MIME-Typ", max_length=100)
    file_size = models.PositiveBigIntegerField("Dateigröße (Bytes)")
    checksum_sha256 = models.CharField("SHA-256", max_length=64, unique=True)

    processing_status = models.CharField(
        "Verarbeitungsstatus",
        max_length=16,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name="Angelegt von",
    )
    created_at = models.DateTimeField("Angelegt am", auto_now_add=True)
    updated_at = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Dokument"
        verbose_name_plural = "Dokumente"
        indexes = [
            models.Index(fields=["document_type"]),
            models.Index(fields=["language"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("documents:detail", kwargs={"pk": self.pk})

    def tag_names(self) -> list[str]:
        return [tag.name for tag in self.tags.all()]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.title = self.title.strip()
        self.source = self.source.strip()
        super().save(*args, **kwargs)
