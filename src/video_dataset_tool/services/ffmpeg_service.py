from pathlib import Path

from ..core.models import ClipRequest
from ..core.validators import validate_request


def build_arguments(binary: str, request: ClipRequest, temporary_path: Path) -> list[str]:
    validate_request(request)
    start = f"{request.requested_in_ms / 1000:.3f}"
    duration = f"{(request.requested_out_ms - request.requested_in_ms) / 1000:.3f}"
    args = [
        binary,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
    ]
    if request.cut_mode == "fast":
        args += [
            "-ss",
            start,
            "-noautorotate",
            "-i",
            request.source_path,
            "-t",
            duration,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
        ]
    else:
        args += [
            "-ss",
            start,
            "-noautorotate",
            "-i",
            request.source_path,
            "-t",
            duration,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
        ]
    return args + [str(temporary_path)]
