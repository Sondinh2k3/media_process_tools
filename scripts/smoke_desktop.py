"""Sinh dữ liệu tổng hợp, chạy thử desktop và ghi ảnh/báo cáo; không dùng video thật."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from video_dataset_tool.core.paths import find_binary, subprocess_options
from video_dataset_tool.ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("test-artifacts/desktop"))
    parser.add_argument("--offscreen", action="store_true")
    args = parser.parse_args()
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    folder = args.output_dir.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "đường phố tổng hợp.mp4"
    if not source.exists():
        subprocess.run(
            [
                find_binary("ffmpeg"),
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=25:duration=8",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=8",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-g",
                "50",
                "-c:a",
                "aac",
                "-shortest",
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=45,
            **subprocess_options(),
        )
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    app = QApplication([])
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI" if os.name == "nt" else "Sans Serif", 10))
    window = MainWindow(folder / "app_data")
    window.resize(1500, 1000)
    window.show()
    window.output_root = folder / "clips"
    window.update_output_label()
    frames = []
    window.viewer.video.videoSink().videoFrameChanged.connect(
        lambda frame: frames.append(frame.isValid())
    )
    decoded_image = [None]

    def save_frame(frame):
        if frame.isValid():
            decoded_image[0] = frame.toImage()

    window.viewer.video.videoSink().videoFrameChanged.connect(save_frame)

    def wait_for(predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        raise RuntimeError("Desktop smoke test timed out")

    window.add_paths([source])
    wait_for(lambda: window.current_metadata is not None and not window.tasks)
    wait_for(lambda: any(frames))
    for mode in ("fast", "precise"):
        window.editor.start.setText("00:00:01.200")
        window.editor.end.setText("00:00:04.000")
        window.editor.notes.setPlainText(
            "Video tổng hợp để kiểm thử. Có dấu tiếng Việt; không phải dữ liệu thực tế."
        )
        window.editor.object_type.setText("Mẫu kiểm thử")
        window.editor.mode.setCurrentIndex(window.editor.mode.findData(mode))
        count = len(window.export_results)
        window.start_export()
        wait_for(lambda: window.export_worker is None and len(window.export_results) > count)
        assert window.export_results[-1].status == "completed"
    window.viewer.player.pause()
    window.viewer.seek(2200)
    wait_for(lambda: abs(window.viewer.player.position() - 2200) < 100)
    window.repository.export_csv(folder / "clip_inventory.csv")
    # Give Qt a complete paint pass before grabbing the desktop widget tree.
    for _ in range(10):
        app.processEvents()
        time.sleep(0.03)
    window.grab().save(str(folder / "desktop.png"))
    if not args.offscreen:
        window.screen().grabWindow(window.winId()).save(str(folder / "desktop-screen.png"))
    if decoded_image[0] is not None:
        decoded_image[0].save(str(folder / "decoded-frame.png"))
    assert original == hashlib.sha256(source.read_bytes()).hexdigest()
    report = {
        "source_sha256_unchanged": True,
        "decoded_video_frame": any(frames),
        "player_position_ms": window.viewer.player.position(),
        "clips": window.repository.clips(),
        "screenshot": str(folder / "desktop.png"),
    }
    (folder / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    window.close()
    app.processEvents()
    print("Desktop smoke: PASS")


if __name__ == "__main__":
    main()
