from pathlib import Path

import pytest
from django.contrib.auth.models import User
from pytest_django.fixtures import Settings

from documents import permissions
from tests import factories


@pytest.fixture(autouse=True)
def media_root(settings: Settings, tmp_path: Path) -> Path:
    """Keep uploaded files of every test in a throwaway directory."""
    root = tmp_path / "media"
    settings.MEDIA_ROOT = root
    return root


@pytest.fixture
def users(db: None) -> dict[str, User]:
    """One user per role, plus one without any role."""
    return {
        "none": factories.make_user("ohne_rolle"),
        "reader": factories.make_user("leser", permissions.READER),
        "editor": factories.make_user("redakteur", permissions.EDITOR),
        "admin": factories.make_user("admin", permissions.ADMIN, is_staff=True),
    }
