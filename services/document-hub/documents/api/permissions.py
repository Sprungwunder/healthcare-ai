from typing import TYPE_CHECKING, Any

from rest_framework.permissions import BasePermission, DjangoModelPermissions

if TYPE_CHECKING:  # importing rest_framework.views here would be circular
    from rest_framework.request import Request
    from rest_framework.views import APIView


class ModelPermissionsWithView(DjangoModelPermissions):
    """`DjangoModelPermissions` that also requires the `view` permission for reads.

    The stock class lets every authenticated user read; here a user needs
    `<app>.view_<model>` (role "Leser" or higher) for GET/HEAD/OPTIONS.
    """

    perms_map: dict[str, list[str]] = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }


class CanViewDocuments(BasePermission):
    """For views without a model queryset (e.g. the OpenAPI schema)."""

    def has_permission(self, request: "Request", view: "APIView") -> bool:
        user: Any = request.user
        return bool(
            user and user.is_authenticated and user.has_perm("documents.view_document")
        )
