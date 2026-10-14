from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from documents.permissions import sync_role_groups

# Old (German) group name -> new (English) name. Renaming keeps user memberships.
RENAMES = {"Leser": "Reader", "Redakteur": "Editor"}


def _rename(apps: Apps, mapping: dict[str, str]) -> None:
    group_model = apps.get_model("auth", "Group")
    for old, new in mapping.items():
        if not group_model.objects.filter(name=new).exists():
            group_model.objects.filter(name=old).update(name=new)


def forwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    _rename(apps, RENAMES)
    sync_role_groups(apps)


def backwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    _rename(apps, {new: old for old, new in RENAMES.items()})


class Migration(migrations.Migration):
    dependencies = [("documents", "0003_english_labels")]

    operations = [migrations.RunPython(forwards, backwards)]
