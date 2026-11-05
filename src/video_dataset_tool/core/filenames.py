import re
from pathlib import Path

from .models import ClipRequest
from .timecode import format_timecode


def source_video_label(request: ClipRequest) -> str:
    """Return the user's video ID (filename stem), distinct from the database UUID."""
    return Path(request.source_filename or request.source_path).stem


def clip_filename(request: ClipRequest) -> str:
    # Preserve the entire ID and its case. Only replace characters forbidden on Windows.
    label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", source_video_label(request))
    if not label or label in {".", ".."}:
        raise ValueError("Tên video nguồn không chứa ID hợp lệ để đặt tên clip.")
    start = format_timecode(request.requested_in_ms).replace(":", "-")
    end = format_timecode(request.requested_out_ms).replace(":", "-")
    suffix = ".mkv" if request.cut_mode == "fast" else ".mp4"
    name = f"{label}__{start}_{end}__{request.id}{suffix}"
    if len(name.encode("utf-8")) > 255:
        raise ValueError(
            "ID video quá dài để ghép tên clip an toàn (tối đa 255 byte UTF-8). "
            "Ứng dụng không tự cắt ngắn ID; hãy dùng ID/tên nguồn ngắn hơn cho bản sao làm việc."
        )
    return name
