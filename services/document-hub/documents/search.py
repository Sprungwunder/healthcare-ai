"""Document search, behind a pluggable backend.

Callers build a `SearchQuery` (usually with `parse_search_params`) and call
`search_documents`. The backend is chosen by `DOCUMENT_HUB_SEARCH_BACKEND`
(dotted path). The default `DatabaseSearchBackend` queries the database; a
future Elasticsearch backend implements the same protocol and returns a
queryset of the matching documents (e.g. `filter(pk__in=ids)` in hit order).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.utils.module_loading import import_string

from documents.models import Document, DocumentType, Language
from documents.validators import normalize_tags

#: Public ordering values -> model ordering.
ORDERINGS: dict[str, tuple[str, ...]] = {
    "-created_at": ("-created_at",),
    "created_at": ("created_at",),
    "title": ("title", "-created_at"),
    "-title": ("-title", "-created_at"),
    "-published_on": ("-published_on", "-created_at"),
    "published_on": ("published_on", "-created_at"),
}
DEFAULT_ORDERING = "-created_at"


@dataclass(frozen=True)
class SearchQuery:
    """Filters are combined with AND. Empty values mean "no filter"."""

    text: str = ""
    document_type: str = ""
    language: str = ""
    tags: tuple[str, ...] = field(default=())
    ordering: str = DEFAULT_ORDERING

    @property
    def is_filtered(self) -> bool:
        return bool(self.text or self.document_type or self.language or self.tags)


class DocumentSearchBackend(Protocol):
    def search(self, query: SearchQuery) -> QuerySet[Document]: ...


class DatabaseSearchBackend:
    """Title contains `text` (case-insensitive); all given tags must match."""

    def search(self, query: SearchQuery) -> QuerySet[Document]:
        documents = Document.objects.select_related("created_by").prefetch_related(
            "tags"
        )
        if query.text:
            documents = documents.filter(title__icontains=query.text)
        if query.document_type:
            documents = documents.filter(document_type=query.document_type)
        if query.language:
            documents = documents.filter(language=query.language)
        for tag in query.tags:
            # One join per tag: a document must carry every tag.
            documents = documents.filter(tags__name=tag)
        return documents.order_by(*ORDERINGS[query.ordering])


def get_search_backend() -> DocumentSearchBackend:
    backend_class = import_string(settings.DOCUMENT_HUB_SEARCH_BACKEND)
    backend: DocumentSearchBackend = backend_class()
    return backend


def search_documents(query: SearchQuery) -> QuerySet[Document]:
    return get_search_backend().search(query)


def parse_search_params(params: Mapping[str, str]) -> SearchQuery:
    """Build a `SearchQuery` from request parameters (API and web UI).

    Accepted keys: `q`, `document_type`, `language`, `tags` (comma-separated),
    `ordering`. Raises `ValidationError` with per-parameter messages.
    """
    errors: dict[str, list[str]] = {}

    document_type = params.get("document_type", "").strip()
    if document_type and document_type not in DocumentType.values:
        errors["document_type"] = [f"Unknown document type “{document_type}”."]

    language = params.get("language", "").strip()
    if language and language not in Language.values:
        errors["language"] = [f"Unknown language “{language}”."]

    ordering = params.get("ordering", "").strip() or DEFAULT_ORDERING
    if ordering not in ORDERINGS:
        errors["ordering"] = [f"Unknown ordering. Allowed: {', '.join(ORDERINGS)}."]

    tags: list[str] = []
    try:
        tags = normalize_tags(params.get("tags", ""))
    except ValidationError as exc:
        errors["tags"] = exc.messages

    if errors:
        raise ValidationError(errors)
    return SearchQuery(
        text=params.get("q", "").strip(),
        document_type=document_type,
        language=language,
        tags=tuple(tags),
        ordering=ordering,
    )
