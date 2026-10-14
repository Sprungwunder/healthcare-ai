from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from pytest_django.fixtures import Settings

from documents import search
from documents.models import Document, DocumentType, Language
from tests import factories

pytestmark = pytest.mark.django_db


@pytest.fixture
def corpus() -> dict[str, Document]:
    return {
        "blood": factories.make_document(
            title="Laborprotokoll Blutbild",
            document_type=DocumentType.LAB_PROTOCOL,
            language=Language.GERMAN,
            tags=["hämatologie", "routine"],
        ),
        "pcr": factories.make_document(
            title="PCR Protocol SARS-CoV-2",
            document_type=DocumentType.LAB_PROTOCOL,
            language=Language.ENGLISH,
            tags=["pcr", "routine"],
        ),
        "sop": factories.make_document(
            title="SOP Zentrifuge",
            document_type=DocumentType.SOP,
            language=Language.GERMAN,
            tags=["geräte"],
        ),
        "manual": factories.make_document(
            title="Analyzer Technical Manual",
            document_type=DocumentType.TECHNICAL_MANUAL,
            language=Language.ENGLISH,
            tags=[],
        ),
    }


def _titles(qs: QuerySet[Document]) -> set[str]:
    return {d.title for d in qs}


def _search(**params: str) -> set[str]:
    return _titles(search.search_documents(search.parse_search_params(params)))


def test_no_filter_returns_all(corpus: dict[str, Document]) -> None:
    assert len(_search()) == 4


def test_title_contains_case_insensitive(corpus: dict[str, Document]) -> None:
    assert _search(q="protokoll") == {"Laborprotokoll Blutbild"}
    assert _search(q="PROTOCOL") == {"PCR Protocol SARS-CoV-2"}
    assert _search(q="  zentri ") == {"SOP Zentrifuge"}


def test_filter_by_type(corpus: dict[str, Document]) -> None:
    assert _search(document_type="lab_protocol") == {
        "Laborprotokoll Blutbild",
        "PCR Protocol SARS-CoV-2",
    }


def test_filter_by_language(corpus: dict[str, Document]) -> None:
    assert _search(language="de") == {"Laborprotokoll Blutbild", "SOP Zentrifuge"}


def test_tags_require_all(corpus: dict[str, Document]) -> None:
    assert _search(tags="routine") == {
        "Laborprotokoll Blutbild",
        "PCR Protocol SARS-CoV-2",
    }
    assert _search(tags="Routine, PCR") == {"PCR Protocol SARS-CoV-2"}
    assert _search(tags="pcr,geräte") == set()
    assert _search(tags="unbekannt") == set()


def test_combined_filters(corpus: dict[str, Document]) -> None:
    assert _search(
        q="proto", document_type="lab_protocol", language="en", tags="routine"
    ) == {"PCR Protocol SARS-CoV-2"}
    assert _search(q="proto", language="de", tags="pcr") == set()


def test_ordering(corpus: dict[str, Document]) -> None:
    query = search.parse_search_params({"ordering": "title"})
    titles = [d.title for d in search.search_documents(query)]
    assert titles == sorted(titles)
    newest_first = list(search.search_documents(search.SearchQuery()))
    assert newest_first[0] == corpus["manual"]


def test_results_are_distinct(corpus: dict[str, Document]) -> None:
    query = search.parse_search_params({"tags": "routine,hämatologie"})
    assert search.search_documents(query).count() == 1


def test_invalid_params_are_reported_per_field() -> None:
    with pytest.raises(ValidationError) as exc:
        search.parse_search_params(
            {
                "document_type": "memo",
                "language": "fr",
                "ordering": "checksum",
                "tags": "x" * 60,
            }
        )
    assert set(exc.value.message_dict) == {
        "document_type",
        "language",
        "ordering",
        "tags",
    }


def test_is_filtered() -> None:
    assert not search.SearchQuery().is_filtered
    assert search.SearchQuery(tags=("a",)).is_filtered


class StubBackend:
    last_query: Any = None

    def search(self, query: search.SearchQuery) -> QuerySet[Document]:
        StubBackend.last_query = query
        return Document.objects.none()


def test_backend_is_configurable(settings: Settings) -> None:
    settings.DOCUMENT_HUB_SEARCH_BACKEND = "tests.test_search.StubBackend"
    query = search.SearchQuery(text="egal")
    assert list(search.search_documents(query)) == []
    assert StubBackend.last_query == query
