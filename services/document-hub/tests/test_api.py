import datetime
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from pytest_django.fixtures import DjangoCaptureOnCommitCallbacks, Settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from documents.models import Document, Tag
from tests import factories

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/documents/"


def detail_url(document: Document) -> str:
    return f"{LIST_URL}{document.id}/"


def client_for(user: User | None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


def upload_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "SOP Probenannahme",
        "document_type": "sop",
        "source": "Synthetisches Labor",
        "language": "de",
        "tags": "Präanalytik, Proben",
        "file": factories.pdf_file(),
    }
    data.update(overrides)
    return data


def error(response: Any) -> dict[str, Any]:
    body: dict[str, Any] = response.json()["error"]
    return body


class TestPermissionMatrix:
    """Expected status per role; `None` is an anonymous client."""

    ROLES = ["anonymous", "none", "reader", "editor", "admin"]

    def _client(self, role: str, users: dict[str, User]) -> APIClient:
        return client_for(None if role == "anonymous" else users[role])

    @pytest.mark.parametrize(
        ("role", "expected"),
        [("anonymous", 401), ("none", 403), ("reader", 200), ("editor", 200),
         ("admin", 200)],
    )  # fmt: skip
    def test_read_endpoints(
        self, role: str, expected: int, users: dict[str, User]
    ) -> None:
        document = factories.make_document(tags=["x"])
        client = self._client(role, users)
        for url in [
            LIST_URL,
            detail_url(document),
            f"{detail_url(document)}download/",
            "/api/v1/tags/",
            "/api/schema/",
        ]:
            assert client.get(url).status_code == expected, url

    @pytest.mark.parametrize(
        ("role", "expected"),
        [("anonymous", 401), ("none", 403), ("reader", 403), ("editor", 201),
         ("admin", 201)],
    )  # fmt: skip
    def test_create(self, role: str, expected: int, users: dict[str, User]) -> None:
        response = self._client(role, users).post(LIST_URL, upload_payload())
        assert response.status_code == expected

    @pytest.mark.parametrize(
        ("role", "expected"),
        [("anonymous", 401), ("none", 403), ("reader", 403), ("editor", 200),
         ("admin", 200)],
    )  # fmt: skip
    def test_update(self, role: str, expected: int, users: dict[str, User]) -> None:
        document = factories.make_document()
        response = self._client(role, users).patch(
            detail_url(document), {"title": "Neu"}, format="json"
        )
        assert response.status_code == expected

    @pytest.mark.parametrize(
        ("role", "expected"),
        [("anonymous", 401), ("none", 403), ("reader", 403), ("editor", 403),
         ("admin", 204)],
    )  # fmt: skip
    def test_delete(self, role: str, expected: int, users: dict[str, User]) -> None:
        document = factories.make_document()
        response = self._client(role, users).delete(detail_url(document))
        assert response.status_code == expected

    def test_tags_are_read_only(self, users: dict[str, User]) -> None:
        response = client_for(users["admin"]).post("/api/v1/tags/", {"name": "x"})
        assert response.status_code == 405
        assert error(response)["code"] == "method_not_allowed"


class TestCrud:
    def test_create_and_retrieve(self, users: dict[str, User]) -> None:
        client = client_for(users["editor"])
        response = client.post(
            LIST_URL,
            upload_payload(
                published_on="2024-03-01", source_url="https://example.org/sop"
            ),
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert sorted(body["tags"]) == ["proben", "präanalytik"]
        assert body["mime_type"] == "application/pdf"
        assert body["processing_status"] == "pending"
        assert body["created_by"] == "editor"
        assert body["download_url"].endswith(
            f"/api/v1/documents/{body['id']}/download/"
        )
        assert "file" not in body

        detail = client.get(f"{LIST_URL}{body['id']}/").json()
        assert detail["title"] == "SOP Probenannahme"
        assert detail["published_on"] == "2024-03-01"

    def test_tags_as_repeated_multipart_fields(self, users: dict[str, User]) -> None:
        response = client_for(users["editor"]).post(
            LIST_URL, upload_payload(tags=["Eins", "zwei, drei"])
        )
        assert sorted(response.json()["tags"]) == ["drei", "eins", "zwei"]

    def test_patch_metadata_and_tags_via_json(self, users: dict[str, User]) -> None:
        document = factories.make_document(tags=["alt"])
        response = client_for(users["editor"]).patch(
            detail_url(document),
            {"title": "Aktualisiert", "tags": ["neu", "Zweiter"]},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Aktualisiert"
        assert sorted(response.json()["tags"]) == ["neu", "zweiter"]

    def test_patch_replaces_file(self, users: dict[str, User]) -> None:
        document = factories.make_document()
        old_checksum = document.checksum_sha256
        response = client_for(users["editor"]).patch(
            detail_url(document), {"file": factories.md_file("neu.md")}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["original_filename"] == "neu.md"
        assert body["mime_type"] == "text/markdown"
        assert body["checksum_sha256"] != old_checksum

    def test_put_without_file_keeps_file(self, users: dict[str, User]) -> None:
        document = factories.make_document()
        response = client_for(users["editor"]).put(
            detail_url(document),
            {
                "title": "Komplett",
                "document_type": "guideline",
                "source": "Fachgesellschaft",
                "language": "en",
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["original_filename"] == document.original_filename
        assert response.json()["document_type"] == "guideline"

    def test_delete_removes_file(
        self,
        users: dict[str, User],
        media_root: Path,
        django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    ) -> None:
        document = factories.make_document()
        path = Path(document.file.path)
        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(users["admin"]).delete(detail_url(document))
        assert response.status_code == 204
        assert not Document.objects.exists()
        assert not path.exists()

    def test_download_returns_file_with_original_name(
        self, users: dict[str, User]
    ) -> None:
        upload = factories.txt_file("Prüfprotokoll Gerät.txt", b"Synthetischer Inhalt")
        document = factories.make_document(file=upload)
        response = client_for(users["reader"]).get(f"{detail_url(document)}download/")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain"
        assert "attachment" in response["Content-Disposition"]
        assert "Pr%C3%BCfprotokoll" in response["Content-Disposition"]
        assert response["Cache-Control"] == "private, no-store"
        assert b"".join(response.streaming_content) == b"Synthetischer Inhalt"  # type: ignore[attr-defined]

    def test_download_missing_file_is_404(self, users: dict[str, User]) -> None:
        document = factories.make_document()
        Path(document.file.path).unlink()
        response = client_for(users["reader"]).get(f"{detail_url(document)}download/")
        assert response.status_code == 404
        assert error(response)["code"] == "not_found"


class TestSearchAndPagination:
    def test_filters(self, users: dict[str, User]) -> None:
        factories.make_document(title="Blutbild", document_type="lab_protocol",
                                tags=["hämatologie", "routine"])  # fmt: skip
        factories.make_document(title="PCR", document_type="lab_protocol",
                                language="en", tags=["routine"])  # fmt: skip
        factories.make_document(title="Zentrifuge SOP", tags=["geräte"])
        client = client_for(users["reader"])

        def titles(**params: str) -> list[str]:
            response = client.get(LIST_URL, params)
            assert response.status_code == 200
            return sorted(d["title"] for d in response.json()["results"])

        assert titles(q="blut") == ["Blutbild"]
        assert titles(document_type="lab_protocol") == ["Blutbild", "PCR"]
        assert titles(tags="routine,Hämatologie") == ["Blutbild"]
        assert titles(language="en") == ["PCR"]
        assert titles(document_type="lab_protocol", language="de") == ["Blutbild"]
        assert titles(ordering="title") == ["Blutbild", "PCR", "Zentrifuge SOP"]

    def test_invalid_filter_is_validation_error(self, users: dict[str, User]) -> None:
        response = client_for(users["reader"]).get(LIST_URL, {"document_type": "memo"})
        assert response.status_code == 400
        assert error(response)["code"] == "validation_error"
        assert "document_type" in error(response)["details"]

    def test_pagination(self, users: dict[str, User]) -> None:
        for _ in range(23):
            factories.make_document()
        client = client_for(users["reader"])
        first = client.get(LIST_URL).json()
        assert first["count"] == 23
        assert len(first["results"]) == 20
        assert first["next"] is not None
        second = client.get(LIST_URL, {"page": 2}).json()
        assert len(second["results"]) == 3
        assert client.get(LIST_URL, {"page": 9}).status_code == 404

    def test_tag_search(self, users: dict[str, User]) -> None:
        for name in ["hämatologie", "hämostaseologie", "pcr"]:
            Tag.objects.create(name=name)
        response = client_for(users["reader"]).get("/api/v1/tags/", {"q": "häm"})
        assert [t["name"] for t in response.json()["results"]] == [
            "hämatologie",
            "hämostaseologie",
        ]


class TestErrors:
    def test_validation_error_format(self, users: dict[str, User]) -> None:
        future = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        response = client_for(users["editor"]).post(
            LIST_URL,
            upload_payload(title="   ", document_type="memo", published_on=future),
        )
        assert response.status_code == 400
        body = error(response)
        assert body["code"] == "validation_error"
        assert body["message"]
        assert set(body["details"]) == {"title", "document_type", "published_on"}

    def test_missing_file(self, users: dict[str, User]) -> None:
        payload = upload_payload()
        del payload["file"]
        response = client_for(users["editor"]).post(LIST_URL, payload)
        assert response.status_code == 400
        assert "file" in error(response)["details"]

    def test_empty_file(self, users: dict[str, User]) -> None:
        response = client_for(users["editor"]).post(
            LIST_URL, upload_payload(file=SimpleUploadedFile("leer.txt", b""))
        )
        assert response.status_code == 400
        assert "file" in error(response)["details"]

    def test_too_large_is_413(self, users: dict[str, User], settings: Settings) -> None:
        settings.DOCUMENT_HUB_MAX_UPLOAD_SIZE = 10
        response = client_for(users["editor"]).post(LIST_URL, upload_payload())
        assert response.status_code == 413
        body = error(response)
        assert body["code"] == "file_too_large"
        assert "10 bytes" in body["details"]["file"][0]
        assert not Document.objects.exists()

    @pytest.mark.parametrize(
        "upload",
        [
            SimpleUploadedFile("bild.png", b"\x89PNG\r\n"),
            SimpleUploadedFile("tarnung.pdf", b"MZ\x90 executable"),
        ],
    )
    def test_unsupported_or_forged_type_is_415(
        self, users: dict[str, User], upload: SimpleUploadedFile
    ) -> None:
        response = client_for(users["editor"]).post(
            LIST_URL, upload_payload(file=upload)
        )
        assert response.status_code == 415
        assert error(response)["code"] == "unsupported_file_type"
        assert "file" in error(response)["details"]

    def test_duplicate_is_400_with_reference(self, users: dict[str, User]) -> None:
        existing = factories.make_document(file=factories.txt_file(content=b"dup"))
        response = client_for(users["editor"]).post(
            LIST_URL, upload_payload(file=factories.txt_file("b.txt", b"dup"))
        )
        assert response.status_code == 400
        assert str(existing.id) in error(response)["details"]["file"][0]

    def test_too_many_tags(self, users: dict[str, User]) -> None:
        tags = ",".join(f"t{i}" for i in range(21))
        response = client_for(users["editor"]).post(LIST_URL, upload_payload(tags=tags))
        assert response.status_code == 400
        assert "tags" in error(response)["details"]

    def test_unauthenticated_format(self) -> None:
        response = APIClient().get(LIST_URL)
        assert response.status_code == 401
        assert response["WWW-Authenticate"] == "Token"
        assert error(response) == {
            "code": "not_authenticated",
            "message": error(response)["message"],
            "details": {},
        }

    def test_forbidden_format(self, users: dict[str, User]) -> None:
        response = client_for(users["reader"]).delete(
            detail_url(factories.make_document())
        )
        assert error(response)["code"] == "permission_denied"

    @pytest.mark.parametrize("pk", ["00000000-0000-0000-0000-000000000000", "abc"])
    def test_not_found(self, users: dict[str, User], pk: str) -> None:
        response = client_for(users["reader"]).get(f"{LIST_URL}{pk}/")
        assert response.status_code == 404
        assert error(response)["code"] == "not_found"

    def test_unsupported_request_media_type(self, users: dict[str, User]) -> None:
        response = client_for(users["editor"]).post(
            LIST_URL, "<xml/>", content_type="application/xml"
        )
        assert response.status_code == 415
        assert error(response)["code"] == "unsupported_media_type"


class TestTokenAuth:
    def test_obtain_token_and_use_it(self, users: dict[str, User]) -> None:
        response = APIClient().post(
            "/api/v1/auth/token/", {"username": "reader", "password": "pw"}
        )
        assert response.status_code == 200
        token = response.json()["token"]
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        assert client.get(LIST_URL).status_code == 200

    def test_wrong_password(self, users: dict[str, User]) -> None:
        response = APIClient().post(
            "/api/v1/auth/token/", {"username": "reader", "password": "wrong"}
        )
        assert response.status_code == 400
        assert error(response)["code"] == "validation_error"

    def test_invalid_token_is_401(self, users: dict[str, User]) -> None:
        Token.objects.create(user=users["reader"])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token ungueltig")
        response = client.get(LIST_URL)
        assert response.status_code == 401
        assert error(response)["code"] == "authentication_failed"


def test_swagger_ui_is_self_hosted(users: dict[str, User]) -> None:
    client = APIClient()
    client.force_login(users["reader"])
    response = client.get("/api/docs/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "cdn.jsdelivr" not in html
    assert "/static/drf_spectacular_sidecar/" in html
