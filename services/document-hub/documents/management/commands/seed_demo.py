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
    "\n\n---\nSynthetisches Demo-Dokument des Document Hub. "
    "Enthält keine echten Daten.\n"
)

DEMO_DOCUMENTS: list[dict[str, Any]] = [
    {
        "filename": "laborprotokoll-blutbild.md",
        "title": "Laborprotokoll: Kleines Blutbild (Demo)",
        "document_type": DocumentType.LAB_PROTOCOL,
        "source": "Demo-Labor Musterstadt",
        "language": Language.GERMAN,
        "tags": ["hämatologie", "routine", "demo"],
        "content": "# Kleines Blutbild\n\nAblauf der Messung am Hämatologie-"
        "Analysator: Probe mischen, Messung starten, Ergebnisse plausibilisieren.",
    },
    {
        "filename": "sop-zentrifuge.txt",
        "title": "SOP Zentrifugation von Serumproben (Demo)",
        "document_type": DocumentType.SOP,
        "source": "Demo-Labor Musterstadt",
        "language": Language.GERMAN,
        "tags": ["präanalytik", "geräte", "demo"],
        "content": "SOP: Serumröhrchen 30 Minuten gerinnen lassen, dann "
        "10 Minuten bei 2000 g zentrifugieren.",
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
        "tags": ["pcr", "molekularbiologie", "demo"],
        "content": "# Extraction\n\n1. Lyse sample.\n2. Bind to column.\n"
        "3. Wash twice.\n4. Elute in 50 µl buffer.",
    },
    {
        "filename": "handbuch-analysator.txt",
        "title": "Technisches Handbuch: Analysator X100 (Demo)",
        "document_type": DocumentType.TECHNICAL_MANUAL,
        "source": "Demo-Medizintechnik GmbH",
        "language": Language.GERMAN,
        "tags": ["geräte", "wartung", "demo"],
        "content": "Wartung: Täglich Reagenzien prüfen, wöchentlich "
        "Messzellen reinigen, monatlich Kalibrierung durchführen.",
    },
    {
        "filename": "leitlinie-praeanalytik.md",
        "title": "Leitlinie Präanalytik in der Notaufnahme (Demo)",
        "document_type": DocumentType.GUIDELINE,
        "source": "Demo-Fachgesellschaft",
        "language": Language.GERMAN,
        "tags": ["präanalytik", "notfall", "demo"],
        "content": "# Präanalytik\n\nBlutentnahme vor Therapiebeginn, "
        "korrekte Röhrchenreihenfolge beachten, Proben zeitnah transportieren.",
    },
]

DEMO_USERS = [
    ("demo-leser", permissions.READER, False),
    ("demo-redakteur", permissions.EDITOR, False),
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
