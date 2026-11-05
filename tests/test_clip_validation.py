import pytest

from video_dataset_tool.core.validators import validate_range


@pytest.mark.parametrize(
    "values",
    [
        (0, 0, 6000),
        (4000, 1000, 6000),
        (-1, 4000, 6000),
        (0, 6001, 6000),
        (0, 1000, 0),
        (0, 1000, 6000, -1, 0),
        (0, 1000, 6000, float("nan"), 0),
    ],
)
def test_invalid_ranges(values):
    with pytest.raises(ValueError):
        validate_range(*values)


def test_padding_clamps_without_overwriting_event():
    assert validate_range(1000, 5000, 6000, 3, 5) == (0, 6000)
    assert validate_range(1000, 4000, 6000, 0.125, 0.25) == (875, 4250)
