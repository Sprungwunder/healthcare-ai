"""Document lifecycle signals, the hook for indexing and processing.

They are sent only after the surrounding transaction commits
(`transaction.on_commit`), so receivers never see rolled-back changes.
A future search index or text-extraction pipeline connects here.

- `document_created(sender=Document, document=...)`
- `document_updated(sender=Document, document=..., file_replaced=bool)`
- `document_deleted(sender=Document, document_id=UUID)`
"""

from django.dispatch import Signal

document_created = Signal()
document_updated = Signal()
document_deleted = Signal()
