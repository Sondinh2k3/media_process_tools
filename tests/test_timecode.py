import pytest

from video_dataset_tool.core.timecode import format_timecode, parse_timecode


@pytest.mark.parametrize("value", [0, 1, 1000, 3723480, 360000000])
def test_roundtrip(value):
    assert parse_timecode(format_timecode(value)) == value


@pytest.mark.parametrize(
    "value", ["1", "00:60:00.000", "00:00:60.000", "-1:00:00.000", "00:00:00.1", "abc"]
)
def test_invalid(value):
    with pytest.raises(ValueError):
        parse_timecode(value)


@pytest.mark.parametrize("value", [-1, 1.5, "1000"])
def test_invalid_formatter(value):
    with pytest.raises(ValueError):
        format_timecode(value)
