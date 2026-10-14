from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files import File
from django.db.models import Manager
from django.urls import reverse
from rest_framework import serializers

from documents import services, validators
from documents.api.exceptions import FileTooLarge, UnsupportedFileType
from documents.models import Document, Tag


class TagListField(serializers.ListField):
    """Tags as a list of names. Also accepts "a, b" (string or list items),
    which is what multipart clients usually send."""

    child = serializers.CharField(allow_blank=True, trim_whitespace=False)

    def to_internal_value(self, data: Any) -> list[str]:
        if isinstance(data, str):
            data = [data]
        items = super().to_internal_value(data)
        try:
            return validators.normalize_tags(items)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def to_representation(self, data: Any) -> list[str]:
        if isinstance(data, Manager):
            return [tag.name for tag in data.all()]
        return list(data)


class DocumentSerializer(serializers.ModelSerializer[Document]):
    file = serializers.FileField(write_only=True)
    tags = TagListField(required=False)
    download_url = serializers.SerializerMethodField()
    created_by = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "document_type",
            "source",
            "source_url",
            "published_on",
            "language",
            "tags",
            "file",
            "download_url",
            "original_filename",
            "mime_type",
            "file_size",
            "checksum_sha256",
            "processing_status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "original_filename",
            "mime_type",
            "file_size",
            "checksum_sha256",
            "processing_status",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            # Replacing the file is optional when editing (also for PUT).
            self.fields["file"].required = False

    def get_download_url(self, document: Document) -> str:
        url = reverse("api:document-download", kwargs={"pk": document.pk})
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def validate_file(self, file: File) -> File:
        """Run the shared file rules early, mapping them to 413/415/400."""
        try:
            validators.validate_upload(file)
        except DjangoValidationError as exc:
            message = exc.messages[0]
            if exc.code == validators.FILE_TOO_LARGE:
                raise FileTooLarge(message) from exc
            if exc.code in {
                validators.FILE_TYPE_NOT_ALLOWED,
                validators.FILE_CONTENT_MISMATCH,
            }:
                raise UnsupportedFileType(message) from exc
            raise serializers.ValidationError(message, code=exc.code) from exc
        return file

    def create(self, validated_data: dict[str, Any]) -> Document:
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None
        return services.create_document(created_by=user, **validated_data)

    def update(self, instance: Document, validated_data: dict[str, Any]) -> Document:
        file = validated_data.pop("file", None)
        tags = validated_data.pop("tags", None)
        return services.update_document(
            instance, file=file, tags=tags, **validated_data
        )


class TagSerializer(serializers.ModelSerializer[Tag]):
    class Meta:
        model = Tag
        fields = ["id", "name"]
