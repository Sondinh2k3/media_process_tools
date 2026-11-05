import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QLockFile, Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.models import VIDEO_EXTENSIONS, ClipRequest
from ..core.paths import app_data_dir, canonical_path, find_binary
from ..core.timecode import format_timecode, parse_timecode
from ..core.validators import validate_request
from ..services.video_probe import probe_video
from ..storage.database import Database
from ..storage.repositories import Repository
from ..workers.export_worker import ExportWorker
from ..workers.task import Task
from .clip_editor import ClipEditor
from .clip_table import ClipTable
from .video_player import VideoPlayer


class MainWindow(QMainWindow):
    def __init__(self, data_dir=None):
        super().__init__()
        self.data_dir = Path(data_dir or app_data_dir()).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session_lock = QLockFile(str(self.data_dir / "session.lock"))
        self.session_lock.setStaleLockTime(0)
        if not self.session_lock.tryLock(0):
            raise ValueError(
                "Dataset đang được mở trong cửa sổ khác. Đóng cửa sổ đó hoặc chọn --data-dir khác."
            )
        self.database = Database(self.data_dir / "dataset.sqlite3")
        self.repository = Repository(self.database)
        self.repository.recover_interrupted()
        self.repository.refresh_availability()
        self.source_records = {}
        self.current_source_id = None
        self.loading_editor = False
        self.closed = False
        self.setWindowTitle("Video Dataset Tool · V1")
        self.resize(1400, 900)
        self.tasks = set()
        self.current_path = None
        self.current_metadata = None
        self.load_generation = 0
        self.pending_probe = None
        self.drafts = {}
        saved_output = self.repository.get_setting("output_root_dir")
        self.output_root = Path(saved_output) if saved_output else None
        self.export_worker = None
        self.export_results = []
        root = QWidget()
        self.setCentralWidget(root)
        self.layout = QVBoxLayout(root)
        bar = QHBoxLayout()
        for label, callback in (("Mở file", self.open_file), ("Mở thư mục", self.open_folder)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            bar.addWidget(button)
        bar.addStretch()
        self.layout.addLayout(bar)
        self.toolbar = bar
        output_button = QPushButton("Thư mục xuất")
        output_button.clicked.connect(self.choose_output)
        self.toolbar.insertWidget(2, output_button)
        settings_button = QPushButton("Thiết lập")
        settings_button.clicked.connect(self.show_settings)
        self.toolbar.insertWidget(3, settings_button)
        refresh_button = QPushButton("Kiểm tra nguồn")
        refresh_button.clicked.connect(self.refresh_library)
        self.toolbar.insertWidget(4, refresh_button)
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        self.update_output_label()
        self.layout.addWidget(self.output_label)
        self.splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("DANH SÁCH VIDEO"))
        self.sources = QListWidget()
        self.sources.setMinimumWidth(180)
        left_layout.addWidget(self.sources)
        self.metadata_label = QLabel("Mở video để bắt đầu.")
        self.metadata_label.setWordWrap(True)
        left_layout.addWidget(self.metadata_label)
        self.splitter.addWidget(left)
        self.viewer = VideoPlayer()
        self.splitter.addWidget(self.viewer)
        self.editor = ClipEditor()
        self.editor.setMinimumWidth(350)
        self.splitter.addWidget(self.editor)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([210, 720, 360])
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.addWidget(self.splitter)
        self.clip_table = ClipTable(self.repository)
        self.clip_table.error.connect(self.show_error)
        self.clip_table.csv_requested.connect(self.export_csv)
        self.vertical_splitter.addWidget(self.clip_table)
        self.vertical_splitter.setSizes([650, 230])
        self.layout.addWidget(self.vertical_splitter, 1)
        self.sources.currentItemChanged.connect(self.source_selected)
        self.editor.mark_requested.connect(self.mark)
        self.editor.marks_changed.connect(self.viewer.timeline.set_marks)
        self.editor.export_requested.connect(self.start_export)
        self.editor.preview_requested.connect(self.preview_selection)
        self.editor.cancel_requested.connect(self.cancel_export)
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(350)
        self.draft_timer.timeout.connect(self.autosave)
        self.editor.changed.connect(self.schedule_autosave)
        self.session_timer = QTimer(self)
        self.session_timer.setInterval(2000)
        self.session_timer.timeout.connect(self.autosave)
        self.session_timer.start()
        QApplication.instance().installEventFilter(self)
        missing = [name for name in ("ffmpeg", "ffprobe") if not find_binary(name)]
        if missing:
            warning = QLabel(
                "Thiếu "
                + ", ".join(missing)
                + ". Cài FFmpeg/FFprobe, thêm bin vào PATH rồi mở lại. Xem README.md."
            )
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #b42318; padding: 8px; background: #fff1e8")
            self.layout.insertWidget(0, warning)
        self.statusBar().showMessage("Sẵn sàng · Video gốc luôn được giữ nguyên")
        self.restore_session()

    def show_error(self, message):
        QMessageBox.warning(self, "Không thể thực hiện", message)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn video",
            self.repository.get_setting("last_source_dir", ""),
            "Video (*.mp4 *.mov *.mkv *.avi *.m4v *.webm *.mts *.m2ts *.ts);;Tất cả (*)",
        )
        if path:
            self.repository.set_setting("last_source_dir", str(Path(path).parent))
            self.add_paths([Path(path)])

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục video", self.repository.get_setting("last_source_dir", "")
        )
        if folder:
            try:
                self.repository.set_setting("last_source_dir", folder)
                self.add_paths(
                    sorted(
                        p
                        for p in Path(folder).iterdir()
                        if p.suffix.lower() in VIDEO_EXTENSIONS and p.is_file()
                    )
                )
            except OSError:
                self.show_error("Không đọc được thư mục. Kiểm tra quyền truy cập.")

    def add_paths(self, paths):
        first = None
        existing = {
            self.sources.item(i).data(Qt.ItemDataRole.UserRole): self.sources.item(i)
            for i in range(self.sources.count())
        }
        for path in paths:
            key = canonical_path(path)
            self.source_records[key] = self.repository.ensure_source(path)
            if key not in existing:
                item = QListWidgetItem(path.name)
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setToolTip(str(path))
                self.sources.addItem(item)
                existing[key] = item
            first = first or existing[key]
        if first:
            if self.sources.currentItem() is first:
                self.source_selected(first)
            else:
                self.sources.setCurrentItem(first)
        else:
            self.statusBar().showMessage("Thư mục không có video được hỗ trợ.")
        self.clip_table.refresh_sources()

    def source_selected(self, item, previous=None):
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        self.save_draft()
        self.load_generation += 1
        generation = self.load_generation
        self.current_path = None
        self.current_metadata = None
        self.current_source_id = None
        self.viewer.clear_source()
        self.viewer.setEnabled(False)
        self.metadata_label.setText("Đang đọc thông số…")
        if self.tasks:
            self.pending_probe = (path, generation)
            return
        self.start_probe(path, generation)

    def start_probe(self, path, generation):
        task = Task(lambda: probe_video(path), self)
        task.context = (path, generation)
        self.tasks.add(task)
        task.succeeded.connect(self.probe_succeeded, Qt.ConnectionType.QueuedConnection)
        task.failed.connect(self.probe_failed, Qt.ConnectionType.QueuedConnection)
        task.finished.connect(self.probe_finished, Qt.ConnectionType.QueuedConnection)
        task.finished.connect(task.deleteLater)
        task.start()

    @Slot(object)
    def probe_succeeded(self, metadata):
        path, generation = self.sender().context
        self.source_loaded(path, metadata, generation)

    @Slot(str)
    def probe_failed(self, message):
        path, generation = self.sender().context
        self.source_failed(message, generation)

    @Slot()
    def probe_finished(self):
        task = self.sender()
        self.tasks.discard(task)
        if self.pending_probe:
            path, generation = self.pending_probe
            self.pending_probe = None
            self.start_probe(path, generation)

    def source_loaded(self, path, metadata, generation):
        if generation != self.load_generation:
            return
        try:
            source = self.repository.ensure_source(path)
            self.repository.update_source(source["id"], metadata)
            self.source_records[path] = self.repository.ensure_source(path)
        except (OSError, sqlite3.Error):
            logging.exception("Could not save source metadata")
            self.source_failed(
                "Không lưu được thông số nguồn. Kiểm tra file và thư mục dữ liệu.", generation
            )
            return
        self.current_path, self.current_metadata = path, metadata
        self.current_source_id = source["id"]
        defaults = {
            "mode": self.repository.get_setting("default_cut_mode", "fast"),
            "before": self.repository.get_setting("default_padding_before_s", 0),
            "after": self.repository.get_setting("default_padding_after_s", 0),
        }
        draft = self.repository.load_draft(source["id"]) or defaults
        self.loading_editor = True
        self.editor.load_draft(draft, metadata.duration_ms)
        self.loading_editor = False
        self.metadata_label.setText(
            f"{Path(path).name}\n{format_timecode(metadata.duration_ms)}\n{metadata.width} × {metadata.height} · {metadata.fps:.3f} FPS\n{metadata.video_codec} / {metadata.audio_codec or 'không âm thanh'}"
        )
        self.viewer.open(path, metadata, min(metadata.duration_ms, draft.get("_position_ms", 0)))
        self.viewer.setEnabled(True)
        self.repository.set_setting("last_opened_video_id", source["id"])
        self.update_source_labels()

    def source_failed(self, message, generation):
        if generation == self.load_generation:
            self.metadata_label.setText(message)
            self.statusBar().showMessage(message)
            self.repository.refresh_availability()
            self.source_records = {row["source_path"]: row for row in self.repository.sources()}
            self.update_source_labels()
            self.clip_table.refresh()

    def closeEvent(self, event):
        if self.closed:
            event.accept()
            return
        if self.export_worker is not None:
            self.statusBar().showMessage("Hãy hủy hoặc chờ tác vụ xuất hoàn tất trước khi đóng.")
            event.ignore()
            return
        if self.tasks:
            self.statusBar().showMessage("Đang đọc video, vui lòng chờ hoàn tất rồi đóng cửa sổ.")
            event.ignore()
            return
        try:
            self.save_draft()
            self.repository.set_setting(
                "output_root_dir", str(self.output_root) if self.output_root else None
            )
            self.repository.set_setting(
                "window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii")
            )
            self.repository.set_setting("splitter_sizes", self.splitter.sizes())
            self.repository.set_setting("vertical_splitter_sizes", self.vertical_splitter.sizes())
        except (OSError, sqlite3.Error):
            logging.exception("Could not save session at shutdown")
            self.show_error(
                "Không lưu được phiên làm việc. Kiểm tra quyền ghi và dung lượng rồi thử đóng lại."
            )
            event.ignore()
            return
        self.session_timer.stop()
        self.draft_timer.stop()
        self.viewer.shutdown()
        QApplication.instance().removeEventFilter(self)
        self.database.close()
        self.session_lock.unlock()
        self.closed = True
        event.accept()

    def save_draft(self):
        if (
            self.current_path
            and self.current_source_id
            and not self.loading_editor
            and not self.closed
        ):
            draft = self.editor.draft()
            draft["_position_ms"] = (
                self.viewer.pending_seek
                if self.viewer.pending_seek is not None
                else self.viewer.player.position()
            )
            self.drafts[self.current_path] = draft
            self.repository.save_draft(self.current_source_id, draft)

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục xuất clip", str(self.output_root or "")
        )
        if folder:
            self.output_root = Path(folder)
            self.repository.set_setting("output_root_dir", str(self.output_root))
            self.update_output_label()
            self.statusBar().showMessage(f"Thư mục xuất: {folder}")

    def mark(self, key):
        if self.current_metadata:
            field = self.editor.start if key == "in" else self.editor.end
            field.setText(format_timecode(max(0, self.viewer.player.position())))

    def preview_selection(self):
        try:
            if not self.current_path:
                raise ValueError("Hãy mở một video hợp lệ trước.")
            self.viewer.preview(*self.editor.range())
        except ValueError as exc:
            self.show_error(str(exc))

    def make_request(self):
        if not self.current_path or not self.current_metadata:
            raise ValueError("Hãy mở một video hợp lệ trước khi xuất.")
        start, end = self.editor.range()
        values = self.editor.draft()
        from uuid import uuid4

        source = self.source_records[self.current_path]
        request = ClipRequest(
            str(uuid4()),
            self.current_source_id,
            self.current_path,
            self.current_metadata,
            start,
            end,
            values["category"],
            cut_mode=values["mode"],
            notes=values["notes"],
            object_type=values["object_type"],
            review_status=values["review"],
            event_start_ms=parse_timecode(values["event_start"])
            if values["event_start"].strip()
            else None,
            event_end_ms=parse_timecode(values["event_end"])
            if values["event_end"].strip()
            else None,
            source_size=source["file_size_bytes"],
            source_mtime_ns=source["mtime_ns"],
        )
        validate_request(request)
        return request

    def start_export(self):
        if self.export_worker is not None:
            return
        try:
            request = self.make_request()
            if self.output_root is None:
                self.choose_output()
            if self.output_root is None:
                return
            self.save_draft()
            self.repository.set_setting("output_root_dir", str(self.output_root))
            self.repository.create_clip(request, self.output_root)
            self.export_worker = ExportWorker(
                request, self.output_root, self, database_path=self.database.path
            )
            self.clip_table.refresh()
            self.editor.set_busy(True)
            self.export_worker.progress.connect(self.editor.progress.setValue)
            self.export_worker.processing.connect(self.clip_table.refresh)
            self.export_worker.result_ready.connect(
                self.export_finished, Qt.ConnectionType.QueuedConnection
            )
            self.export_worker.finished.connect(
                self.export_thread_finished, Qt.ConnectionType.QueuedConnection
            )
            self.statusBar().showMessage("Đang xuất clip… Video gốc được giữ nguyên.")
            self.export_worker.start()
        except sqlite3.Error:
            logging.exception("Could not create export record")
            self.show_error(
                "Không lưu được tác vụ vào database. Kiểm tra dung lượng và quyền ghi thư mục dữ liệu."
            )
        except (ValueError, OSError) as exc:
            self.show_error(str(exc))

    @Slot(object)
    def export_finished(self, result):
        self.export_results.append(result)
        self.clip_table.refresh()
        self.statusBar().showMessage(
            "Xuất clip thành công: " + result.output_path
            if result.status == "completed"
            else result.error_message
        )
        if result.status == "failed":
            self.show_error(result.error_message)

    @Slot()
    def export_thread_finished(self):
        self.export_worker.deleteLater()
        self.export_worker = None
        self.editor.set_busy(False)

    def cancel_export(self):
        if self.export_worker:
            self.export_worker.cancel()
            self.statusBar().showMessage("Đang hủy và dọn file tạm…")

    def update_output_label(self):
        self.output_label.setText(f"Xuất clip: {self.output_root or 'chưa chọn thư mục'}")
        self.output_label.setToolTip(str(self.data_dir))

    def schedule_autosave(self):
        if not self.loading_editor and not self.closed:
            self.draft_timer.start()

    def autosave(self):
        try:
            self.save_draft()
        except (OSError, sqlite3.Error):
            logging.exception("Could not autosave draft")
            self.statusBar().showMessage(
                "Chưa lưu được bản nháp. Kiểm tra dung lượng và quyền ghi thư mục dữ liệu."
            )

    def restore_session(self):
        geometry = self.repository.get_setting("window_geometry")
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        for setting, splitter in (
            ("splitter_sizes", self.splitter),
            ("vertical_splitter_sizes", self.vertical_splitter),
        ):
            sizes = self.repository.get_setting(setting)
            if sizes:
                splitter.setSizes(sizes)
        selected = self.repository.get_setting("last_opened_video_id")
        self.sources.blockSignals(True)
        item_to_select = None
        for source in self.repository.sources():
            path = source["source_path"]
            self.source_records[path] = source
            item = QListWidgetItem(source["display_name"])
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.sources.addItem(item)
            if source["id"] == selected:
                item_to_select = item
        self.sources.setCurrentRow(-1)
        self.sources.blockSignals(False)
        self.update_source_labels()
        if item_to_select:
            self.sources.setCurrentItem(item_to_select)

    def update_source_labels(self):
        states = {
            "missing": " · mất nguồn",
            "changed": " · đã thay đổi",
            "unreadable": " · không đọc được",
        }
        for index in range(self.sources.count()):
            item = self.sources.item(index)
            source = self.source_records[item.data(Qt.ItemDataRole.UserRole)]
            item.setText(source["display_name"] + states.get(source["availability"], ""))

    def refresh_library(self):
        self.repository.refresh_availability()
        self.source_records = {row["source_path"]: row for row in self.repository.sources()}
        self.update_source_labels()
        self.clip_table.refresh_sources()
        item = self.sources.currentItem()
        if item:
            self.source_selected(item)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất toàn bộ lịch sử CSV",
            str(self.output_root or Path.home()) + "/clip_inventory.csv",
            "CSV (*.csv)",
        )
        if path:
            target = Path(path)
            if target.suffix.lower() != ".csv":
                target = target.with_name(target.name + ".csv")
            try:
                self.repository.export_csv(target)
                self.statusBar().showMessage(f"Đã xuất CSV UTF-8-SIG: {target}")
            except (OSError, ValueError, sqlite3.Error):
                logging.exception("Could not export CSV")
                self.show_error(
                    "Không ghi được CSV. Chọn tên file khác trong thư mục có quyền ghi; không chọn video nguồn, clip hoặc database."
                )

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Thiết lập")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        mode = QComboBox()
        mode.addItem("Fast · sao chép luồng", "fast")
        mode.addItem("Precise · mã hóa lại", "precise")
        mode.setCurrentIndex(
            max(0, mode.findData(self.repository.get_setting("default_cut_mode", "fast")))
        )
        form.addRow("Chế độ cho video mới", mode)
        padding_fields = []
        for key, label in (
            ("default_padding_before_s", "Đệm trước mặc định"),
            ("default_padding_after_s", "Đệm sau mặc định"),
        ):
            field = QDoubleSpinBox()
            field.setRange(0, 3600)
            field.setDecimals(3)
            field.setSuffix(" giây")
            field.setValue(self.repository.get_setting(key, 0))
            form.addRow(label, field)
            padding_fields.append((key, field))
        layout.addLayout(form)
        info = QLabel(
            f"Dữ liệu và log cục bộ:\n{self.data_dir}\n\nDùng --data-dir để chọn dataset riêng khi khởi động.\nBản nháp hiện có được ưu tiên hơn thiết lập mặc định."
        )
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(info)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.set_setting("default_cut_mode", mode.currentData())
            for key, field in padding_fields:
                self.repository.set_setting(key, field.value())
            self.statusBar().showMessage("Đã lưu thiết lập cho video chưa có bản nháp.")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and self.isActiveWindow():
            key, modifiers = event.key(), event.modifiers()
            control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
            shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            if control and key == Qt.Key.Key_O:
                self.open_folder() if shift else self.open_file()
                return True
            if control and key == Qt.Key.Key_E:
                self.start_export()
                return True
            focus = QApplication.focusWidget()
            editing = isinstance(
                focus, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QComboBox)
            )
            if not editing and not control:
                if key == Qt.Key.Key_Space:
                    self.viewer.toggle()
                elif key in (Qt.Key.Key_I, Qt.Key.Key_O):
                    self.mark("in" if key == Qt.Key.Key_I else "out")
                elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                    self.viewer.seek_relative(
                        (5000 if shift else 1000) * (-1 if key == Qt.Key.Key_Left else 1)
                    )
                else:
                    return super().eventFilter(watched, event)
                return True
        return super().eventFilter(watched, event)
