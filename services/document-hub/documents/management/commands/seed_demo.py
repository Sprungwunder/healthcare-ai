"""Create synthetic demo documents (and optionally demo users).

Idempotent: documents whose file already exists (same checksum) are skipped,
existing users keep their password. No credentials live in this file; demo
users are only created when a password is passed via `--password` or the
`DOCUMENT_HUB_DEMO_PASSWORD` environment variable.
"""

import os
from typing import Any

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from documents import permissions, services
from documents.models import Document, DocumentType, Language

DEMO_NOTE = (
    "\n\n---\nSynthetic demo document of the Document Hub. Contains no real data.\n"
)

DEMO_DOCUMENTS: list[dict[str, Any]] = [
    {
        "filename": "lab-protocol-complete-blood-count.md",
        "title": "Lab Protocol: Complete Blood Count (Demo)",
        "document_type": DocumentType.LAB_PROTOCOL,
        "source": "Demo Lab Sampletown",
        "language": Language.ENGLISH,
        "tags": ["hematology", "routine", "demo"],
        "content": "# Complete blood count\n\nMeasurement on the hematology "
        "analyzer: mix the sample, start the measurement, check results "
        "for plausibility.",
    },
    {
        "filename": "sop-centrifugation.txt",
        "title": "SOP: Centrifugation of Serum Samples (Demo)",
        "document_type": DocumentType.SOP,
        "source": "Demo Lab Sampletown",
        "language": Language.ENGLISH,
        "tags": ["preanalytics", "equipment", "demo"],
        "content": "SOP: Let serum tubes clot for 30 minutes, then centrifuge "
        "for 10 minutes at 2000 g.",
    },
    {
        "filename": "guideline-hand-hygiene.md",
        "title": "Guideline: Hand Hygiene in the Laboratory (Demo)",
        "document_type": DocumentType.GUIDELINE,
        "source": "Demo Society for Laboratory Medicine",
        "source_url": "https://example.org/guidelines/hand-hygiene",
        "language": Language.ENGLISH,
        "tags": ["hygiene", "demo"],
        "content": "# Hand hygiene\n\nDisinfect hands before and after handling "
        "samples. Wear gloves when handling potentially infectious material.",
    },
    {
        "filename": "pcr-protocol.md",
        "title": "PCR Protocol: Nucleic Acid Extraction (Demo)",
        "document_type": DocumentType.LAB_PROTOCOL,
        "source": "Demo Molecular Lab",
        "language": Language.ENGLISH,
        "tags": ["pcr", "molecular biology", "demo"],
        "content": "# Extraction\n\n1. Lyse sample.\n2. Bind to column.\n"
        "3. Wash twice.\n4. Elute in 50 µl buffer.",
    },
    {
        "filename": "manual-analyzer-x100.txt",
        "title": "Technical Manual: Analyzer X100 (Demo)",
        "document_type": DocumentType.TECHNICAL_MANUAL,
        "source": "Demo Medical Devices Inc.",
        "language": Language.ENGLISH,
        "tags": ["equipment", "maintenance", "demo"],
        "content": "Maintenance: check reagents daily, clean measuring cells "
        "weekly, calibrate monthly.",
    },
    {
        "filename": "guideline-preanalytics-emergency.md",
        "title": "Guideline: Preanalytics in the Emergency Department (Demo)",
        "document_type": DocumentType.GUIDELINE,
        "source": "Demo Professional Society",
        "language": Language.ENGLISH,
        "tags": ["preanalytics", "emergency", "demo"],
        "content": "# Preanalytics\n\nDraw blood before starting therapy, follow "
        "the correct order of draw, transport samples promptly.",
    },
]

DEMO_USERS = [
    ("demo-reader", permissions.READER, False),
    ("demo-editor", permissions.EDITOR, False),
    ("demo-admin", permissions.ADMIN, True),
]


class Command(BaseCommand):
    help = "Create synthetic demo documents (and optionally demo users)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--password",
            help="Password for the demo users (or set "
            "DOCUMENT_HUB_DEMO_PASSWORD). Without a password no users are created.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        password = options.get("password") or os.environ.get(
            "DOCUMENT_HUB_DEMO_PASSWORD", ""
        )
        owner = self._create_users(password) if password else None
        if not password:
            self.stdout.write("No demo users created (no password given).")

        created = skipped = 0
        for spec in DEMO_DOCUMENTS:
            data = dict(spec)
            content = (data.pop("content") + DEMO_NOTE).encode()
            filename = data.pop("filename")
            try:
                services.create_document(
                    file=ContentFile(content, name=filename), created_by=owner, **data
                )
                created += 1
            except ValidationError:
                skipped += 1  # already seeded (duplicate checksum)
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} demo documents created, {skipped} already present "
                f"({Document.objects.count()} in total)."
            )
        )

    @transaction.atomic
    def _create_users(self, password: str) -> User:
        editor: User | None = None
        for username, role, is_staff in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username, defaults={"is_staff": is_staff}
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"User {username} ({role}) created.")
            user.groups.add(Group.objects.get(name=role))
            if role == permissions.EDITOR:
                editor = user
        assert editor is not None
        return editor
