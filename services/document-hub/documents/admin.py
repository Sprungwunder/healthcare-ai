from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from documents.models import Document, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Read-only overview. Documents are created and edited in the web UI or the
    API, so the file rules and signals in `documents.services` always apply."""

    list_display = [
        "title",
        "document_type",
        "language",
        "processing_status",
        "created_at",
    ]
    list_filter = ["document_type", "language", "processing_status"]
    search_fields = ["title", "source"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: Document | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Document | None = None
    ) -> bool:
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[Document]:
        return super().get_queryset(request).select_related("created_by")
