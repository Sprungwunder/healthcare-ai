from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from documents import permissions
from documents.models import Document

pytestmark = pytest.mark.django_db


def run(*args: str) -> str:
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def test_creates_documents_without_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_HUB_DEMO_PASSWORD", raising=False)
    output = run()
    assert "No demo users" in output
    assert Document.objects.count() == 6
    assert not User.objects.exists()
    assert all("Demo" in d.title for d in Document.objects.all())


def test_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_HUB_DEMO_PASSWORD", raising=False)
    run()
    output = run()
    assert "0 demo documents created, 6 already present" in output
    assert Document.objects.count() == 6


def test_creates_users_with_password_argument() -> None:
    run("--password", "synthetic-demo-pw")
    reader = User.objects.get(username="demo-reader")
    admin = User.objects.get(username="demo-admin")
    assert reader.check_password("synthetic-demo-pw")
    assert reader.groups.filter(name=permissions.READER).exists()
    assert admin.is_staff and not reader.is_staff
    assert Document.objects.filter(created_by__username="demo-editor").count() == 6


def test_password_from_env_and_existing_password_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCUMENT_HUB_DEMO_PASSWORD", "first-synthetic-pw")
    run()
    monkeypatch.setenv("DOCUMENT_HUB_DEMO_PASSWORD", "second-synthetic-pw")
    run()
    assert User.objects.get(username="demo-admin").check_password("first-synthetic-pw")
