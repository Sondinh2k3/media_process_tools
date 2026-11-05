import pytest
from PySide6.QtCore import QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from video_dataset_tool.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def drain_windows_before_qt_teardown(qtbot):
    yield
    for window in QApplication.topLevelWidgets():
        if isinstance(window, MainWindow) and not window.closed:
            window.cancel_export()
            qtbot.waitUntil(
                lambda: window.export_worker is None and not window.tasks, timeout=50000
            )
            window.close()


def test_open_play_pause_seek_and_bad_file(qtbot, synthetic_video, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.add_paths([synthetic_video])
    qtbot.waitUntil(lambda: window.current_metadata is not None, timeout=15000)
    assert window.sources.count() == 1
    qtbot.waitUntil(lambda: window.viewer.player.position() > 0, timeout=15000)
    window.viewer.player.pause()
    assert window.viewer.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    window.viewer.seek(3000)
    qtbot.waitUntil(lambda: abs(window.viewer.player.position() - 3000) < 300, timeout=5000)
    assert "00:00:03." in window.viewer.clock.text()
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"bad")
    window.add_paths([bad])
    qtbot.waitUntil(lambda: not window.tasks, timeout=15000)
    assert window.current_metadata is None
    assert "không đọc được" in window.metadata_label.text().lower()
    window.close()


def test_cached_source_switch_forced_refresh_and_unchanged_autosave(
    qtbot, synthetic_video, monkeypatch
):
    from video_dataset_tool.ui import main_window

    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.editor.export_button.isEnabled()
    window.add_paths([synthetic_video])
    qtbot.waitUntil(lambda: window.current_metadata is not None and not window.tasks, timeout=15000)
    window.viewer.player.pause()
    window.viewer.pending_seek = None
    window.save_draft()
    changes = window.repository.connection.total_changes
    for _ in range(10):
        window.save_draft()
    assert window.repository.connection.total_changes == changes
    original = main_window.probe_video
    calls = []

    def probe(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(main_window, "probe_video", probe)
    window.source_selected(window.sources.currentItem())
    assert window.current_metadata is not None and not calls
    assert window.editor.export_button.isEnabled()
    window.refresh_library()
    assert not window.editor.export_button.isEnabled()
    qtbot.waitUntil(lambda: window.current_metadata is not None and not window.tasks, timeout=15000)
    assert len(calls) == 1
    window.close()


def test_editor_export_worker_and_draft(qtbot, synthetic_video, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.add_paths([synthetic_video])
    qtbot.waitUntil(lambda: window.current_metadata is not None, timeout=15000)
    window.editor.start.setText("00:00:01.200")
    window.editor.end.setText("00:00:03.600")
    window.editor.notes.setPlainText("Hàng hóa cần xem xét")
    window.output_root = tmp_path / "clips"
    ticks = []
    timer = QTimer(window)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)
    window.start_export()
    worker = window.export_worker
    window.start_export()
    assert window.export_worker is worker
    assert not window.editor.export_button.isEnabled()
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=20000)
    timer.stop()
    assert ticks
    assert window.export_results[-1].status == "completed"
    assert window.repository.clips()[0]["status"] == "completed"
    assert window.repository.clips()[0]["source_video_id"] == window.current_source_id
    assert window.drafts[window.current_path]["notes"] == "Hàng hóa cần xem xét"
    window.close()


def test_cancel_button_waits_for_worker_cleanup(qtbot, synthetic_video, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.add_paths([synthetic_video])
    qtbot.waitUntil(lambda: window.current_metadata is not None and not window.tasks, timeout=15000)
    window.output_root = tmp_path / "cancelled-clips"
    window.start_export()
    assert window.editor.cancel_button.isEnabled()
    window.cancel_export()
    assert not window.editor.cancel_button.isEnabled()
    assert window.editor.cancel_button.text() == "Đang hủy…"
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=20000)
    assert window.export_results[-1].status == "cancelled"
    assert window.repository.clips()[0]["status"] == "cancelled"
    assert window.editor.export_button.isEnabled()
    assert not window.export_timer.isActive()
    assert not list(window.output_root.rglob("*.partial*"))
    window.close()


def test_reopen_restores_library_draft_output_and_clips(qtbot, synthetic_video, tmp_path):
    from pathlib import Path

    data = tmp_path / "dataset"
    window = MainWindow(data)
    qtbot.addWidget(window)
    window.add_paths([synthetic_video])
    qtbot.waitUntil(lambda: window.current_metadata is not None, timeout=15000)
    window.editor.start.setText("00:00:01.000")
    window.editor.end.setText("00:00:02.000")
    window.editor.notes.setPlainText("Bản nháp tiếng Việt")
    window.editor.event_start.setText("00:00:01.200")
    window.editor.event_end.setText("00:00:01.800")
    window.editor.before.setValue(0.5)
    window.output_root = tmp_path / "đầu ra"
    window.start_export()
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=20000)
    qtbot.waitUntil(lambda: not window.tasks, timeout=15000)
    source_id = window.current_source_id
    window.close()
    reopened = MainWindow(data)
    qtbot.addWidget(reopened)
    qtbot.waitUntil(lambda: reopened.current_metadata is not None, timeout=15000)
    assert reopened.sources.count() == 1
    assert reopened.output_root == tmp_path / "đầu ra"
    assert reopened.editor.notes.toPlainText() == "Bản nháp tiếng Việt"
    assert reopened.editor.start.text() == "00:00:01.000"
    assert reopened.editor.event_start.text() == "00:00:01.200"
    rows = reopened.repository.clips()
    assert rows[0]["source_video_id"] == source_id
    assert rows[0]["requested_in_ms"] == 500
    assert rows[0]["event_start_ms"] == 1200
    assert Path(rows[0]["output_path"]).is_file()
    assert reopened.clip_table.table.model().rowCount() == 1
    reopened.clip_table.category_filter.setCurrentIndex(
        reopened.clip_table.category_filter.findData("normal")
    )
    assert reopened.clip_table.table.model().rowCount() == 0
    qtbot.waitUntil(lambda: not reopened.tasks, timeout=15000)
    reopened.close()


def test_rapid_switch_preview_shortcuts_and_video_frame(qtbot, synthetic_video, tmp_path):
    import shutil

    from video_dataset_tool.core.paths import canonical_path

    other = tmp_path / "video thứ hai.mp4"
    shutil.copyfile(synthetic_video, other)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    frames = []
    window.viewer.video.videoSink().videoFrameChanged.connect(
        lambda frame: frames.append(frame.isValid())
    )
    window.add_paths([synthetic_video, other])
    for _ in range(12):
        window.sources.setCurrentRow(1)
        window.sources.setCurrentRow(0)
    window.sources.setCurrentRow(1)
    assert len(window.tasks) <= 1
    qtbot.waitUntil(
        lambda: window.current_path == canonical_path(other) and not window.tasks, timeout=20000
    )
    qtbot.waitUntil(lambda: any(frames), timeout=15000)
    window.viewer.player.pause()
    window.viewer.seek(1000)
    window.editor.start.setText("00:00:01.000")
    window.editor.end.setText("00:00:01.500")
    window.preview_selection()
    qtbot.waitUntil(
        lambda: window.viewer.player.playbackState() == QMediaPlayer.PlaybackState.PausedState,
        timeout=5000,
    )
    assert 1500 <= window.viewer.player.position() < 2000
    initial = window.editor.start.text()
    window.editor.notes.setFocus()
    qtbot.keyClicks(window.editor.notes, "I O ")
    assert window.editor.notes.toPlainText() == "I O "
    assert window.editor.start.text() == initial
    window.editor.notes.setPlainText("Ghi chú cho video thứ hai")
    window.sources.setCurrentRow(0)
    qtbot.waitUntil(
        lambda: window.current_path == canonical_path(synthetic_video) and not window.tasks,
        timeout=15000,
    )
    window.sources.setCurrentRow(1)
    qtbot.waitUntil(
        lambda: window.current_path == canonical_path(other) and not window.tasks, timeout=15000
    )
    assert window.editor.notes.toPlainText() == "Ghi chú cho video thứ hai"
    window.viewer.handle_error(QMediaPlayer.Error.FormatError, "unsupported codec")
    assert "codec" in window.viewer.error_label.text()
    window.close()


def test_failed_export_record_and_session_lock(qtbot, synthetic_video, tmp_path, monkeypatch):
    data = tmp_path / "session"
    window = MainWindow(data)
    qtbot.addWidget(window)
    with pytest.raises(ValueError, match="cửa sổ khác"):
        MainWindow(data)
    window.add_paths([synthetic_video])
    qtbot.waitUntil(lambda: window.current_metadata is not None and not window.tasks, timeout=15000)
    invalid = tmp_path / "file_thay_vi_thu_muc"
    invalid.write_text("keep", encoding="utf-8")
    window.output_root = invalid
    monkeypatch.setattr(window, "show_error", lambda message: None)
    window.start_export()
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=20000)
    assert window.repository.clips()[0]["status"] == "failed"
    assert window.repository.clips()[0]["error_message"]
    assert invalid.read_text() == "keep"
    window.close()


def test_disappearing_source_keeps_failed_history(qtbot, synthetic_video, tmp_path, monkeypatch):
    import shutil

    source = tmp_path / "sắp bị mất.mp4"
    shutil.copyfile(synthetic_video, source)
    window = MainWindow()
    qtbot.addWidget(window)
    window.add_paths([source])
    qtbot.waitUntil(lambda: window.current_metadata is not None and not window.tasks, timeout=15000)
    window.viewer.clear_source()

    def remove_after_backend_release():
        try:
            source.unlink()
            return True
        except PermissionError:
            return False

    qtbot.waitUntil(remove_after_backend_release, timeout=10000)
    window.output_root = tmp_path / "clips"
    monkeypatch.setattr(window, "show_error", lambda message: None)
    window.start_export()
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=20000)
    assert window.repository.clips()[0]["status"] == "failed"
    window.repository.refresh_availability()
    assert window.repository.sources()[0]["availability"] == "missing"
    assert len(window.repository.clips()) == 1
    window.close()


def test_gui_keeps_original_video_id_case(qtbot, synthetic_video, tmp_path):
    import shutil
    from pathlib import Path

    source = tmp_path / "Video_Camera_ABC_1234_MixedCase.mp4"
    shutil.copyfile(synthetic_video, source)
    window = MainWindow()
    qtbot.addWidget(window)
    window.add_paths([source])
    qtbot.waitUntil(lambda: window.current_metadata is not None and not window.tasks, timeout=15000)
    window.output_root = tmp_path / "clips"
    window.editor.start.setText("00:00:01.200")
    window.editor.end.setText("00:00:03.600")
    window.start_export()
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=20000)
    result = window.export_results[-1]
    assert result.status == "completed"
    assert Path(result.output_path).name.startswith(source.stem + "__00-00-01.200_00-00-03.600__")
    window.close()
