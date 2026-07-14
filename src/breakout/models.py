"""Provider-neutral export types and future extension points."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

JSONRecord = dict[str, Any]
ProgressCallback = Callable[[str, int, int | None], Awaitable[None]]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class ExportWarning:
    code: str
    message: str
    collection: str | None = None
    resource_id: str | None = None
    status_code: int | None = None


@dataclass(slots=True)
class ExportSnapshot:
    """The canonical, provider-neutral data handed to archive writers."""

    source_service: str
    account: JSONRecord
    collections: dict[str, list[JSONRecord]] = field(default_factory=dict)
    warnings: list[ExportWarning] = field(default_factory=list)
    exported_at: str = field(default_factory=utc_now)

    def archive_document(self) -> JSONRecord:
        return {
            "schema_version": "1.0",
            "exported_at": self.exported_at,
            "source": {"service": self.source_service, "account": self.account},
            "collections": self.collections,
            "warnings": [asdict(warning) for warning in self.warnings],
        }


class SourceConnector(Protocol):
    """A read-only provider connector that produces one normalized snapshot."""

    async def current_user(self) -> JSONRecord: ...

    async def export(self, progress: ProgressCallback) -> ExportSnapshot: ...


class ArchiveImporter(Protocol):
    """Contract for a future destination-service importer."""

    name: str

    async def import_archive(self, archive: JSONRecord) -> list[JSONRecord]:
        """Return an item-by-item result without changing the source archive."""
