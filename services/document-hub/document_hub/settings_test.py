"""Settings for the test suite: production settings plus test-only tweaks."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-not-a-secret")
os.environ.setdefault("DJANGO_HTTPS", "false")

from document_hub.settings import *  # noqa: E402,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
