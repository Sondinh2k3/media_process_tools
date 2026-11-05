import argparse
import json
import logging
import re
import signal
import sqlite3
import sys
import threading
from dataclasses import asdict
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Sequence

from .core.filenames import source_video_label
from .core.models import CATEGORIES, ENCODING_PRESETS, ClipRequest
from .core.paths import app_data_dir, io_path
from .core.timecode import format_timecode
from .core.validators import validate_request
from .services.export_service import export_clip
from .services.video_probe import probe_video
from .storage.database import Database
from .storage.repositories import Repository


def parse_cli_time(value: str) -> int:
    """Accept exact milliseconds as seconds or HH:MM:SS[.mmm], without float rounding."""
    value = value.strip()
    seconds = re.fullmatch(r"(\d+)(?:\.(\d{1,3}))?", value)
    clock = re.fullmatch(r"(\d{1,}):([0-5]\d):([0-5]\d)(?:\.(\d{1,3}))?", value)
    if seconds:
        return int(seconds[1]) * 1000 + int((seconds[2] or "").ljust(3, "0"))
    if clock:
        return ((int(clock[1]) * 60 + int(clock[2])) * 60 + int(clock[3])) * 1000 + int(
            (clock[4] or "").ljust(3, "0")
        )
    raise argparse.ArgumentTypeError(
        "Thời gian phải là số giây không âm (10.250) hoặc HH:MM:SS[.mmm] (00:00:10.250), tối đa 3 chữ số thập phân."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video_dataset_tool",
        description="Video Dataset Tool: mở giao diện hoặc cắt video bằng một lệnh.",
    )
    parser.add_argument("--data-dir", type=Path, help="Thư mục SQLite/log của dataset")
    parser.add_argument("--smoke-exit-ms", type=int, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", title="Lệnh")
    cut = commands.add_parser("cut", help="Cắt một clip, không mở cửa sổ giao diện")
    cut.add_argument("--input", required=True, type=Path, help="Video nguồn; tên file là ID video")
    cut.add_argument(
        "--start", type=parse_cli_time, default=0, help="IN: giây hoặc HH:MM:SS[.mmm]; mặc định 0"
    )
    bounds = cut.add_mutually_exclusive_group(required=True)
    bounds.add_argument("--end", type=parse_cli_time, help="OUT tính trên timeline nguồn")
    bounds.add_argument("--duration", type=parse_cli_time, help="Độ dài cần cắt tính từ --start")
    cut.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Thư mục đích; clip được ghi trực tiếp vào đây",
    )
    cut.add_argument(
        "--mode",
        choices=("precise", "fast"),
        default="precise",
        help="Mặc định precise/MP4; fast/MKV có thể lệch keyframe",
    )
    cut.add_argument(
        "--category",
        choices=tuple(CATEGORIES),
        default="uncertain",
        help="Nhóm lưu trong SQLite; mặc định uncertain",
    )
    cut.add_argument(
        "--preset",
        choices=ENCODING_PRESETS,
        default="veryfast",
        help="Preset H.264 cho precise: veryfast (mặc định), fast, medium; không dùng khi stream copy",
    )
    cut.add_argument("--notes", default="", help="Ghi chú tùy chọn")
    cut.add_argument(
        "--data-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Thư mục SQLite/log (có thể đặt trước hoặc sau cut)",
    )
    cut.add_argument(
        "--json", action="store_true", help="In kết quả JSON ra stdout, tiến độ vẫn ở stderr"
    )
    return parser


def _print_result(payload: dict, json_output: bool):
    if json_output:
        print(json.dumps(payload, ensure_ascii=False))
    elif payload["status"] == "completed":
        print(f"Đã cắt clip: {payload['output_path']}")
        print(f"ID video: {payload['video_id']}")
        print(
            f"Khoảng yêu cầu: {format_timecode(payload['requested_in_ms'])} → {format_timecode(payload['requested_out_ms'])}"
        )
        print(f"Thời lượng thực đo: {format_timecode(payload['actual_duration_ms'])}")
        print(f"Database: {payload['database_path']}")
        if payload["cut_mode"] == "fast":
            print(
                "Lưu ý: Fast có thể lệch điểm cắt theo keyframe; dùng --mode precise nếu cần sát thời gian."
            )
    else:
        print(payload["error_message"], file=sys.stderr)


def run_cut(args: argparse.Namespace) -> int:
    # QCoreApplication has no window and requires no display server. Reuse the GUI's lock format.
    from PySide6.QtCore import QCoreApplication, QLockFile

    core_application = QCoreApplication.instance() or QCoreApplication(["video-dataset-tool"])
    core_application.setApplicationName("VideoDatasetTool")
    core_application.setOrganizationName("VideoDatasetTool")
    database = lock = handler = None
    cancel = threading.Event()
    previous_sigint = None
    request = result = None
    payload = {"status": "failed"}
    try:
        source = args.input.expanduser().resolve()
        before = Path(io_path(source)).stat()
        metadata = probe_video(source)
        after = Path(io_path(source)).stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(
                "Video nguồn thay đổi trong lúc đọc thông số. Hãy thử lại khi file ổn định."
            )
        end_ms = args.end if args.end is not None else args.start + args.duration
        request = ClipRequest.create(
            source,
            metadata,
            args.start,
            end_ms,
            args.category,
            cut_mode=args.mode,
            encoding_preset=args.preset,
            notes=args.notes,
        )
        validate_request(request)
        output_dir = args.output_dir.expanduser().resolve()
        data_dir = (args.data_dir or app_data_dir()).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(data_dir / "session.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise ValueError(
                "Dataset đang được mở bởi giao diện hoặc lệnh khác. Đóng phiên đó hoặc chọn --data-dir khác."
            )
        handler = RotatingFileHandler(
            data_dir / "application.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8"
        )
        logging.getLogger().addHandler(handler)
        database = Database(data_dir / "dataset.sqlite3")
        repository = Repository(database)
        repository.recover_interrupted()
        row = repository.ensure_source(source)
        repository.update_source(row["id"], metadata)
        from dataclasses import replace

        request = replace(request, source_video_id=row["id"])
        repository.create_clip(request, output_dir)
        repository.set_processing(request.id)
        previous_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda signum, frame: cancel.set())
        last_progress = [-10]

        def progress(value):
            if value == 100 or value >= last_progress[0] + 10:
                print(f"Đang cắt: {value}%", file=sys.stderr, flush=True)
                last_progress[0] = value

        result = export_clip(request, output_dir, cancel, progress, group_by_category=False)
        repository.finish_clip(request.id, result)
        payload = {
            **asdict(result),
            "clip_id": request.id,
            "video_id": source_video_label(request),
            "source_video_id": request.source_video_id,
            "source_path": request.source_path,
            "requested_in_ms": request.requested_in_ms,
            "requested_out_ms": request.requested_out_ms,
            "cut_mode": request.cut_mode,
            "encoding_preset": request.encoding_preset,
            "database_path": str(database.path),
        }
    except (ValueError, OSError, sqlite3.Error) as exc:
        if handler is not None:
            logging.exception("Command-line cut failed")
        if isinstance(exc, FileNotFoundError):
            message = "Không tìm thấy video nguồn. Kiểm tra --input."
        elif isinstance(exc, PermissionError):
            message = "Không có quyền đọc nguồn hoặc ghi thư mục dữ liệu/đầu ra."
        elif isinstance(exc, sqlite3.Error):
            message = "Không lưu được metadata vào SQLite. Kiểm tra dung lượng/quyền ghi; clip đã tạo (nếu có) được giữ nguyên."
        elif isinstance(exc, OSError):
            message = "Lỗi đọc/ghi dữ liệu. Kiểm tra đường dẫn, dung lượng và quyền truy cập."
        else:
            message = str(exc)
        payload = {"status": "failed", "error_message": message}
        if result and result.output_path:
            payload["output_path"] = result.output_path
    except KeyboardInterrupt:
        payload = {"status": "cancelled", "error_message": "Đã hủy theo yêu cầu."}
    finally:
        if previous_sigint is not None:
            signal.signal(signal.SIGINT, previous_sigint)
        if database:
            database.close()
        if handler:
            logging.getLogger().removeHandler(handler)
            handler.close()
        if lock:
            lock.unlock()
    _print_result(payload, args.json)
    return (
        0 if payload["status"] == "completed" else (130 if payload["status"] == "cancelled" else 1)
    )


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.command == "cut":
        return run_cut(args)
    from .app import run_gui

    return run_gui(args.data_dir, args.smoke_exit_ms)
