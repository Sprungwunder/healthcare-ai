from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import FormView

from documents import search, services
from documents.downloads import document_file_response
from documents.models import Document, DocumentType, Language, Tag
from documents.web.forms import DocumentForm

ORDERING_LABELS = {
    "-created_at": "Neueste zuerst",
    "created_at": "Älteste zuerst",
    "title": "Titel A–Z",
    "-title": "Titel Z–A",
    "-published_on": "Veröffentlichung, neueste",
    "published_on": "Veröffentlichung, älteste",
}
TAG_SUGGESTION_LIMIT = 200


def _tag_suggestions() -> list[str]:
    return list(Tag.objects.values_list("name", flat=True)[:TAG_SUGGESTION_LIMIT])


class RoleRequiredMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Anonymous users go to the login page; users without the role get 403."""


class DocumentListView(RoleRequiredMixin, ListView[Document]):
    permission_required = "documents.view_document"
    template_name = "documents/list.html"
    context_object_name = "documents"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Document]:
        self.search_errors: dict[str, list[str]] = {}
        params = {key: self.request.GET.get(key, "") for key in self.request.GET}
        try:
            self.query = search.parse_search_params(params)
        except ValidationError as exc:
            self.query = search.SearchQuery()
            self.search_errors = exc.message_dict
            return Document.objects.none()
        return search.search_documents(self.query)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(
            filters={
                "q": self.request.GET.get("q", ""),
                "document_type": self.request.GET.get("document_type", ""),
                "language": self.request.GET.get("language", ""),
                "tags": self.request.GET.get("tags", ""),
                "ordering": self.request.GET.get("ordering", "")
                or search.DEFAULT_ORDERING,
            },
            query=self.query,
            search_errors=self.search_errors,
            document_types=DocumentType.choices,
            languages=Language.choices,
            orderings=list(ORDERING_LABELS.items()),
            tag_suggestions=_tag_suggestions(),
            page_query=urlencode(
                [(k, v) for k, v in self.request.GET.items() if k != "page" and v]
            ),
        )
        return context


class DocumentDetailView(RoleRequiredMixin, DetailView[Document]):
    permission_required = "documents.view_document"
    template_name = "documents/detail.html"
    context_object_name = "document"

    def get_queryset(self) -> QuerySet[Document]:
        return Document.objects.select_related("created_by").prefetch_related("tags")


class _DocumentFormView(RoleRequiredMixin, FormView[DocumentForm]):
    form_class = DocumentForm
    template_name = "documents/form.html"
    document: Document | None = None

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["document"] = self.document
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["document"] = self.document
        context["tag_suggestions"] = _tag_suggestions()
        return context

    def save(self, form: DocumentForm) -> Document:
        raise NotImplementedError

    def form_valid(self, form: DocumentForm) -> HttpResponse:
        try:
            document = self.save(form)
        except ValidationError as exc:
            form.add_service_errors(exc)
            return self.form_invalid(form)
        messages.success(self.request, self.success_message.format(document.title))
        return HttpResponseRedirect(document.get_absolute_url())

    success_message = ""


class DocumentCreateView(_DocumentFormView):
    permission_required = "documents.add_document"
    success_message = "Dokument „{}“ wurde angelegt."

    def save(self, form: DocumentForm) -> Document:
        user = self.request.user
        return services.create_document(
            created_by=user if user.is_authenticated else None,
            **form.service_data(),
        )


class DocumentUpdateView(_DocumentFormView):
    permission_required = "documents.change_document"
    success_message = "Dokument „{}“ wurde gespeichert."

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        self.document = get_object_or_404(Document, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def save(self, form: DocumentForm) -> Document:
        assert self.document is not None
        return services.update_document(self.document, **form.service_data())


class DocumentDeleteView(RoleRequiredMixin, TemplateView):
    permission_required = "documents.delete_document"
    template_name = "documents/confirm_delete.html"

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        self.document = get_object_or_404(Document, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["document"] = self.document
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        title = self.document.title
        services.delete_document(self.document)
        messages.success(request, f"Dokument „{title}“ wurde gelöscht.")
        return redirect(reverse("documents:list"))


class DocumentDownloadView(RoleRequiredMixin, View):
    permission_required = "documents.view_document"

    def get(self, request: HttpRequest, pk: str) -> FileResponse:
        return document_file_response(get_object_or_404(Document, pk=pk))
