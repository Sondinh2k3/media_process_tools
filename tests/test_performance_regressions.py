"""Behavior checks for optimizations; avoid machine-dependent timing thresholds."""

import csv
import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt

from video_dataset_tool.cli import build_parser
from video_dataset_tool.core.models import ClipRequest, VideoMetadata
from video_dataset_tool.core.validators import validate_request
from video_dataset_tool.services.ffmpeg_service import build_arguments
from video_dataset_tool.services.video_probe import cached_metadata
from video_dataset_tool.storage.database import Database
from video_dataset_tool.storage.migrations import SCHEMA
from video_dataset_tool.storage.repositories import Repository
from video_dataset_tool.ui.clip_editor import ClipEditor
from video_dataset_tool.ui.clip_table import ClipTable


@pytest.fixture
def library(tmp_path):
    database = Database(tmp_path / "library.sqlite3")
    repository = Repository(database)
    source = repository.ensure_source(tmp_path / "Video_ID.mp4")
    stamp = "2026-01-01T00:00:00Z"
    with database.connection:
        database.connection.executemany(
            "INSERT INTO clips(id,source_video_id,source_path_snapshot,requested_in_ms,requested_out_ms,category,cut_mode,output_root,status,created_at,updated_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    str(uuid4()),
                    source["id"],
                    source["source_path"],
                    0,
                    1000,
                    "normal" if i % 2 else "positive",
                    "precise",
                    str(tmp_path),
                    "completed",
                    stamp,
                    stamp,
                    f"Ghi chú {i:04d}",
                )
                for i in range(405)
            ],
        )
    yield repository, source
    database.close()


def test_v1_migration_preserves_history_and_legacy_preset(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA + "PRAGMA user_version=1;")
        connection.execute(
            "INSERT INTO source_videos(id,source_path,display_name,created_at,last_seen_at) VALUES('source','/video','Video_ID.mp4','date','date')"
        )
        connection.execute(
            "INSERT INTO clips(id,source_video_id,source_path_snapshot,requested_in_ms,requested_out_ms,category,cut_mode,output_root,status,created_at,updated_at,notes) VALUES('old','source','/video',0,1000,'normal','precise','/out','completed','date','date','Ghi chú cũ')"
        )
    database = Database(path)
    try:
        row = Repository(database).clips()[0]
        assert row["id"] == "old"
        assert row["notes"] == "Ghi chú cũ"
        assert row["encoding_preset"] == "medium"
        assert database.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        database.close()


def test_pagination_stable_ties_filters_and_full_csv(library, tmp_path):
    repository, source = library
    first = repository.clips(limit=200)
    second = repository.clips(limit=200, offset=200)
    last = repository.clips(limit=200, offset=400)
    assert len(first) == len(second) == 200 and len(last) == 5
    assert len({row["id"] for row in first + second + last}) == 405
    assert first == repository.clips(limit=200)
    filters = (source["id"], "normal", "completed", "Ghi chú")
    assert repository.count_clips(*filters) == len(repository.clips(*filters)) == 202
    assert repository.count_clips(search="%") == 0
    assert repository.count_clips(search="__") == 0
    path = tmp_path / "all.csv"
    repository.export_csv(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 405
    with pytest.raises(ValueError):
        repository.clips(limit=-1)


def test_bulk_sources_deduplicate_and_drafts_skip_identical_writes(library, tmp_path):
    repository, source = library
    changes = repository.connection.total_changes
    repository.save_draft(source["id"], {"notes": "Nháp", "preset": "veryfast"})
    repository.set_setting("example", "giữ lại")
    for _ in range(10):
        repository.save_draft(source["id"], {"notes": "Nháp", "preset": "veryfast"})
        repository.set_setting("example", "giữ lại")
    assert repository.connection.total_changes - changes == 2
    paths = [tmp_path / f"Video_{i}.mp4" for i in range(1002)]
    commits = []
    repository.connection.set_trace_callback(
        lambda sql: commits.append(sql) if sql == "COMMIT" else None
    )
    records = repository.ensure_sources(paths + paths)
    repository.connection.set_trace_callback(None)
    assert len(commits) == 1
    assert records[:1002] == records[1002:]
    assert len(repository.sources()) == 1003
    assert repository.ensure_sources([]) == []


def test_table_debounces_search_pages_and_preserves_selection(qtbot, library, monkeypatch):
    repository, _ = library
    table = ClipTable(repository)
    qtbot.addWidget(table)
    assert table.total == 405 and table.model.rowCount() == 200
    assert not table.previous_button.isEnabled() and table.next_button.isEnabled()
    table.table.selectRow(7)
    selected = table.selected()["id"]
    table.refresh()
    assert table.selected()["id"] == selected
    table.change_page(1)
    assert table.page == 1 and table.model.rowCount() == 200
    table.change_page(1)
    assert table.model.rowCount() == 5 and not table.next_button.isEnabled()
    calls = []
    original = repository.clips

    def query(*args, **kwargs):
        calls.append(True)
        assert kwargs["limit"] == 200
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "clips", query)
    for term in ("G", "Gh", "Ghi", "Ghi chú", "Ghi chú 0001"):
        table.search.setText(term)
    assert not calls
    qtbot.waitUntil(lambda: len(calls) == 1)
    assert table.page == 0 and table.total == 1 and table.model.rowCount() == 1
    assert table.model.data(table.model.index(0, 7)) == "Ghi chú 0001"
    assert table.model.headerData(0, Qt.Orientation.Horizontal) == "Clip"
    table.search.setText("không có kết quả")
    qtbot.waitUntil(lambda: table.total == 0)
    assert table.selected() is None


def test_metadata_cache_checks_source_identity(tmp_path):
    path = tmp_path / "Video_ID.mp4"
    path.write_bytes(b"synthetic identity")
    database = Database(tmp_path / "cache.sqlite3")
    try:
        repository = Repository(database)
        source = repository.ensure_source(path)
        metadata = VideoMetadata(10000, 25, 1, 320, 240, "h264", None)
        assert cached_metadata(source) is None
        repository.update_source(source["id"], metadata)
        source = repository.ensure_source(path)
        assert cached_metadata(source) == metadata
        assert cached_metadata({**source, "availability": "missing"}) is None
        assert cached_metadata({**source, "availability": "changed"}) is None
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
        assert cached_metadata(source) is None
        path.unlink()
        assert cached_metadata(source) is None
    finally:
        database.close()


@pytest.mark.parametrize("preset", ["veryfast", "fast", "medium"])
def test_preset_validation_arguments_and_cli(tmp_path, preset):
    request = ClipRequest(
        str(uuid4()),
        "source",
        str(tmp_path / "Video.mp4"),
        VideoMetadata(5000, 25, 1, 320, 240, "h264"),
        1000,
        3000,
        "normal",
        cut_mode="precise",
        encoding_preset=preset,
    )
    args = build_arguments("ffmpeg", request, Path("clip.mp4"))
    assert args[args.index("-preset") + 1] == preset
    assert args[args.index("-crf") + 1] == "18"
    assert "-vf" not in args and "-r" not in args
    assert "-preset" not in build_arguments(
        "ffmpeg", replace(request, cut_mode="fast"), Path("clip.mkv")
    )
    parsed = build_parser().parse_args(
        ["cut", "--input", "Video.mp4", "--end", "1", "--output-dir", "out", "--preset", preset]
    )
    assert parsed.preset == preset
    with pytest.raises(ValueError, match="Preset"):
        validate_request(replace(request, encoding_preset="invalid"))


def test_editor_actions_and_preset_draft(qtbot):
    editor = ClipEditor()
    qtbot.addWidget(editor)
    assert not editor.export_button.isEnabled() and not editor.preview_button.isEnabled()
    editor.load_draft({"mode": "precise", "preset": "medium"}, 5000)
    editor.set_source_ready(True)
    assert editor.export_button.isEnabled() and editor.preset.isEnabled()
    assert editor.draft()["preset"] == "medium"
    editor.set_busy(True)
    assert not editor.export_button.isEnabled() and editor.cancel_button.isEnabled()
    editor.end.setText("00:00:00.000")
    editor.set_busy(False)
    assert not editor.export_button.isEnabled() and not editor.preview_button.isEnabled()
    editor.load_draft({}, 5000)
    assert editor.export_button.isEnabled() and not editor.preset.isEnabled()
