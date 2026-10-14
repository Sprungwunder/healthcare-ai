from django.http import FileResponse, Http404

from documents.models import Document


def document_file_response(document: Document) -> FileResponse:
    """Stream the stored file as an attachment under its original name.

    Callers are responsible for the permission check.
    """
    try:
        handle = document.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Die Datei zu diesem Dokument wurde nicht gefunden.") from exc
    response = FileResponse(
        handle,
        as_attachment=True,
        filename=document.original_filename,
        content_type=document.mime_type,
    )
    response["Cache-Control"] = "private, no-store"
    return response
