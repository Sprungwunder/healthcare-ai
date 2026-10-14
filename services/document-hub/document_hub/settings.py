"""Django settings for the document hub.

All deployment-specific values come from environment variables (see
`.env.example`). A local `.env` file next to `manage.py` is read if present;
real environment variables take precedence over it.
"""

import os
from pathlib import Path

import dj_database_url
import django_stubs_ext
from django.core.exceptions import ImproperlyConfigured

# Lets generic classes be subscripted at runtime (e.g. `ListView[Document]`).
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from `path` without overriding existing variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item]


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


_load_dotenv(BASE_DIR / ".env")

DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off."
        )
    # Only reachable with DEBUG on: a fixed, obviously unsafe key for local use.
    SECRET_KEY = "django-insecure-local-development-only"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "documents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "document_hub.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "document_hub.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=env_int("DJANGO_DB_CONN_MAX_AGE", 60),
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "documents:list"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles"))

# Uploaded documents. There is deliberately no public MEDIA_URL route: files are
# only served through the permission-checked download views.
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Document hub ---------------------------------------------------------
DOCUMENT_HUB_MAX_UPLOAD_SIZE = env_int("DOCUMENT_HUB_MAX_UPLOAD_SIZE", 10 * 1024 * 1024)
DOCUMENT_HUB_SEARCH_BACKEND = os.environ.get(
    "DOCUMENT_HUB_SEARCH_BACKEND", "documents.search.DatabaseSearchBackend"
)

# --- REST API -------------------------------------------------------------
REST_FRAMEWORK = {
    # Token first, so unauthenticated API calls get 401 (with WWW-Authenticate)
    # instead of the 403 that session auth alone would produce.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "documents.api.permissions.ModelPermissionsWithView",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "documents.api.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Healthcare Document Hub API",
    "DESCRIPTION": "Manage medical and lab-related documents.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["documents.api.permissions.CanViewDocuments"],
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Security (production) ------------------------------------------------
# DJANGO_HTTPS defaults to on outside DEBUG. Turn it off only for local,
# plain-HTTP container runs (see compose.yaml).
HTTPS = env_bool("DJANGO_HTTPS", not DEBUG)
SECURE_SSL_REDIRECT = HTTPS
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 3600) if HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS
# Preloading is hard to undo, so it is opt-in.
SECURE_HSTS_PRELOAD = HTTPS and env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
if env_bool("DJANGO_TRUST_X_FORWARDED_PROTO", False):
    # Only enable behind a proxy that always sets this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

# --- Logging --------------------------------------------------------------
# Console only. Nothing here logs request bodies, query data or file contents;
# `django.request` is raised to ERROR so 4xx paths aren't logged either.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"level": "ERROR"},
    },
}
