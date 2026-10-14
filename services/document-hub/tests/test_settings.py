import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parent.parent

PRODUCTION_ENV = {
    "DJANGO_SETTINGS_MODULE": "document_hub.settings",
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": "x" * 20 + "-synthetic-smoke-test-key-" + "y" * 30,
    "DJANGO_ALLOWED_HOSTS": "hub.example.org",
    "DJANGO_HTTPS": "true",
    "DJANGO_SECURE_HSTS_SECONDS": "31536000",
    "DJANGO_SECURE_HSTS_PRELOAD": "true",
}


def _manage(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    full_env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_",))}
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=SERVICE_DIR,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.slow
def test_check_deploy_passes_with_production_env() -> None:
    result = _manage("check", "--deploy", "--fail-level", "WARNING", env=PRODUCTION_ENV)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_secret_key_without_debug_fails() -> None:
    env = {**PRODUCTION_ENV, "DJANGO_SECRET_KEY": ""}
    result = _manage("check", env=env)
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr
