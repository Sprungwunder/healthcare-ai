from django.apps.registry import Apps
from django.contrib.auth.management import create_permissions
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from documents.permissions import sync_role_groups


def create_role_groups(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    # Permissions are normally created after `migrate` finishes (post_migrate);
    # create them now so the groups can reference them on a fresh database.
    for app_config in apps.get_app_configs():
        app_config.models_module = True  # type: ignore[assignment]
        create_permissions(app_config, apps=apps, verbosity=0)  # type: ignore[arg-type]
        app_config.models_module = None
    sync_role_groups(apps)


def remove_role_groups(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    from documents.permissions import ROLE_PERMISSIONS

    apps.get_model("auth", "Group").objects.filter(name__in=ROLE_PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("authtoken", "0004_alter_tokenproxy_options"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_role_groups, remove_role_groups)]
