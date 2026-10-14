import importlib
import uuid

import pytest
from django.contrib.auth.models import Group, User

from documents import permissions
from documents.models import Document, DocumentType, Language, Tag, document_upload_to


def test_upload_path_uses_document_id_not_client_filename() -> None:
    document = Document(id=uuid.UUID("12345678-1234-5678-1234-567812345678"))
    path = document_upload_to(document, "Mein Befund (final).PDF")
    assert path.startswith("documents/")
    assert path.endswith("/12345678-1234-5678-1234-567812345678.pdf")
    assert "Befund" not in path


def test_upload_path_without_extension() -> None:
    document = Document()
    assert document_upload_to(document, "README").endswith(str(document.id))


def test_str_representations() -> None:
    assert str(Tag(name="hämatologie")) == "hämatologie"
    assert str(Document(title="SOP Zentrifuge")) == "SOP Zentrifuge"


def test_choices_have_english_labels() -> None:
    assert DocumentType.LAB_PROTOCOL.label == "Lab protocol"
    assert Language.GERMAN.value == "de"


@pytest.mark.django_db
def test_role_groups_have_expected_permissions() -> None:
    for role, expected in permissions.ROLE_PERMISSIONS.items():
        group = Group.objects.get(name=role)
        actual = {
            f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.all()
        }
        assert actual == set(expected)


@pytest.mark.django_db
def test_sync_role_groups_is_idempotent() -> None:
    permissions.sync_role_groups()
    permissions.sync_role_groups()
    assert Group.objects.filter(name__in=permissions.ROLE_PERMISSIONS).count() == 3


@pytest.mark.django_db
def test_rename_migration_moves_german_groups_with_members() -> None:
    from django.apps import apps

    rename = importlib.import_module("documents.migrations.0004_rename_role_groups")
    Group.objects.filter(name__in=["Reader", "Editor"]).delete()
    old_group = Group.objects.create(name="Leser")
    user = User.objects.create_user("bestehend")
    user.groups.add(old_group)

    rename.forwards(apps, None)

    assert not Group.objects.filter(name="Leser").exists()
    assert user.groups.filter(name=permissions.READER).exists()
    assert Group.objects.get(name=permissions.EDITOR).permissions.count() == 5

    rename.backwards(apps, None)
    assert user.groups.filter(name="Leser").exists()
