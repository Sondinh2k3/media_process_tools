from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .paths import canonical_path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mts", ".m2ts", ".ts"}
CATEGORIES = {
    "positive": "Có tình huống nghi lấn chiếm",
    "hard_negative": "Dễ nhận nhầm",
    "normal": "Giao thông bình thường",
    "uncertain": "Chưa đủ thông tin",
}


@dataclass(frozen=True)
class VideoMetadata:
    duration_ms: int
    fps_num: int
    fps_den: int
    width: int
    height: int
    video_codec: str
    audio_codec: str | None = None

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den if self.fps_den else 0


@dataclass(frozen=True)
class ClipRequest:
    id: str
    source_video_id: str
    source_path: str
    metadata: VideoMetadata
    requested_in_ms: int
    requested_out_ms: int
    category: str
    cut_mode: str = "fast"
    object_type: str = ""
    notes: str = ""
    review_status: str = "unreviewed"
    event_start_ms: int | None = None
    event_end_ms: int | None = None
    source_size: int | None = None
    source_mtime_ns: int | None = None

    @classmethod
    def create(cls, source_path, metadata, start, end, category, **kwargs):
        stat = Path(source_path).stat()
        return cls(
            str(uuid4()),
            kwargs.pop("source_video_id", ""),
            canonical_path(source_path),
            metadata,
            start,
            end,
            category,
            source_size=stat.st_size,
            source_mtime_ns=stat.st_mtime_ns,
            **kwargs,
        )


@dataclass(frozen=True)
class ExportResult:
    status: str
    output_path: str | None = None
    actual_duration_ms: int | None = None
    actual_start_ms: int | None = None
    cut_precision: str = "unknown"
    error_message: str | None = None
