import datetime
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from pytest_django.fixtures import DjangoCaptureOnCommitCallbacks, Settings

from documents.models import Document
from tests import factories

pytestmark = pytest.mark.django_db


def login(client: Client, user: User) -> Client:
    client.force_login(user)
    return client


def form_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Guideline Preanalytics",
        "document_type": "guideline",
        "source": "Synthetic Professional Society",
        "source_url": "",
        "published_on": "2023-11-02",
        "language": "de",
        "tags": "Preanalytics, Routine",
        "file": factories.md_file(),
    }
    data.update(overrides)
    return data


class TestAccess:
    def test_anonymous_is_redirected_to_login(self, client: Client) -> None:
        response = client.get("/")
        assert response.status_code == 302
        assert response["Location"].startswith("/login/?next=/")

    def test_user_without_role_is_forbidden(
        self, client: Client, users: dict[str, User]
    ) -> None:
        assert login(client, users["none"]).get("/").status_code == 403

    @pytest.mark.parametrize(
        ("role", "create", "edit", "delete"),
        [
            ("reader", 403, 403, 403),
            ("editor", 200, 200, 403),
            ("admin", 200, 200, 200),
        ],
    )
    def test_pages_per_role(
        self,
        client: Client,
        users: dict[str, User],
        role: str,
        create: int,
        edit: int,
        delete: int,
    ) -> None:
        document = factories.make_document()
        login(client, users[role])
        assert client.get("/").status_code == 200
        assert client.get(f"/documents/{document.pk}/").status_code == 200
        assert client.get(f"/documents/{document.pk}/download/").status_code == 200
        assert client.get("/documents/new/").status_code == create
        assert client.get(f"/documents/{document.pk}/edit/").status_code == edit
        assert client.get(f"/documents/{document.pk}/delete/").status_code == delete

    @pytest.mark.parametrize(
        ("role", "visible", "hidden"),
        [
            ("reader", ["Download"], ["Edit", "Delete"]),
            ("editor", ["Download", "Edit"], ["Delete"]),
            ("admin", ["Download", "Edit", "Delete"], []),
        ],
    )
    def test_buttons_per_role(
        self,
        client: Client,
        users: dict[str, User],
        role: str,
        visible: list[str],
        hidden: list[str],
    ) -> None:
        document = factories.make_document()
        html = login(client, users[role]).get(document.get_absolute_url()).content
        for label in visible:
            assert label.encode() in html
        for label in hidden:
            assert label.encode() not in html

    def test_new_button_only_for_editors(
        self, client: Client, users: dict[str, User]
    ) -> None:
        assert b"New document" not in login(client, users["reader"]).get("/").content
        assert b"New document" in login(client, users["editor"]).get("/").content

    def test_login_page_and_logout(
        self, client: Client, users: dict[str, User]
    ) -> None:
        assert client.get("/login/").status_code == 200
        response = client.post("/login/", {"username": "reader", "password": "pw"})
        assert response.status_code == 302
        assert client.get("/").status_code == 200
        assert client.post("/logout/").status_code == 302
        assert client.get("/").status_code == 302

    def test_unknown_document_is_404(
        self, client: Client, users: dict[str, User]
    ) -> None:
        login(client, users["admin"])
        missing = "00000000-0000-0000-0000-000000000000"
        for suffix in ["", "edit/", "delete/", "download/"]:
            assert client.get(f"/documents/{missing}/{suffix}").status_code == 404


class TestCreate:
    def test_create_document(self, client: Client, users: dict[str, User]) -> None:
        login(client, users["editor"])
        response = client.post("/documents/new/", form_data(), follow=True)
        document = Document.objects.get()
        assert response.redirect_chain[-1][0] == document.get_absolute_url()
        assert "was created" in response.content.decode()
        assert document.title == "Guideline Preanalytics"
        assert document.published_on == datetime.date(2023, 11, 2)
        assert sorted(document.tag_names()) == ["preanalytics", "routine"]
        assert document.created_by == users["editor"]

    def test_errors_are_shown_at_the_fields(
        self, client: Client, users: dict[str, User]
    ) -> None:
        future = (timezone.localdate() + datetime.timedelta(days=2)).isoformat()
        login(client, users["editor"])
        response = client.post(
            "/documents/new/",
            form_data(
                title="  ",
                published_on=future,
                file=factories.txt_file("disguised.pdf"),
            ),
        )
        assert response.status_code == 200
        form = response.context["form"]
        assert set(form.errors) == {"title", "published_on", "file"}
        assert "must not be in the future" in response.content.decode()
        assert not Document.objects.exists()

    def test_file_required_on_create(
        self, client: Client, users: dict[str, User]
    ) -> None:
        login(client, users["editor"])
        data = form_data()
        del data["file"]
        response = client.post("/documents/new/", data)
        assert "file" in response.context["form"].errors

    def test_too_large_file(
        self, client: Client, users: dict[str, User], settings: Settings
    ) -> None:
        settings.DOCUMENT_HUB_MAX_UPLOAD_SIZE = 8
        login(client, users["editor"])
        response = client.post("/documents/new/", form_data())
        assert "too large" in response.context["form"].errors["file"][0]

    def test_duplicate_shown_at_file_field(
        self, client: Client, users: dict[str, User]
    ) -> None:
        factories.make_document(file=factories.md_file(content=b"# same\n"))
        login(client, users["editor"])
        response = client.post(
            "/documents/new/", form_data(file=factories.md_file(content=b"# same\n"))
        )
        assert (
            "already exists as document" in response.context["form"].errors["file"][0]
        )

    def test_too_many_tags(self, client: Client, users: dict[str, User]) -> None:
        login(client, users["editor"])
        tags = ", ".join(f"t{i}" for i in range(21))
        response = client.post("/documents/new/", form_data(tags=tags))
        assert "tags" in response.context["form"].errors

    def test_tag_suggestions_are_offered(
        self, client: Client, users: dict[str, User]
    ) -> None:
        factories.make_document(tags=["hematology"])
        html = login(client, users["editor"]).get("/documents/new/").content.decode()
        assert '<datalist id="tag-suggestions">' in html
        assert '<option value="hematology">' in html


class TestEditAndDelete:
    def test_edit_prefills_and_saves(
        self, client: Client, users: dict[str, User]
    ) -> None:
        document = factories.make_document(title="Old", tags=["a", "b"])
        login(client, users["editor"])
        form = client.get(f"/documents/{document.pk}/edit/").context["form"]
        assert form.initial["title"] == "Old"
        assert form.initial["tags"] == "a, b"
        assert not form.fields["file"].required

        data = form_data(title="New", tags="c")
        del data["file"]
        response = client.post(f"/documents/{document.pk}/edit/", data, follow=True)
        assert "was saved" in response.content.decode()
        document.refresh_from_db()
        assert document.title == "New"
        assert document.tag_names() == ["c"]

    def test_edit_replaces_file(
        self,
        client: Client,
        users: dict[str, User],
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    ) -> None:
        document = factories.make_document()
        old_path = Path(document.file.path)
        login(client, users["editor"])
        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                f"/documents/{document.pk}/edit/",
                form_data(file=factories.pdf_file("new.pdf")),
            )
        document.refresh_from_db()
        assert document.original_filename == "new.pdf"
        assert not old_path.exists()

    def test_edit_with_duplicate_file_shows_error(
        self, client: Client, users: dict[str, User]
    ) -> None:
        factories.make_document(file=factories.txt_file(content=b"taken"))
        document = factories.make_document()
        login(client, users["editor"])
        response = client.post(
            f"/documents/{document.pk}/edit/",
            form_data(file=factories.txt_file(content=b"taken")),
        )
        assert response.status_code == 200
        assert "file" in response.context["form"].errors

    def test_delete_confirm_and_delete(
        self,
        client: Client,
        users: dict[str, User],
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    ) -> None:
        document = factories.make_document(title="Remove me")
        path = Path(document.file.path)
        login(client, users["admin"])
        confirm = client.get(f"/documents/{document.pk}/delete/")
        assert "deleted permanently" in confirm.content.decode()
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(f"/documents/{document.pk}/delete/", follow=True)
        assert "“Remove me” was deleted" in response.content.decode()
        assert not Document.objects.exists()
        assert not path.exists()

    def test_editor_cannot_delete_via_post(
        self, client: Client, users: dict[str, User]
    ) -> None:
        document = factories.make_document()
        login(client, users["editor"])
        assert client.post(f"/documents/{document.pk}/delete/").status_code == 403
        assert Document.objects.filter(pk=document.pk).exists()


class TestListAndSearch:
    @pytest.fixture
    def docs(self) -> None:
        factories.make_document(
            title="Blood Count Protocol", document_type="lab_protocol", tags=["routine"]
        )
        factories.make_document(
            title="PCR Protocol",
            document_type="lab_protocol",
            language="en",
            tags=["routine", "pcr"],
        )
        factories.make_document(title="SOP Centrifuge", tags=["equipment"])

    def _titles(self, client: Client, **params: str) -> list[str]:
        response = client.get("/", params)
        assert response.status_code == 200
        return sorted(d.title for d in response.context["documents"])

    def test_search(self, client: Client, users: dict[str, User], docs: None) -> None:
        login(client, users["reader"])
        assert self._titles(client) == [
            "Blood Count Protocol",
            "PCR Protocol",
            "SOP Centrifuge",
        ]
        assert self._titles(client, q="proto") == [
            "Blood Count Protocol",
            "PCR Protocol",
        ]
        assert self._titles(client, document_type="lab_protocol", language="en") == [
            "PCR Protocol"
        ]
        assert self._titles(client, tags="routine, PCR") == ["PCR Protocol"]

    def test_filter_values_are_kept(
        self, client: Client, users: dict[str, User], docs: None
    ) -> None:
        html = (
            login(client, users["reader"])
            .get("/", {"q": "proto", "document_type": "sop"})
            .content.decode()
        )
        assert 'value="proto"' in html
        assert '<option value="sop" selected>' in html

    def test_invalid_filter_shows_error(
        self, client: Client, users: dict[str, User], docs: None
    ) -> None:
        response = login(client, users["reader"]).get("/", {"language": "xx"})
        assert response.status_code == 200
        assert "Unknown language" in response.content.decode()
        assert list(response.context["documents"]) == []

    def test_empty_result(self, client: Client, users: dict[str, User]) -> None:
        html = (
            login(client, users["reader"]).get("/", {"q": "nothing"}).content.decode()
        )
        assert "No documents found" in html

    def test_pagination_keeps_filters(
        self, client: Client, users: dict[str, User]
    ) -> None:
        for i in range(21):
            factories.make_document(title=f"Series {i:02d}")
        login(client, users["reader"])
        first = client.get("/", {"q": "Series"})
        assert len(first.context["documents"]) == 20
        assert "q=Series&amp;page=2" in first.content.decode()
        second = client.get("/", {"q": "Series", "page": "2"})
        assert len(second.context["documents"]) == 1

    def test_download(self, client: Client, users: dict[str, User]) -> None:
        document = factories.make_document(
            file=factories.txt_file("report.txt", b"Synthetic")
        )
        response = login(client, users["reader"]).get(
            f"/documents/{document.pk}/download/"
        )
        assert response["Content-Disposition"].startswith("attachment")
        assert b"".join(response.streaming_content) == b"Synthetic"  # type: ignore[attr-defined]

    def test_static_css_is_served(self, client: Client) -> None:
        response = client.get("/static/documents/hub.css")
        assert response.status_code == 200
