import math
from uuid import UUID

from .models import CATEGORIES, ENCODING_PRESETS, ClipRequest


def validate_range(
    start: int, end: int, duration: int, before_s=0.0, after_s=0.0
) -> tuple[int, int]:
    if any(not isinstance(value, int) for value in (start, end, duration)):
        raise ValueError("Thời gian phải là số mili giây nguyên.")
    if duration <= 0 or start < 0 or end > duration or start >= end:
        raise ValueError("Khoảng cắt không hợp lệ: cần 0 ≤ IN < OUT ≤ thời lượng video.")
    if any(not math.isfinite(value) or value < 0 for value in (before_s, after_s)):
        raise ValueError("Padding phải là số giây không âm.")
    return max(0, start - round(before_s * 1000)), min(duration, end + round(after_s * 1000))


def validate_request(request: ClipRequest):
    try:
        if str(UUID(request.id)) != request.id:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Định danh clip phải là UUID hợp lệ.") from None
    validate_range(request.requested_in_ms, request.requested_out_ms, request.metadata.duration_ms)
    if request.category not in CATEGORIES:
        raise ValueError("Chọn một trong bốn nhóm tình huống V1.")
    if request.cut_mode not in {"fast", "precise"}:
        raise ValueError("Chế độ cắt không hợp lệ.")
    if request.encoding_preset not in ENCODING_PRESETS:
        raise ValueError("Preset mã hóa không hợp lệ.")
    if request.review_status not in {"unreviewed", "reviewed"}:
        raise ValueError("Trạng thái xem xét không hợp lệ.")
    start, end = request.event_start_ms, request.event_end_ms
    if (start is None) != (end is None):
        raise ValueError("Nhập cả bắt đầu và kết thúc sự kiện hoặc để trống cả hai.")
    if start is not None:
        validate_range(start, end, request.metadata.duration_ms)
        if start < request.requested_in_ms or end > request.requested_out_ms:
            raise ValueError("Khoảng sự kiện phải nằm trong khoảng clip xuất (đã tính padding).")
