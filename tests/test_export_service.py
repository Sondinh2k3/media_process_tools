import hashlib
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from video_dataset_tool.core.models import ClipRequest
from video_dataset_tool.core.paths import find_binary
from video_dataset_tool.services.export_service import export_clip
from video_dataset_tool.services.ffmpeg_service import build_arguments
from video_dataset_tool.services.video_probe import probe_video


@pytest.fixture
def clip_request(synthetic_video):
    return ClipRequest.create(
        synthetic_video,
        probe_video(synthetic_video),
        1200,
        3600,
        "positive",
        notes="Hàng hóa trên đường",
        event_start_ms=1500,
        event_end_ms=3000,
    )


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_export_and_source_immutable(clip_request, tmp_path, mode):
    source = Path(clip_request.source_path)
    before_stat = source.stat()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = export_clip(replace(clip_request, cut_mode=mode), tmp_path)
    assert result.status == "completed", result.error_message
    assert result.actual_start_ms is None
    assert Path(result.output_path).is_file()
    assert abs(probe_video(result.output_path).duration_ms - 2400) <= (
        3000 if mode == "fast" else 150
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert source.stat().st_size == before_stat.st_size
    old = Path(result.output_path).read_bytes()
    collision = export_clip(replace(clip_request, cut_mode=mode), tmp_path)
    assert collision.status == "failed"
    assert Path(result.output_path).read_bytes() == old
    assert not list(tmp_path.rglob("*.partial*"))


def test_argument_paths_are_single_arguments(clip_request, tmp_path):
    source = 'C:/Dữ liệu & video/$(không chạy); "mẫu".mp4'
    args = build_arguments(
        "ffmpeg", replace(clip_request, source_path=source), tmp_path / "out.mp4"
    )
    assert args[args.index("-i") + 1] == source
    assert args[args.index("-c") + 1] == "copy"
    assert "0:a?" in args


def test_cancel_before_export(clip_request, tmp_path):
    cancel = threading.Event()
    cancel.set()
    assert export_clip(clip_request, tmp_path, cancel).status == "cancelled"
    assert not list(tmp_path.iterdir())


def test_cancel_running_process(clip_request, tmp_path):
    original = build_arguments
    cancel = threading.Event()

    def slow_args(*args):
        result = original(*args)
        result.insert(result.index("-i"), "-re")
        return result

    timer = threading.Timer(0.4, cancel.set)
    with patch("video_dataset_tool.services.export_service.build_arguments", slow_args):
        timer.start()
        result = export_clip(clip_request, tmp_path, cancel)
        timer.join()
    assert result.status == "cancelled"
    assert not list(tmp_path.rglob("*.partial*"))
    assert not list(tmp_path.rglob("*.mkv"))


def test_failed_post_probe_is_not_success(clip_request, tmp_path):
    with patch(
        "video_dataset_tool.services.export_service.probe_video",
        side_effect=ValueError("Video hỏng"),
    ):
        result = export_clip(clip_request, tmp_path)
    assert result.status == "failed"
    assert not list(tmp_path.rglob("*.mkv"))


def test_zero_exit_is_not_sufficient(clip_request, tmp_path):
    # A real process returning zero while leaving our empty temporary file untouched.
    with patch(
        "video_dataset_tool.services.export_service.build_arguments",
        return_value=[find_binary("ffmpeg"), "-version"],
    ):
        result = export_clip(clip_request, tmp_path)
    assert result.status == "failed"
    assert "rỗng" in result.error_message


def test_missing_source(clip_request, tmp_path):
    result = export_clip(replace(clip_request, source_path=str(tmp_path / "absent.mp4")), tmp_path)
    assert result.status == "failed"


def test_no_audio(clip_request, tmp_path):
    silent = tmp_path / "không âm thanh.mp4"
    subprocess.run(
        [
            find_binary("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-i",
            clip_request.source_path,
            "-an",
            "-c:v",
            "copy",
            str(silent),
        ],
        check=True,
        capture_output=True,
    )
    for mode in ("fast", "precise"):
        clip = ClipRequest.create(silent, probe_video(silent), 1000, 3000, "normal", cut_mode=mode)
        result = export_clip(clip, tmp_path / "clips")
        assert result.status == "completed", result.error_message
        assert probe_video(result.output_path).audio_codec is None
