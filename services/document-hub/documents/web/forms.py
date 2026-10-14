from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from documents.models import Document, DocumentType, Language
from documents.validators import (
    ALLOWED_FILE_TYPES,
    normalize_tags,
    validate_not_in_future,
    validate_upload,
)

_ACCEPT = ",".join(f".{ext}" for ext in ALLOWED_FILE_TYPES)


class DocumentForm(forms.Form):
    """Create/edit form. Format checks only; `documents.services` decides."""

    title = forms.CharField(label="Titel", max_length=255)
    document_type = forms.ChoiceField(label="Dokumenttyp", choices=DocumentType.choices)
    source = forms.CharField(
        label="Quelle",
        max_length=255,
        help_text="Z. B. Herausgeber, Labor oder Fachgesellschaft.",
    )
    source_url = forms.URLField(
        label="Quell-URL", required=False, max_length=500, assume_scheme="https"
    )
    published_on = forms.DateField(
        label="Veröffentlicht am",
        required=False,
        validators=[validate_not_in_future],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    language = forms.ChoiceField(label="Sprache", choices=Language.choices)
    tags = forms.CharField(
        label="Tags",
        required=False,
        help_text="Kommagetrennt, z. B. „hämatologie, routine“. Höchstens 20.",
        widget=forms.TextInput(attrs={"list": "tag-suggestions"}),
    )
    file = forms.FileField(
        label="Datei",
        help_text="PDF, DOCX, TXT oder MD.",
        widget=forms.ClearableFileInput(attrs={"accept": _ACCEPT}),
    )

    def __init__(
        self, *args: Any, document: Document | None = None, **kwargs: Any
    ) -> None:
        if document is not None and not kwargs.get("initial"):
            kwargs["initial"] = {
                "title": document.title,
                "document_type": document.document_type,
                "source": document.source,
                "source_url": document.source_url,
                "published_on": document.published_on,
                "language": document.language,
                "tags": ", ".join(document.tag_names()),
            }
        super().__init__(*args, **kwargs)
        self.document = document
        if document is not None:
            self.fields["file"].required = False
            self.fields["file"].help_text = (
                f"Optional: ersetzt „{document.original_filename}“. "
                "PDF, DOCX, TXT oder MD."
            )
            self.fields["file"].widget = forms.FileInput(attrs={"accept": _ACCEPT})

    def clean_title(self) -> str:
        title: str = self.cleaned_data["title"].strip()
        if not title:
            raise ValidationError("Dieses Feld darf nicht leer sein.")
        return title

    def clean_tags(self) -> list[str]:
        return normalize_tags(self.cleaned_data.get("tags") or "")

    def clean_file(self) -> Any:
        file = self.cleaned_data.get("file")
        if file:
            validate_upload(file)
        return file or None

    def service_data(self) -> dict[str, Any]:
        """Cleaned data as keyword arguments for the service functions."""
        data = dict(self.cleaned_data)
        if data.get("file") is None:
            data.pop("file", None)
        return data

    def add_service_errors(self, exc: ValidationError) -> None:
        """Show a `ValidationError` from the service layer on the right fields."""
        if hasattr(exc, "error_dict"):
            for field, errors in exc.error_dict.items():
                self.add_error(field if field in self.fields else None, errors)
        else:
            self.add_error(None, exc)
