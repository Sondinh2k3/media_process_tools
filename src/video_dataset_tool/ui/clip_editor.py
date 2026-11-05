from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import CATEGORIES
from ..core.timecode import format_timecode, parse_timecode
from ..core.validators import validate_range


class ClipEditor(QWidget):
    marks_changed = Signal(int, int)
    changed = Signal()
    export_requested = Signal()
    preview_requested = Signal()
    cancel_requested = Signal()
    mark_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.duration_ms = 0
        self.source_ready = False
        self.busy = False
        self.range_valid = False
        self.setMinimumWidth(290)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        layout.addWidget(QLabel("THÔNG TIN CLIP"))
        form = QFormLayout()
        self.start = QLineEdit("00:00:00.000")
        self.end = QLineEdit("00:00:00.000")
        self.start.setObjectName("in_time")
        self.end.setObjectName("out_time")
        for label, field, key in (("IN", self.start, "in"), ("OUT", self.end, "out")):
            row = QHBoxLayout()
            row.addWidget(field)
            button = QPushButton("Đặt " + label)
            button.clicked.connect(lambda checked=False, k=key: self.mark_requested.emit(k))
            row.addWidget(button)
            form.addRow(label, row)
            field.textChanged.connect(self.update_summary)
        self.before = QDoubleSpinBox()
        self.after = QDoubleSpinBox()
        for title, field in (("Đệm trước", self.before), ("Đệm sau", self.after)):
            field.setRange(0, 3600)
            field.setDecimals(3)
            field.setSuffix(" giây")
            field.setToolTip("Mặc định 0; có thể dùng 3–5 giây. Tự giới hạn tại đầu/cuối video.")
            field.valueChanged.connect(self.update_summary)
            form.addRow(title, field)
        self.event_start = QLineEdit()
        self.event_end = QLineEdit()
        for label, field in (
            ("Sự kiện bắt đầu", self.event_start),
            ("Sự kiện kết thúc", self.event_end),
        ):
            field.setPlaceholderText("HH:MM:SS.mmm · tùy chọn")
            form.addRow(label, field)
        self.category = QComboBox()
        for code, label in CATEGORIES.items():
            self.category.addItem(label, code)
        form.addRow("Nhóm tình huống", self.category)
        self.object_type = QLineEdit()
        self.object_type.setPlaceholderText("Ví dụ: hàng hóa, xe đẩy…")
        form.addRow("Loại vật (tùy chọn)", self.object_type)
        self.review = QComboBox()
        self.review.addItem("Chưa xem xét", "unreviewed")
        self.review.addItem("Đã xem xét", "reviewed")
        form.addRow("Xem xét", self.review)
        self.mode = QComboBox()
        self.mode.addItem("Fast · sao chép luồng", "fast")
        self.mode.addItem("Precise · mã hóa lại", "precise")
        form.addRow("Chế độ cắt", self.mode)
        self.preset = QComboBox()
        self.preset.addItem("Veryfast · ưu tiên tốc độ", "veryfast")
        self.preset.addItem("Fast · cân bằng", "fast")
        self.preset.addItem("Medium · cấu hình cũ", "medium")
        self.preset.setToolTip(
            "Chỉ dùng cho Precise. Giữ CRF 18; tốc độ, độ nén và chất lượng có thể khác giữa các preset."
        )
        self.preset.setEnabled(False)
        self.mode.currentIndexChanged.connect(
            lambda: self.preset.setEnabled(self.mode.currentData() == "precise")
        )
        form.addRow("Tốc độ mã hóa", self.preset)
        layout.addLayout(form)
        self.precision_note = QLabel(
            "Fast có thể lệch theo keyframe. Precise mã hóa lại, hướng tới frame gần yêu cầu; không bảo đảm tuyệt đối."
        )
        self.precision_note.setWordWrap(True)
        layout.addWidget(self.precision_note)
        note_label = QLabel("Ghi chú · positive là nghi vấn, chưa kết luận vi phạm")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(110)
        layout.addWidget(self.notes)
        layout.addStretch()
        layout = outer
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.preview_button = QPushButton("Xem trước khoảng xuất")
        self.preview_button.clicked.connect(self.preview_requested)
        layout.addWidget(self.preview_button)
        self.export_button = QPushButton("Xuất clip · Ctrl+E")
        self.export_button.setStyleSheet(
            "background: #176b55; color: white; padding: 9px; font-weight: bold"
        )
        self.export_button.clicked.connect(self.export_requested)
        layout.addWidget(self.export_button)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.cancel_button = QPushButton("Hủy tác vụ xuất")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_requested)
        layout.addWidget(self.cancel_button)
        for field in (self.event_start, self.event_end, self.object_type):
            field.textChanged.connect(self.changed)
        self.notes.textChanged.connect(self.changed)
        for field in (self.category, self.review, self.mode, self.preset):
            field.currentIndexChanged.connect(self.changed)
        self.update_summary()

    def range(self):
        return validate_range(
            parse_timecode(self.start.text()),
            parse_timecode(self.end.text()),
            self.duration_ms,
            self.before.value(),
            self.after.value(),
        )

    def update_summary(self):
        try:
            start, end = self.range()
            self.summary.setText(
                f"Xuất: {format_timecode(start)} → {format_timecode(end)}\nĐộ dài dự kiến: {format_timecode(end - start)}"
            )
            self.summary.setStyleSheet("color: #176b55")
            self.range_valid = True
            self.marks_changed.emit(start, end)
        except ValueError as exc:
            self.summary.setText(str(exc))
            self.summary.setStyleSheet("color: #b42318")
            self.range_valid = False
        self.update_actions()
        self.changed.emit()

    def set_source_ready(self, ready):
        self.source_ready = ready
        self.update_actions()

    def update_actions(self):
        self.export_button.setEnabled(self.source_ready and self.range_valid and not self.busy)
        self.preview_button.setEnabled(self.source_ready and self.range_valid)

    def set_busy(self, busy):
        self.busy = busy
        self.update_actions()
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setText("Hủy tác vụ xuất")
        if busy:
            self.progress.setValue(0)

    def draft(self):
        return {
            "start": self.start.text(),
            "end": self.end.text(),
            "before": self.before.value(),
            "after": self.after.value(),
            "event_start": self.event_start.text(),
            "event_end": self.event_end.text(),
            "object_type": self.object_type.text(),
            "notes": self.notes.toPlainText(),
            "category": self.category.currentData(),
            "review": self.review.currentData(),
            "mode": self.mode.currentData(),
            "preset": self.preset.currentData(),
        }

    def load_draft(self, draft, duration_ms):
        self.duration_ms = duration_ms
        self.start.setText(draft.get("start", "00:00:00.000"))
        self.end.setText(draft.get("end", format_timecode(duration_ms)))
        self.before.setValue(draft.get("before", 0))
        self.after.setValue(draft.get("after", 0))
        for name in ("event_start", "event_end", "object_type"):
            getattr(self, name).setText(draft.get(name, ""))
        self.notes.setPlainText(draft.get("notes", ""))
        for name, default in (
            ("category", "positive"),
            ("review", "unreviewed"),
            ("mode", "fast"),
            ("preset", "veryfast"),
        ):
            combo = getattr(self, name)
            combo.setCurrentIndex(max(0, combo.findData(draft.get(name, default))))
        self.update_summary()
