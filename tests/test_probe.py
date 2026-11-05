from unittest.mock import Mock, patch

import pytest

from video_dataset_tool.services.video_probe import ProbeError, probe_video


def test_probe_synthetic(synthetic_video):
    metadata = probe_video(synthetic_video)
    assert metadata.duration_ms == 6000
    assert (metadata.width, metadata.height) == (320, 240)
    assert (metadata.fps_num, metadata.fps_den) == (25, 1)
    assert metadata.audio_codec == "aac"


def test_probe_missing(tmp_path):
    with pytest.raises(ProbeError):
        probe_video(tmp_path / "absent.mp4", "ffprobe")


def test_invalid_codec(tmp_path):
    file = tmp_path / "bad.mp4"
    file.write_bytes(b"invalid")
    with patch(
        "video_dataset_tool.services.video_probe.subprocess.run",
        return_value=Mock(returncode=1, stdout="", stderr="Unsupported codec"),
    ):
        with pytest.raises(ProbeError, match="codec"):
            probe_video(file, "ffprobe")
