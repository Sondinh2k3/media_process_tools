import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QLockFile

from video_dataset_tool.cli import build_parser, parse_cli_time
from video_dataset_tool.core.models import ExportResult
from video_dataset_tool.core.paths import io_path
from video_dataset_tool.services.video_probe import probe_video
from video_dataset_tool.storage.database import Database
from video_dataset_tool.storage.repositories import Repository


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", 0),
        ("1.001", 1001),
        ("10.25", 10250),
        ("00:00:10", 10000),
        ("0:00:10.250", 10250),
        ("01:02:03.004", 3723004),
        ("100:00:00", 360000000),
    ],
)
def test_cli_time(value, expected):
    assert parse_cli_time(value) == expected


@pytest.mark.parametrize(
    "value", ["-1", "nan", "inf", "1e3", "1.0001", "00:60:00", "00:00:60", "1:20", ""]
)
def test_cli_bad_time(value):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_cli_time(value)


def run_cli(*args, timeout=45):
    environment = os.environ.copy()
    # A GUI launch would abort with this platform name; QtCore must work without a window.
    environment["QT_QPA_PLATFORM"] = "no_gui_platform_for_cli_test"
    return subprocess.run(
        [sys.executable, "-m", "video_dataset_tool", *map(str, args)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=timeout,
    )


@pytest.mark.parametrize("mode", ["precise", "fast"])
def test_cli_cut_direct_folder_id_sqlite_and_no_overwrite(synthetic_video, tmp_path, mode):
    source = tmp_path / "Video_ID_ABCD_1234-XYZ.mp4"
    shutil.copyfile(synthetic_video, source)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    stat = source.stat()
    output = tmp_path / "Thư mục kết quả"
    data = tmp_path / "metadata"
    args = [
        "cut",
        "--input",
        source,
        "--start",
        "1.200",
        "--duration",
        "2.400",
        "--output-dir",
        output,
        "--mode",
        mode,
        "--data-dir",
        data,
        "--json",
    ]
    first = run_cli(*args)
    assert first.returncode == 0, first.stderr
    payload = json.loads(first.stdout)
    path = Path(payload["output_path"])
    assert path.parent == output
    assert path.name.startswith(source.stem + "__00-00-01.200_00-00-03.600__")
    assert payload["video_id"] == source.stem
    assert payload["requested_out_ms"] == 3600
    assert payload["status"] == "completed"
    assert payload["encoding_preset"] == "veryfast"
    assert "Traceback" not in first.stderr
    assert probe_video(path).duration_ms == payload["actual_duration_ms"]
    previous_bytes = path.read_bytes()
    second = run_cli(*args)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["output_path"] != str(path)
    assert path.read_bytes() == previous_bytes
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    assert (source.stat().st_size, source.stat().st_mtime_ns) == (stat.st_size, stat.st_mtime_ns)
    database = Database(data / "dataset.sqlite3")
    rows = Repository(database).clips()
    assert len(rows) == 2
    assert all(row["status"] == "completed" and row["category"] == "uncertain" for row in rows)
    database.close()


def test_cli_bad_range_without_traceback(synthetic_video, tmp_path):
    result = run_cli(
        "cut",
        "--input",
        synthetic_video,
        "--start",
        "5",
        "--end",
        "2",
        "--output-dir",
        tmp_path / "clips",
        "--data-dir",
        tmp_path / "app",
        "--json",
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "failed"
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "clips").exists()


def test_cli_missing_source(tmp_path):
    result = run_cli(
        "cut",
        "--input",
        tmp_path / "missing.mp4",
        "--end",
        "2",
        "--output-dir",
        tmp_path / "clips",
        "--json",
    )
    assert result.returncode == 1
    assert "--input" in json.loads(result.stdout)["error_message"]
    assert "Traceback" not in result.stderr


def test_cli_invalid_output_persists_failed(synthetic_video, tmp_path):
    output = tmp_path / "existing_file"
    output.write_text("keep", encoding="utf-8")
    data = tmp_path / "app"
    result = run_cli(
        "cut",
        "--input",
        synthetic_video,
        "--end",
        "2",
        "--output-dir",
        output,
        "--data-dir",
        data,
        "--json",
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "failed"
    assert "Traceback" not in result.stderr
    database = Database(data / "dataset.sqlite3")
    assert Repository(database).clips()[0]["status"] == "failed"
    database.close()
    assert output.read_text() == "keep"


def test_cli_respects_shared_gui_lock(synthetic_video, tmp_path, qapp):
    data = tmp_path / "app"
    data.mkdir()
    lock = QLockFile(str(data / "session.lock"))
    lock.setStaleLockTime(0)
    assert lock.tryLock(0)
    try:
        result = run_cli(
            "cut",
            "--input",
            synthetic_video,
            "--end",
            "2",
            "--output-dir",
            tmp_path / "clips",
            "--data-dir",
            data,
            "--json",
        )
        assert result.returncode == 1
        assert "Dataset đang được mở" in json.loads(result.stdout)["error_message"]
        assert not (data / "dataset.sqlite3").exists()
    finally:
        lock.unlock()


def test_cli_parser_data_dir_before_or_after_cut():
    args = ["cut", "--input", "Video_000.mp4", "--end", "00:00:20", "--output-dir", "clips"]
    assert build_parser().parse_args(["--data-dir", "project", *args]).data_dir == Path("project")
    assert build_parser().parse_args([*args, "--data-dir", "project"]).data_dir == Path("project")
    assert build_parser().parse_args(args).mode == "precise"


def test_cli_sigint_records_cancelled_and_restores_handler(
    synthetic_video, tmp_path, monkeypatch, capsys, qapp
):
    from video_dataset_tool import cli

    previous_handler = signal.getsignal(signal.SIGINT)

    def cancel_via_sigint(request, output_root, cancel, progress, **kwargs):
        signal.raise_signal(signal.SIGINT)
        assert cancel.is_set()
        return ExportResult("cancelled", error_message="Đã hủy theo yêu cầu.")

    monkeypatch.setattr(cli, "export_clip", cancel_via_sigint)
    data = tmp_path / "app"
    code = cli.main(
        [
            "cut",
            "--input",
            str(synthetic_video),
            "--end",
            "2",
            "--output-dir",
            str(tmp_path / "clips"),
            "--data-dir",
            str(data),
            "--json",
        ]
    )
    assert code == 130
    assert json.loads(capsys.readouterr().out)["status"] == "cancelled"
    assert signal.getsignal(signal.SIGINT) == previous_handler
    database = Database(data / "dataset.sqlite3")
    assert Repository(database).clips()[0]["status"] == "cancelled"
    database.close()


def test_cli_long_source_path_keeps_full_id(synthetic_video, tmp_path):
    parent = tmp_path / ("folder_" * 12)
    Path(io_path(parent)).mkdir()
    source = parent / ("VIDEO_ABC_" + "0123456789" * 7 + ".mp4")
    shutil.copyfile(synthetic_video, io_path(source))
    output = tmp_path / "clips"
    result = run_cli(
        "cut",
        "--input",
        source,
        "--start",
        "1",
        "--end",
        "2",
        "--output-dir",
        output,
        "--data-dir",
        tmp_path / "app",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["output_path"]).name.startswith(source.stem + "__")
    assert probe_video(payload["output_path"]).duration_ms == 1000
