"""Validated, portable archive and CSV bundle generation."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
import zipfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from breakout.models import ExportSnapshot

CSV_COLUMNS: dict[str, list[str]] = {
    "playlists": [
        "item_id",
        "title",
        "description",
        "owner_id",
        "owner_name",
        "public",
        "collaborative",
        "item_count",
        "uri",
        "url",
        "image_url",
    ],
    "playlist_items": [
        "playlist_id",
        "playlist_name",
        "position",
        "added_at",
        "added_by_id",
        "item_type",
        "item_id",
        "title",
        "creators",
        "album_name",
        "release_date",
        "duration_ms",
        "isrc",
        "uri",
        "url",
        "is_local",
        "is_playable",
        "image_url",
    ],
    "saved_tracks": [
        "added_at",
        "item_id",
        "title",
        "creators",
        "album_name",
        "release_date",
        "duration_ms",
        "isrc",
        "uri",
        "url",
        "is_local",
        "is_playable",
        "image_url",
    ],
    "saved_albums": [
        "added_at",
        "item_id",
        "title",
        "creators",
        "release_date",
        "total_tracks",
        "upc",
        "uri",
        "url",
        "image_url",
    ],
    "followed_artists": ["item_id", "title", "genres", "uri", "url", "image_url"],
    "saved_shows": [
        "added_at",
        "item_id",
        "title",
        "creators",
        "description",
        "total_episodes",
        "uri",
        "url",
        "image_url",
    ],
    "saved_episodes": [
        "added_at",
        "item_id",
        "title",
        "creators",
        "show_name",
        "release_date",
        "duration_ms",
        "resume_position_ms",
        "uri",
        "url",
        "image_url",
    ],
    "saved_audiobooks": [
        "added_at",
        "item_id",
        "title",
        "creators",
        "description",
        "total_chapters",
        "uri",
        "url",
        "image_url",
    ],
}


def archive_schema() -> dict[str, Any]:
    resource = files("breakout").joinpath("schemas/breakout-archive-v1.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_archive(archive: dict[str, Any]) -> None:
    Draft202012Validator(archive_schema()).validate(archive)


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _cell(row.get(column)) for column in columns})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_timestamp(exported_at: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", exported_at).strip("-")


def _readme(snapshot: ExportSnapshot) -> str:
    return "\n".join(
        [
            "# BreakOut export",
            "",
            f"Source: {snapshot.source_service}",
            f"Exported at: {snapshot.exported_at}",
            "",
            "`archive.json` is the machine-transferable BreakOut Archive v1.0.",
            "The `csv` directory contains UTF-8-with-BOM tables that open directly in Excel.",
            "Warnings in `archive.json` describe items or collections that could not be read.",
            "",
        ]
    )


def build_export_zip(snapshot: ExportSnapshot, output_dir: Path) -> Path:
    """Write one self-describing ZIP archive and return its local temporary path."""

    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"breakout-build-{_safe_timestamp(snapshot.exported_at)}-"
    bundle_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=output_dir))
    csv_dir = bundle_dir / "csv"
    csv_dir.mkdir(exist_ok=True)

    archive = snapshot.archive_document()
    validate_archive(archive)
    (bundle_dir / "archive.json").write_text(
        json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for collection, columns in CSV_COLUMNS.items():
        _write_csv(csv_dir / f"{collection}.csv", columns, snapshot.collections.get(collection, []))

    schema_path = bundle_dir / "breakout-archive-v1.schema.json"
    schema_path.write_text(
        json.dumps(archive_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (bundle_dir / "README.md").write_text(_readme(snapshot), encoding="utf-8")

    manifest_files = {
        str(path.relative_to(bundle_dir)): {"sha256": _sha256(path), "bytes": path.stat().st_size}
        for path in sorted(bundle_dir.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "format": "breakout-export-manifest-1.0",
        "exported_at": snapshot.exported_at,
        "files": manifest_files,
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    filename = f"breakout-{snapshot.source_service}-{_safe_timestamp(snapshot.exported_at)}.zip"
    zip_path = output_dir / filename
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive_file:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                archive_file.write(path, path.relative_to(bundle_dir))
    return zip_path
