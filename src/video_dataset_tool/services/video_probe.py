import json
import subprocess
from fractions import Fraction
from pathlib import Path

from ..core.models import VideoMetadata
from ..core.paths import find_binary, subprocess_options


class ProbeError(ValueError):
    pass


def probe_video(path: str | Path, binary: str | None = None) -> VideoMetadata:
    binary = binary or find_binary("ffprobe")
    if not binary:
        raise ProbeError(
            "Thiếu FFprobe. Cài FFmpeg và thêm thư mục bin vào PATH, sau đó mở lại ứng dụng."
        )
    if not Path(path).is_file():
        raise ProbeError("Không tìm thấy video nguồn hoặc không có quyền đọc.")
    try:
        result = subprocess.run(
            [binary, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            **subprocess_options(),
        )
        if result.returncode:
            raise ProbeError(
                "FFprobe không đọc được video. File có thể hỏng hoặc codec không được hỗ trợ."
            )
        data = json.loads(result.stdout)
        video = next(
            (
                s
                for s in data.get("streams", [])
                if s.get("codec_type") == "video"
                and not s.get("disposition", {}).get("attached_pic")
            ),
            None,
        )
        if video is None:
            raise ProbeError("File không có luồng video có thể đọc được.")
        duration = video.get("duration") or data.get("format", {}).get("duration")
        duration_ms = round(float(duration) * 1000)
        if duration_ms <= 0:
            raise ProbeError("Không xác định được thời lượng video hợp lệ.")
        try:
            fps = Fraction(video.get("avg_frame_rate", "0/1"))
        except (ValueError, ZeroDivisionError):
            fps = Fraction(0)
        audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
        return VideoMetadata(
            duration_ms,
            fps.numerator,
            fps.denominator,
            int(video.get("width", 0)),
            int(video.get("height", 0)),
            video.get("codec_name", "unknown"),
            audio.get("codec_name"),
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, StopIteration) as exc:
        if isinstance(exc, ProbeError):
            raise
        raise ProbeError(
            "Không đọc được thông số video. Kiểm tra file, quyền truy cập và FFprobe."
        ) from exc
