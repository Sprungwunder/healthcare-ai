# Document Hub: Zusammenfassung

Erster Service im Mono-Repo: `services/document-hub/`. Er verwaltet medizinische
und laborbezogene Dokumente (Datei plus Metadaten) mit Suche, Rollen, REST-API
und deutscher Weboberfläche. Später soll er als Datenquelle für einen
RAG-Assistenten dienen. LLM, Embeddings, RAG und Elasticsearch sind bewusst
noch nicht enthalten.

## Architekturentscheidungen

| Thema | Entscheidung | Grund |
|---|---|---|
| Stack | Django 6.0, DRF 3.18, drf-spectacular (mit Sidecar, ohne CDN), dj-database-url, psycopg 3, gunicorn, whitenoise | DRF unterstützt Django 6 offiziell, Django 5.2 war daher nicht nötig. |
| Python/Tooling | ≥ 3.12, uv mit `uv.lock` | CI testet 3.12 und 3.14. |
| Core-Abhängigkeit | `[tool.uv.sources] healthcare-ai = { path = "../../packages/healthcare-ai-core" }` | **Abweichung vom Plan:** uv lehnt relative `file:`-URLs in `dependencies` ab. Die Wirkung ist dieselbe; die Konvention in `services/README.md` ist ergänzt. |
| Schichten | API und UI rufen nur `services.py` (Schreiben) und `search.py` (Lesen) auf. Die Regeln stehen in `validators.py`. | API und UI verhalten sich gleich. Der Service validiert selbst noch einmal, so greifen die Regeln auch für `seed_demo`. |
| Primärschlüssel | UUID | stabil für den späteren Abgleich mit einem externen Index |
| Dateiprüfung | Endung **und** Inhalt, nur Standardbibliothek | Umbenannte Dateien werden abgelehnt (415). |
| Duplikate | SHA-256 unique, 400 mit Verweis auf das vorhandene Dokument | Bei einer Race-Condition wird der `IntegrityError` in denselben Fehler übersetzt. |
| Dateien und Transaktionen | Erst validieren, dann die Datei schreiben, dann die DB-Zeile anlegen. Schlägt das fehl, wird die neue Datei entfernt. Alte Dateien werden erst nach dem Commit gelöscht. | Es bleiben keine verwaisten oder fehlenden Dateien zurück. |
| Suche | `DocumentSearchBackend`-Protocol, Wahl über `DOCUMENT_HUB_SEARCH_BACKEND` | Ein ES-Backend kommt später ohne Änderungen an API oder UI dazu. |
| Pipeline-Hooks | Signale `document_created/updated/deleted` per `on_commit`, Feld `processing_status` | Einhängepunkt für Textextraktion und Indexierung |
| Rollen | Gruppen Leser/Redakteur/Administrator über eine Daten-Migration (`sync_role_groups`) | GET braucht zusätzlich die `view`-Permission (`ModelPermissionsWithView`). |
| Auth | Token vor Session | Unangemeldete API-Aufrufe bekommen 401 (nicht 403). |
| Fehlerformat | `{"error": {"code", "message", "details"}}` für 400/401/403/404/413/415 | Fachliche Django-`ValidationError`s aus den Services werden ebenfalls übersetzt. |
| Downloads | nur über Views mit Rechteprüfung, `Cache-Control: private, no-store` | Es gibt keine öffentliche `MEDIA_URL`. |
| Settings | alles aus Env, optional `.env` (eigener kleiner Loader, ohne Extra-Abhängigkeit). `DJANGO_DEBUG` ist standardmäßig aus, ohne Secret Key startet nichts. | Sichere Voreinstellung. **Abweichung:** Lokal braucht es vorher `cp .env.example .env`. |
| HTTPS-Härtung | `DJANGO_HTTPS` (Standard: an, außer bei DEBUG), HSTS-Preload nur per Opt-in | compose läuft lokal per HTTP und schaltet die Härtung deshalb ab. |
| Admin | Dokumente im Django-Admin nur lesbar | Anlegen, Ändern und Löschen laufen über UI/API, damit Dateiregeln und Signale immer greifen. |
| Laufzeit-Generics | `django-stubs-ext` als Runtime-Abhängigkeit (`monkeypatch()`) | Für typisierte Views wie `ListView[Document]` |

## Was geändert wurde

Commits auf `feature/document-hub`:

1. Gerüst: pyproject/uv.lock, Settings, Docs für Agents, Settings-Smoke-Test
2. Modelle `Document`/`Tag`, Migrationen inkl. Rollen-Gruppen, Admin
3. Validatoren, Services und Signale
4. Such-Abstraktion
5. REST-API, Rechte, Fehlerformat, OpenAPI
6. Weboberfläche (Templates, responsives CSS, Forms, Views)
7. `seed_demo`, Dockerfile (+ `Dockerfile.dockerignore`), `compose.yaml`
8. CI-Job `document-hub` sowie Doku-Updates (`services/README.md`, `services/AGENTS.md`, Root-`AGENTS.md`/`README.md`, `docs/architecture.md`)

CI: Die `on:`-Filter enthalten jetzt `services/document-hub/**`. Ein `changes`-Job
(`dorny/paths-filter`) sorgt dafür, dass `document-hub` nur bei Änderungen am
Hub, an Core, an der Ruff-Config oder an der Workflow-Datei läuft. Der Job läuft
mit Python 3.12 und 3.14: `uv sync --locked`, ruff, mypy, pytest gegen einen
Postgres-17-Service-Container, danach `docker build` (nur 3.14). Der `core`-Job
ist unverändert. Er läuft jetzt aber auch, wenn nur der Hub geändert wird, weil
Filter auf Workflow-Ebene alle Jobs auslösen.

## Testergebnisse (lokal, 2026-10-14)

- `uv run pytest --cov`: **152 Tests grün, Coverage 97,7 %** (Grenze 90 %). Gleiches Ergebnis mit Python 3.12 und 3.14.
- Gleiche Suite gegen Postgres 17 (compose-`db`): grün.
- `uv run mypy .` (django-stubs, djangorestframework-stubs): keine Fehler.
- `ruff check .` / `ruff format --check .` von der Repo-Wurzel: sauber.
- Core: `pytest --cov=healthcare_ai` (100 %) und `mypy src` grün.
- `drf-spectacular --validate --fail-on-warn`: Schema ohne Warnungen.
- `docker compose up --build`, dann manuell per `curl`:
  - Rechte: anonym 401, Leser darf nicht anlegen (403), Redakteur darf nicht löschen (403), Admin löscht (204).
  - Upload, Suche nach Tags, PATCH und Download funktionieren.
  - Duplikat 400, gefälschte PDF 415, 10,5-MB-Datei 413.
  - Web-Flow per Session: Login, Upload, Suche, Bearbeiten (Redakteur), Löschen (Admin). Die Buttons erscheinen je nach Rolle.
  - `/media/` gibt 404 zurück.

Nicht geprüft: die Darstellung im Browser (Layout auf Desktop und Handy) und der
erste echte GitHub-Actions-Lauf.

## Bekannte Einschränkungen

- SQLite faltet bei `icontains` nur ASCII (`Ä` ≠ `ä`). Postgres macht das korrekt.
- Zu große Uploads werden erst nach dem Empfang abgelehnt. In Produktion sollte der Proxy die Request-Größe begrenzen (z. B. `client_max_body_size`).
- Wer `auth.change_user` hat, kann im Django-Admin auch `is_superuser` setzen (Standardverhalten von Django). Die Administrator-Rolle ist also faktisch voll vertrauenswürdig.
- Die Migration läuft beim Container-Start. Bei mehreren Replikas gehört sie in einen separaten Job.
- Tags werden alphabetisch zurückgegeben, nicht in der Reihenfolge der Eingabe.

## Nächste Schritte

1. PR öffnen und den ersten CI-Lauf prüfen (insbesondere die `setup-uv`/`paths-filter`-Versionen und den Docker-Build).
2. Optional: beim Upload bestätigen lassen, dass das Dokument keine Patientendaten enthält.
3. Textextraktion (PDF/DOCX) als Signal-Receiver mit `processing_status`, danach Embeddings und Index.
4. `ElasticsearchSearchBackend` mit Volltext, wenn die Titelsuche nicht mehr reicht.
5. Virenscan, Objekt-Storage (S3 über django-storages), Audit-Log.
6. Die Administrator-Rolle ohne Superuser-Eskalation (eigener `UserAdmin`).
