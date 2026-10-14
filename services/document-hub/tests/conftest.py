from pathlib import Path

import pytest
from pytest_django.fixtures import Settings


@pytest.fixture(autouse=True)
def media_root(settings: Settings, tmp_path: Path) -> Path:
    """Keep uploaded files of every test in a throwaway directory."""
    root = tmp_path / "media"
    settings.MEDIA_ROOT = root
    return root
