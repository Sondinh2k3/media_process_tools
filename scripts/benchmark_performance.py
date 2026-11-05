"""Opt-in local benchmark. Source videos are read only; all artifacts stay in a new run folder."""

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtWidgets import QApplication

from video_dataset_tool.core.models import ClipRequest
from video_dataset_tool.core.paths import find_binary, io_path, subprocess_options
from video_dataset_tool.services.export_service import export_clip
from video_dataset_tool.services.video_probe import probe_video
from video_dataset_tool.storage.database import Database
from video_dataset_tool.storage.repositories import Repository, utc_now
from video_dataset_tool.ui.clip_table import ClipTable


def measure_library(folder):
    app = QApplication.instance() or QApplication(["vdt-benchmark"])
    database = Database(folder / "synthetic.sqlite3")
    repo = Repository(database)
    try:
        started = time.perf_counter()
        sources = repo.ensure_sources([folder / f"Video_{i:04d}.mp4" for i in range(500)])
        registration = time.perf_counter() - started
        stamp = utc_now()
        with database.connection:
            database.connection.executemany(
                "INSERT INTO clips(id,source_video_id,source_path_snapshot,requested_in_ms,requested_out_ms,category,cut_mode,output_root,status,created_at,updated_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        str(uuid4()),
                        sources[0]["id"],
                        sources[0]["source_path"],
                        0,
                        1000,
                        "uncertain",
                        "precise",
                        str(folder),
                        "completed",
                        stamp,
                        stamp,
                        f"Ghi chu {i:05d}",
                    )
                    for i in range(10000)
                ],
            )
        started = time.perf_counter()
        table = ClipTable(repo)
        initialization = time.perf_counter() - started
        started = time.perf_counter()
        for term in ("G", "Gh", "Ghi", "Ghi ", "Ghi c", "Ghi ch", "Ghi chu"):
            table.search.setText(term)
        typing = time.perf_counter() - started
        while table.search_timer.isActive():
            app.processEvents()
            time.sleep(0.001)
        settled = time.perf_counter() - started
        changes = database.connection.total_changes
        started = time.perf_counter()
        for _ in range(100):
            repo.save_draft(sources[0]["id"], {"notes": "unchanged"})
        draft_time = time.perf_counter() - started
        report = {
            "clip_count": 10000,
            "source_registration_500_s": registration,
            "table_initialization_s": initialization,
            "search_7_keystrokes_s": typing,
            "search_including_debounce_s": settled,
            "visible_rows": table.model.rowCount(),
            "identical_draft_100_s": draft_time,
            "draft_rows_changed": database.connection.total_changes - changes,
        }
        table.close()
        table.deleteLater()
        app.processEvents()
        return report
    finally:
        database.close()


def measure_video(source, folder, start_ms, end_ms):
    source = source.resolve()
    before = source.stat()
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    metadata = probe_video(source)
    samples = []
    for trial, presets in enumerate((("medium", "veryfast"), ("veryfast", "medium")), 1):
        for preset in presets:
            request = ClipRequest.create(
                source,
                metadata,
                start_ms,
                end_ms,
                "uncertain",
                cut_mode="precise",
                encoding_preset=preset,
            )
            started = time.perf_counter()
            result = export_clip(request, folder, group_by_category=False)
            elapsed = time.perf_counter() - started
            if result.status != "completed":
                raise RuntimeError(result.error_message)
            samples.append(
                {
                    "trial": trial,
                    "preset": preset,
                    "elapsed_s": elapsed,
                    "output_path": result.output_path,
                    "size_bytes": Path(result.output_path).stat().st_size,
                    "duration_ms": result.actual_duration_ms,
                }
            )
            print(f"{preset}: {elapsed:.3f}s", flush=True)
    quality = validate_video(source, samples, start_ms)
    after = source.stat()
    with source.open("rb") as stream:
        unchanged = (before.st_size, before.st_mtime_ns, digest) == (
            after.st_size,
            after.st_mtime_ns,
            hashlib.file_digest(stream, "sha256").hexdigest(),
        )
    if not unchanged:
        raise RuntimeError("Source identity changed during benchmark")
    return {
        "samples": samples,
        "quality": quality,
        "source_unchanged": unchanged,
        "source_sha256": digest,
        "start_ms": start_ms,
        "end_ms": end_ms,
    }


def validate_video(source, samples, start_ms):
    """Full decode plus a first-frame smoke comparison; not a perceptual quality certification."""
    binary = find_binary("ffmpeg")

    def frame(path, position):
        return subprocess.run(
            [
                binary,
                "-v",
                "error",
                "-nostdin",
                "-ss",
                f"{position / 1000:.3f}",
                "-noautorotate",
                "-i",
                io_path(path),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "-",
            ],
            check=True,
            capture_output=True,
            timeout=120,
            **subprocess_options(),
        ).stdout

    reference = frame(source, start_ms)
    quality = []
    for sample in samples:
        subprocess.run(
            [
                binary,
                "-v",
                "error",
                "-nostdin",
                "-xerror",
                "-i",
                sample["output_path"],
                "-f",
                "null",
                "-",
            ],
            check=True,
            capture_output=True,
            timeout=120,
            **subprocess_options(),
        )
        image = frame(sample["output_path"], 0)
        if not image or len(image) != len(reference):
            raise RuntimeError("Decoded first-frame dimensions differ from source")
        mae = sum(abs(a - b) for a, b in zip(reference, image)) / len(reference)
        quality.append(
            {
                "preset": sample["preset"],
                "trial": sample["trial"],
                "decode_passed": True,
                "first_frame_rgb_mae_255": mae,
            }
        )
    return quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("test-artifacts/performance"))
    parser.add_argument("--input", type=Path, help="Optional video to benchmark; never modified")
    parser.add_argument("--start-ms", type=int, default=10250)
    parser.add_argument("--end-ms", type=int, default=20750)
    args = parser.parse_args()
    folder = args.output_dir.resolve() / str(uuid4())
    folder.mkdir(parents=True)
    report = {"platform": platform.platform(), "library": measure_library(folder)}
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if args.input:
        report["video"] = measure_video(args.input, folder, args.start_ms, args.end_ms)
    path = folder / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {path}")


if __name__ == "__main__":
    main()
