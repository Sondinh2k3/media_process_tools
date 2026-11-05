import os
import subprocess
import sys

import pytest

from video_dataset_tool.core.paths import find_binary, subprocess_options


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory):
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg or not find_binary("ffprobe"):
        pytest.skip("Cần FFmpeg/FFprobe cho integration test")
    folder = tmp_path_factory.mktemp("video") / "Dữ liệu thử có dấu"
    folder.mkdir()
    path = folder / "đường phố mẫu.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25:duration=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "50",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=45,
        **subprocess_options(),
    )
    return path


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_DATASET_DATA_DIR", str(tmp_path / "app"))


@pytest.fixture(scope="session", autouse=True)
def qt_test_environment():
    # The Windows offscreen platform cannot render fonts/video reliably on this host.
    # Exercise the native desktop there; use offscreen for Linux CI without a display.
    if sys.platform != "win32" and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
