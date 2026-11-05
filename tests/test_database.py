import csv
import shutil
import sqlite3
from dataclasses import replace

import pytest

from video_dataset_tool.core.models import ClipRequest, ExportResult
from video_dataset_tool.services.video_probe import probe_video
from video_dataset_tool.storage.database import Database
from video_dataset_tool.storage.repositories import Repository


def test_migration_crud_reopen_csv_missing(synthetic_video, tmp_path):
    source = tmp_path / "nguồn có dấu.mp4"
    shutil.copyfile(synthetic_video, source)
    db_path = tmp_path / "data.sqlite3"
    database = Database(db_path)
    repo = Repository(database)
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    row = repo.ensure_source(source)
    assert repo.ensure_source(source.parent / "." / source.name)["id"] == row["id"]
    assert len(repo.sources()) == 1
    metadata = probe_video(source)
    repo.update_source(row["id"], metadata)
    clip = ClipRequest.create(
        source,
        metadata,
        1000,
        3000,
        "positive",
        source_video_id=row["id"],
        notes="Hàng hóa, cần xem xét\nDòng 2",
    )
    repo.create_clip(clip, tmp_path / "clips")
    repo.set_processing(clip.id)
    with pytest.raises(ValueError):
        repo.set_processing(clip.id)
    repo.finish_clip(clip.id, ExportResult("failed", error_message="Không ghi được"))
    repo.set_setting("output_root_dir", "Dữ liệu thử")
    repo.save_draft(row["id"], {"notes": "Bản nháp"})
    database.close()
    database = Database(db_path)
    repo = Repository(database)
    assert repo.get_setting("output_root_dir") == "Dữ liệu thử"
    assert repo.load_draft(row["id"])["notes"] == "Bản nháp"
    assert (
        len(
            repo.clips(source_id=row["id"], category="positive", status="failed", search="Hàng hóa")
        )
        == 1
    )
    assert not repo.clips(category="normal")
    csv_path = tmp_path / "danh mục.csv"
    repo.export_csv(csv_path)
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["notes"] == clip.notes
    assert rows[0]["requested_in_ms"] == "1000"
    assert rows[0]["event_start_ms"] == ""
    assert rows[0]["source_path"] == row["source_path"]
    with pytest.raises(ValueError):
        repo.export_csv(source)
    source.unlink()
    repo.refresh_availability()
    assert repo.sources()[0]["availability"] == "missing"
    assert len(repo.clips()) == 1
    assert repo.clips()[0]["source_availability"] == "missing"
    database.close()


def test_recover_interrupted_and_constraints(synthetic_video, tmp_path):
    database = Database(tmp_path / "data.sqlite3")
    repo = Repository(database)
    row = repo.ensure_source(synthetic_video)
    clip = ClipRequest.create(
        synthetic_video, probe_video(synthetic_video), 0, 1000, "normal", source_video_id=row["id"]
    )
    repo.create_clip(clip, tmp_path)
    repo.recover_interrupted()
    assert repo.clips()[0]["status"] == "failed"
    assert "gián đoạn" in repo.clips()[0]["error_message"]
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_clip(replace(clip, source_video_id="missing"), tmp_path)
    with pytest.raises(ValueError):
        repo.finish_clip(clip.id, ExportResult("completed"))
    database.close()


def test_refuse_future_schema(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(ValueError, match="mới hơn"):
        Database(path)
