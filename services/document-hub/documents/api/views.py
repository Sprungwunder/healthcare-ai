from django.db.models import QuerySet
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request

from documents import search, services
from documents.api.serializers import DocumentSerializer, TagSerializer
from documents.downloads import document_file_response
from documents.models import Document, DocumentType, Language, Tag

SEARCH_PARAMETERS = [
    OpenApiParameter("q", str, description="Teil des Titels (ohne Groß/Klein)."),
    OpenApiParameter("document_type", str, enum=DocumentType.values),
    OpenApiParameter("language", str, enum=Language.values),
    OpenApiParameter(
        "tags", str, description="Kommagetrennt; alle Tags müssen vorhanden sein."
    ),
    OpenApiParameter("ordering", str, enum=list(search.ORDERINGS)),
]


@extend_schema_view(list=extend_schema(parameters=SEARCH_PARAMETERS))
class DocumentViewSet(viewsets.ModelViewSet[Document]):
    """Documents: Leser read, Redakteur create/edit, Administrator delete."""

    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self) -> QuerySet[Document]:
        if self.action == "list":
            params = self.request.query_params
            query = search.parse_search_params(
                {key: str(params.get(key, "")) for key in params}
            )
            return search.search_documents(query)
        return Document.objects.select_related("created_by").prefetch_related("tags")

    def perform_destroy(self, instance: Document) -> None:
        services.delete_document(instance)

    @extend_schema(
        responses={
            (200, "application/octet-stream"): OpenApiResponse(OpenApiTypes.BINARY)
        }
    )
    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        return document_file_response(self.get_object())


@extend_schema_view(
    list=extend_schema(
        parameters=[OpenApiParameter("q", str, description="Teil des Tag-Namens.")]
    )
)
class TagViewSet(viewsets.ReadOnlyModelViewSet[Tag]):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

    def get_queryset(self) -> QuerySet[Tag]:
        tags = Tag.objects.all()
        text = str(self.request.query_params.get("q", "")).strip()
        if text:
            tags = tags.filter(name__icontains=text)
        return tags
