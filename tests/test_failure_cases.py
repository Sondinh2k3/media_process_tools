import errno
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from video_dataset_tool.core.models import ClipRequest
from video_dataset_tool.core.paths import find_binary, subprocess_options
from video_dataset_tool.core.validators import validate_request
from video_dataset_tool.services.export_service import export_clip
from video_dataset_tool.services.video_probe import ProbeError, probe_video


@pytest.fixture
def clip(synthetic_video):
    return ClipRequest.create(
        synthetic_video, probe_video(synthetic_video), 1000, 3000, "uncertain"
    )


@pytest.mark.parametrize(
    "fault,expected", [("disk", "Dung lượng"), ("permission", "quyền"), ("write", "đọc/ghi")]
)
def test_output_failures_do_not_leave_clips(clip, tmp_path, fault, expected):
    if fault == "disk":
        target = "video_dataset_tool.services.export_service.shutil.disk_usage"
        mock = patch(target, return_value=Mock(free=0))
    elif fault == "permission":
        mock = patch(
            "video_dataset_tool.services.export_service.tempfile.mkstemp",
            side_effect=PermissionError(),
        )
    else:
        mock = patch(
            "video_dataset_tool.services.export_service.subprocess.Popen",
            side_effect=OSError(errno.ENOSPC, "disk full"),
        )
    with mock:
        result = export_clip(clip, tmp_path)
    assert result.status == "failed"
    assert expected in result.error_message
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_ffmpeg_failure_and_duration_rejection(clip, tmp_path):
    with patch(
        "video_dataset_tool.services.export_service.build_arguments",
        return_value=[find_binary("ffmpeg"), "-invalid_option_vdt"],
    ):
        result = export_clip(clip, tmp_path)
    assert result.status == "failed"
    with patch(
        "video_dataset_tool.services.export_service.probe_video",
        return_value=replace(clip.metadata, duration_ms=90000),
    ):
        result = export_clip(clip, tmp_path)
    assert result.status == "failed"
    assert "dung sai" in result.error_message
    assert not list(tmp_path.rglob("*.partial*"))
    assert not list(tmp_path.rglob("*.mkv"))


def test_source_changed_and_tools_missing(clip, tmp_path):
    result = export_clip(replace(clip, source_size=clip.source_size + 1), tmp_path)
    assert result.status == "failed"
    assert "đã thay đổi" in result.error_message
    with patch("video_dataset_tool.services.export_service.find_binary", return_value=None):
        result = export_clip(clip, tmp_path)
    assert result.status == "failed"
    assert "Thiếu" in result.error_message


def test_no_video_stream(clip):
    with patch(
        "video_dataset_tool.services.video_probe.subprocess.run",
        return_value=Mock(returncode=0, stdout='{"streams":[{"codec_type":"audio"}]}'),
    ):
        with pytest.raises(ProbeError, match="luồng video"):
            probe_video(clip.source_path, "ffprobe")


def test_long_filename(clip, tmp_path):
    path = tmp_path / ("tuyến phố " * 10 + ".mp4")
    shutil.copyfile(clip.source_path, path)
    request = ClipRequest.create(path, probe_video(path), 1000, 3000, "normal", cut_mode="precise")
    result = export_clip(request, tmp_path / "clips")
    assert result.status == "completed", result.error_message
    assert len(Path(result.output_path).name) < 90


def test_long_duration_over_one_hour(tmp_path):
    binary = find_binary("ffmpeg")
    if not binary or not find_binary("ffprobe"):
        pytest.skip("Cần FFmpeg/FFprobe")
    path = tmp_path / "video_dai.mp4"
    subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=64x48:rate=1:duration=3700",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            "2",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=45,
        **subprocess_options(),
    )
    metadata = probe_video(path)
    assert metadata.duration_ms == 3_700_000
    request = ClipRequest.create(path, metadata, 3_650_000, 3_653_000, "normal", cut_mode="precise")
    result = export_clip(request, tmp_path / "clips")
    assert result.status == "completed", result.error_message


def test_nonzero_source_timestamp(clip, tmp_path):
    path = tmp_path / "offset.mp4"
    subprocess.run(
        [
            find_binary("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-i",
            clip.source_path,
            "-c",
            "copy",
            "-output_ts_offset",
            "5",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
        **subprocess_options(),
    )
    metadata = probe_video(path)
    assert metadata.duration_ms == 6000
    result = export_clip(
        ClipRequest.create(path, metadata, 1000, 3000, "normal", cut_mode="precise"),
        tmp_path / "clips",
    )
    assert result.status == "completed", result.error_message


@pytest.mark.parametrize(
    "changes",
    [
        {"category": "other"},
        {"cut_mode": "other"},
        {"review_status": "other"},
        {"event_start_ms": 1200},
        {"event_start_ms": 500, "event_end_ms": 1500},
        {"event_start_ms": 2200, "event_end_ms": 2000},
        {"id": "../escape"},
    ],
)
def test_invalid_request_fields(clip, changes):
    with pytest.raises(ValueError):
        validate_request(replace(clip, **changes))


def test_variable_frame_rate(clip, tmp_path):
    import json

    path = tmp_path / "vfr.mp4"
    binary = find_binary("ffmpeg")
    subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-i",
            clip.source_path,
            "-vf",
            "select=not(mod(n\\,2))+not(mod(n\\,5))",
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-an",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=45,
        **subprocess_options(),
    )
    result = subprocess.run(
        [
            find_binary("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        **subprocess_options(),
    )
    times = [
        float(frame["best_effort_timestamp_time"]) for frame in json.loads(result.stdout)["frames"]
    ]
    assert len({round(b - a, 3) for a, b in zip(times, times[1:])}) > 1
    metadata = probe_video(path)
    for mode in ("fast", "precise"):
        request = ClipRequest.create(path, metadata, 1000, 3000, "normal", cut_mode=mode)
        result = export_clip(request, tmp_path / "clips")
        assert result.status == "completed", result.error_message
        output = probe_video(result.output_path)
        assert (output.width, output.height) == (metadata.width, metadata.height)
