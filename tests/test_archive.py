import csv
import io
import json
import zipfile
from pathlib import Path

from breakout.archive import build_export_zip, validate_archive
from breakout.models import ExportSnapshot, ExportWarning


def test_archive_bundle_is_valid_and_excel_friendly(tmp_path: Path) -> None:
    snapshot = ExportSnapshot(
        source_service="spotify",
        account={"id": "user-1", "display_name": "A user"},
        exported_at="2026-07-14T11:00:00Z",
        collections={
            "playlists": [{"item_id": "p1", "title": "Commas, and \u03b1", "public": False}],
            "playlist_items": [
                {
                    "playlist_id": "p1",
                    "playlist_name": "Commas, and \u03b1",
                    "position": 1,
                    "item_id": "t1",
                    "title": "Quoted \"title\"",
                    "creators": ["Artist"],
                }
            ],
        },
        warnings=[
            ExportWarning("item_unavailable", "One item could not be read.", "playlist_items")
        ],
    )

    archive_path = build_export_zip(snapshot, tmp_path)
    assert archive_path.name == "breakout-spotify-2026-07-14T11-00-00Z.zip"

    with zipfile.ZipFile(archive_path) as bundle:
        names = set(bundle.namelist())
        assert {
            "archive.json",
            "manifest.json",
            "README.md",
            "breakout-archive-v1.schema.json",
            "csv/playlists.csv",
            "csv/playlist_items.csv",
            "csv/saved_tracks.csv",
        } <= names
        document = json.loads(bundle.read("archive.json"))
        validate_archive(document)
        assert document["warnings"][0]["code"] == "item_unavailable"

        csv_bytes = bundle.read("csv/playlist_items.csv")
        assert csv_bytes.startswith(b"\xef\xbb\xbf")
        rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        assert rows[0]["title"] == 'Quoted "title"'
        assert rows[0]["creators"] == '["Artist"]'

        manifest = json.loads(bundle.read("manifest.json"))
        assert "archive.json" in manifest["files"]
