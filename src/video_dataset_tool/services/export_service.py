import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from ..core.models import ClipRequest, ExportResult
from ..core.paths import canonical_path, find_binary, subprocess_options
from ..core.validators import validate_request
from .ffmpeg_service import build_arguments
from .video_probe import probe_video


class ExportCancelled(Exception):
    pass


def duration_tolerance_ms(request: ClipRequest) -> int:
    if request.cut_mode == "precise":
        return max(150, round(2000 / request.metadata.fps)) if request.metadata.fps else 250
    return max(3000, round((request.requested_out_ms - request.requested_in_ms) * 0.1))


def export_clip(
    request: ClipRequest, output_root: Path, cancel: threading.Event | None = None, progress=None
) -> ExportResult:
    cancel = cancel or threading.Event()
    temporary = reserved = process = reader = None
    try:
        validate_request(request)
        if cancel.is_set():
            raise ExportCancelled()
        binary = find_binary("ffmpeg")
        if not binary or not find_binary("ffprobe"):
            raise ValueError("Thiếu FFmpeg/FFprobe. Kiểm tra PATH và mở lại ứng dụng.")
        source = Path(request.source_path)
        stat = source.stat()
        if (request.source_size is not None and stat.st_size != request.source_size) or (
            request.source_mtime_ns is not None and stat.st_mtime_ns != request.source_mtime_ns
        ):
            raise ValueError("Video nguồn đã thay đổi từ khi mở. Hãy mở lại video trước khi xuất.")
        folder = Path(output_root).expanduser().resolve() / request.category
        folder.mkdir(parents=True, exist_ok=True)
        fraction = (
            request.requested_out_ms - request.requested_in_ms
        ) / request.metadata.duration_ms
        estimate = max(
            1_048_576, int(stat.st_size * fraction * (1.2 if request.cut_mode == "fast" else 3))
        )
        if shutil.disk_usage(folder).free < estimate:
            raise ValueError(
                "Dung lượng trống không đủ theo ước lượng. Chọn ổ đĩa khác hoặc giải phóng dung lượng."
            )
        stem = re.sub(r"[^\w-]+", "_", source.stem, flags=re.UNICODE)[:36].strip("._") or "video"
        suffix = ".mkv" if request.cut_mode == "fast" else ".mp4"
        destination = folder / f"{stem}_{request.id}{suffix}"
        if canonical_path(source) == canonical_path(destination) or destination.exists():
            raise ValueError(
                "Tên clip đã tồn tại. Vui lòng tạo tác vụ xuất mới; clip cũ được giữ nguyên."
            )
        fd, filename = tempfile.mkstemp(
            prefix=f".vdt-{request.id}-", suffix=f".partial{suffix}", dir=folder
        )
        os.close(fd)
        temporary = Path(filename)
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                build_arguments(binary, request, temporary),
                stdout=subprocess.PIPE,
                stderr=errors,
                stdin=subprocess.DEVNULL,
                **subprocess_options(),
            )
            last_progress = [time.monotonic()]

            def read_progress():
                for raw in process.stdout:
                    last_progress[0] = time.monotonic()
                    line = raw.decode("utf-8", errors="replace").strip()
                    if progress and line.startswith("out_time_us="):
                        try:
                            ms = int(line.split("=", 1)[1]) / 1000
                            progress(
                                min(
                                    99,
                                    max(
                                        0,
                                        round(
                                            ms
                                            * 100
                                            / (request.requested_out_ms - request.requested_in_ms)
                                        ),
                                    ),
                                )
                            )
                        except ValueError:
                            pass

            reader = threading.Thread(target=read_progress, daemon=True)
            reader.start()
            while process.poll() is None:
                if cancel.wait(0.1):
                    raise ExportCancelled()
                if time.monotonic() - last_progress[0] > 180:
                    raise ValueError(
                        "FFmpeg không báo tiến độ trong 180 giây. Tác vụ đã được dừng an toàn."
                    )
            reader.join(timeout=5)
            if cancel.is_set():
                raise ExportCancelled()
            if process.returncode:
                errors.seek(0, os.SEEK_END)
                errors.seek(max(0, errors.tell() - 8000))
                logging.error("FFmpeg failed: %s", errors.read().decode("utf-8", errors="replace"))
                raise ValueError(
                    "FFmpeg xuất thất bại. Kiểm tra codec, quyền ghi và dung lượng đĩa; xem application.log để biết chi tiết."
                )
        if not temporary.is_file() or temporary.stat().st_size < 128:
            raise ValueError("File xuất rỗng hoặc quá nhỏ; không được ghi nhận thành công.")
        metadata = probe_video(temporary)
        expected = request.requested_out_ms - request.requested_in_ms
        if abs(metadata.duration_ms - expected) > duration_tolerance_ms(request):
            raise ValueError(
                "Thời lượng clip lệch quá dung sai kiểm tra. Thử chế độ Precise hoặc điều chỉnh khoảng cắt."
            )
        if cancel.is_set():
            raise ExportCancelled()
        with destination.open("xb"):
            pass
        reserved = destination
        os.replace(temporary, destination)
        temporary = reserved = None
        if progress:
            progress(100)
        return ExportResult(
            "completed",
            str(destination),
            metadata.duration_ms,
            None,
            "approximate" if request.cut_mode == "fast" else "unknown",
        )
    except ExportCancelled:
        return ExportResult(
            "cancelled", error_message="Đã hủy theo yêu cầu; video gốc được giữ nguyên."
        )
    except Exception as exc:
        logging.exception("Clip export failed")
        if isinstance(exc, PermissionError):
            message = "Không có quyền đọc nguồn hoặc ghi thư mục xuất. Chọn thư mục có quyền ghi."
        elif isinstance(exc, FileNotFoundError):
            message = "Không tìm thấy video nguồn hoặc công cụ FFmpeg. Kiểm tra đường dẫn và mở lại video."
        elif isinstance(exc, OSError):
            message = (
                "Lỗi đọc/ghi dữ liệu. Kiểm tra dung lượng đĩa, quyền truy cập và kết nối ổ đĩa."
            )
        else:
            message = str(exc)
        return ExportResult("failed", error_message=message)
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if reader:
            reader.join(timeout=5)
        if process and process.stdout:
            process.stdout.close()
        for path in (temporary, reserved):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logging.warning("Could not remove owned export temporary file", exc_info=True)
