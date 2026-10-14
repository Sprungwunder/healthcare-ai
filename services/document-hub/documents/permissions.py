"""Roles are Django groups with model permissions.

- Reader: view, search and download documents.
- Editor: additionally create and edit all documents.
- Administrator: additionally delete documents and manage users (in the Django
  admin, which also needs `is_staff` on the user account).

The groups are created by a data migration. When changing the mapping below,
add a new data migration that calls `sync_role_groups` again.
"""

from typing import Any

from django.apps import apps as global_apps

READER = "Reader"
EDITOR = "Editor"
ADMIN = "Administrator"

_READER_PERMS = [
    "documents.view_document",
    "documents.view_tag",
]
_EDITOR_PERMS = [
    *_READER_PERMS,
    "documents.add_document",
    "documents.change_document",
    "documents.add_tag",
]
_ADMIN_PERMS = [
    *_EDITOR_PERMS,
    "documents.delete_document",
    "documents.change_tag",
    "documents.delete_tag",
    "auth.view_user",
    "auth.add_user",
    "auth.change_user",
    "auth.delete_user",
    "auth.view_group",
    "authtoken.view_token",
    "authtoken.add_token",
    "authtoken.change_token",
    "authtoken.delete_token",
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    READER: _READER_PERMS,
    EDITOR: _EDITOR_PERMS,
    ADMIN: _ADMIN_PERMS,
}


def sync_role_groups(apps: Any = global_apps) -> None:
    """Create the role groups and set their permissions to exactly the mapping.

    `apps` is the historical app registry when called from a migration.
    """
    group_model = apps.get_model("auth", "Group")
    permission_model = apps.get_model("auth", "Permission")
    for role, perm_names in ROLE_PERMISSIONS.items():
        group, _ = group_model.objects.get_or_create(name=role)
        permissions = []
        for perm_name in perm_names:
            app_label, codename = perm_name.split(".")
            permissions.append(
                permission_model.objects.get(
                    content_type__app_label=app_label, codename=codename
                )
            )
        group.permissions.set(permissions)
