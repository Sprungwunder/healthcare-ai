"""Uniform API error format.

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "details": {...}}}

`details` holds field errors for validation failures and is empty otherwise.
"""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.fields import get_error_detail
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

VALIDATION_MESSAGE = "Die Eingabe ist ungültig."


class FileRejected(exceptions.APIException):
    """An uploaded file that is rejected with a specific HTTP status.

    `details` follows the validation-error shape (`{"file": ["..."]}`), so
    clients can handle 400, 413 and 415 upload errors the same way.
    """

    def __init__(
        self, message: str, *, code: str, status_code: int, field: str = "file"
    ) -> None:
        super().__init__(detail=message, code=code)
        self.status_code = status_code
        self.details = {field: [message]}


class FileTooLarge(FileRejected):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    def __init__(self, message: str) -> None:
        super().__init__(message, code="file_too_large", status_code=self.status_code)


class UnsupportedFileType(FileRejected):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def __init__(self, message: str) -> None:
        super().__init__(
            message, code="unsupported_file_type", status_code=self.status_code
        )


def _error_code(exc: exceptions.APIException) -> str:
    codes = exc.get_codes()
    if isinstance(codes, str):
        return codes
    return exc.default_code


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DjangoValidationError):
        # Raised by the service layer (e.g. duplicate files); treat like DRF's.
        exc = exceptions.ValidationError(detail=get_error_detail(exc))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound(*exc.args)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied(*exc.args)

    response = drf_exception_handler(exc, context)
    if response is None or not isinstance(exc, exceptions.APIException):
        return response

    details: Any
    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        message = VALIDATION_MESSAGE
        details = response.data
        if not isinstance(details, dict):
            details = {"non_field_errors": details}
    else:
        code = _error_code(exc)
        message = str(exc.detail)
        details = getattr(exc, "details", {})

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
