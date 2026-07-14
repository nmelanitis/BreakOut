"""Ephemeral local export jobs and their browser-visible state."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from breakout.archive import build_export_zip
from breakout.models import SourceConnector, utc_now


@dataclass(slots=True)
class ExportJob:
    id: str
    owner_session_id: str
    status: str = "queued"
    phase: str = "Waiting to start"
    completed: int = 0
    total: int | None = None
    error: str | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    archive_path: Path | None = None
    created_at: str = field(default_factory=utc_now)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "phase": self.phase,
            "completed": self.completed,
            "total": self.total,
            "error": self.error,
            "warnings": self.warnings,
            "created_at": self.created_at,
            "download_url": f"/exports/{self.id}/download" if self.status == "succeeded" else None,
        }


class JobManager:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or Path(tempfile.gettempdir()) / "breakout-exports"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, ExportJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def get(self, job_id: str) -> ExportJob | None:
        return self._jobs.get(job_id)

    async def start(self, owner_session_id: str, connector: SourceConnector) -> ExportJob:
        job = ExportJob(id=uuid.uuid4().hex, owner_session_id=owner_session_id)
        self._jobs[job.id] = job
        task = asyncio.create_task(self._run(job, connector))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: ExportJob, connector: SourceConnector) -> None:
        async def progress(phase: str, completed: int, total: int | None) -> None:
            job.phase = phase
            job.completed = completed
            job.total = total

        job.status = "running"
        try:
            snapshot = await connector.export(progress)
            job.phase = "Building portable archive"
            job.archive_path = build_export_zip(snapshot, self.output_dir)
            job.warnings = [asdict(warning) for warning in snapshot.warnings]
            job.completed = 1
            job.total = 1
            job.phase = "Export ready"
            job.status = "succeeded"
        except Exception as exc:
            # Errors are displayed to this local user, never re-raised into ASGI.
            job.status = "failed"
            job.phase = "Export failed"
            job.error = str(exc) or "Export failed unexpectedly."
        finally:
            close = getattr(connector, "aclose", None)
            if close:
                await close()
