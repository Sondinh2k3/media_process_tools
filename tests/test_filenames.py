from dataclasses import replace

import pytest

from video_dataset_tool.core.filenames import clip_filename
from video_dataset_tool.core.models import ClipRequest, VideoMetadata


@pytest.fixture
def clip():
    return ClipRequest(
        "12345678-1234-4234-8234-123456789abc",
        "source-db-uuid",
        "/data/video_000.mp4",
        VideoMetadata(60000, 30, 1, 1920, 1080, "hevc"),
        10250,
        20750,
        "uncertain",
        cut_mode="precise",
        source_filename="Video_000.mp4",
    )


def test_keep_id_case_and_requested_times(clip):
    assert clip_filename(clip) == (
        "Video_000__00-00-10.250_00-00-20.750__12345678-1234-4234-8234-123456789abc.mp4"
    )
    assert clip_filename(replace(clip, cut_mode="fast")).endswith(".mkv")


def test_keep_entire_long_id(clip):
    video_id = "Camera_ABC_" + "1234567890" * 10
    assert clip_filename(replace(clip, source_filename=video_id + ".mp4")).startswith(
        video_id + "__"
    )


def test_keep_unicode_spaces_and_dots(clip):
    assert clip_filename(replace(clip, source_filename="ID_Đường phố.001.mp4")).startswith(
        "ID_Đường phố.001__"
    )


def test_do_not_silently_truncate_oversized_id(clip):
    with pytest.raises(ValueError, match="không tự cắt ngắn ID"):
        clip_filename(replace(clip, source_filename="A" * 240 + ".mp4"))
