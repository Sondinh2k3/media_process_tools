from pathlib import Path

from PySide6.QtCore import QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import CATEGORIES
from ..core.timecode import format_timecode

STATUS_LABELS = {
    "pending": "Chờ xử lý",
    "processing": "Đang xuất",
    "completed": "Hoàn tất",
    "failed": "Thất bại",
    "cancelled": "Đã hủy",
}


class ClipTable(QWidget):
    csv_requested = Signal()
    error = Signal(str)

    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.rows = []
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("LỊCH SỬ CLIP"))
        self.source_filter = QComboBox()
        self.category_filter = QComboBox()
        self.category_filter.addItem("Tất cả nhóm", None)
        for code, label in CATEGORIES.items():
            self.category_filter.addItem(label, code)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Tất cả trạng thái", None)
        for code, label in STATUS_LABELS.items():
            self.status_filter.addItem(label, code)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm tên nguồn, loại vật, ghi chú…")
        for widget in (self.source_filter, self.category_filter, self.status_filter, self.search):
            bar.addWidget(widget)
        layout.addLayout(bar)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Clip", "Nhóm", "Video nguồn", "IN", "OUT", "Chế độ", "Trạng thái", "Ghi chú / lỗi"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self.show_details)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, callback in (
            ("Mở thư mục chứa clip", self.open_folder),
            ("Chi tiết", self.show_details),
            ("Xuất CSV (toàn bộ lịch sử)", self.csv_requested.emit),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.count_label = QLabel()
        buttons.addWidget(self.count_label)
        buttons.addStretch()
        layout.addLayout(buttons)
        for combo in (self.source_filter, self.category_filter, self.status_filter):
            combo.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.refresh_sources()

    def refresh_sources(self):
        selected = self.source_filter.currentData()
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("Tất cả video", None)
        for source in self.repository.sources():
            self.source_filter.addItem(source["display_name"], source["id"])
        self.source_filter.setCurrentIndex(max(0, self.source_filter.findData(selected)))
        self.source_filter.blockSignals(False)
        self.refresh()

    @Slot()
    def refresh(self):
        self.rows = self.repository.clips(
            self.source_filter.currentData(),
            self.category_filter.currentData(),
            self.status_filter.currentData(),
            self.search.text(),
        )
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            name = Path(row["output_path"]).name if row["output_path"] else row["id"][:12]
            source = row["display_name"] + (
                " · mất nguồn" if row["source_availability"] == "missing" else ""
            )
            values = [
                name,
                CATEGORIES[row["category"]],
                source,
                format_timecode(row["requested_in_ms"]),
                format_timecode(row["requested_out_ms"]),
                row["cut_mode"],
                STATUS_LABELS[row["status"]],
                row["error_message"] or row["notes"] or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)
        self.count_label.setText(f"{len(self.rows)} clip")

    def selected(self):
        index = self.table.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def open_folder(self):
        row = self.selected()
        if not row or not row["output_path"]:
            self.error.emit("Chọn một clip có đường dẫn đầu ra trước.")
            return
        folder = Path(row["output_path"]).parent
        if not folder.is_dir():
            self.error.emit("Thư mục chứa clip không còn tồn tại.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.error.emit("Không mở được trình quản lý file của hệ điều hành.")

    def show_details(self, *args):
        from PySide6.QtWidgets import QMessageBox

        row = self.selected()
        if row:
            box = QMessageBox(self)
            box.setWindowTitle("Chi tiết clip")
            box.setText(
                f"{STATUS_LABELS[row['status']]} · {CATEGORIES[row['category']]}\nNguồn: {row['source_path']}\nClip: {row['output_path'] or 'chưa có'}\n{row['error_message'] or row['notes'] or ''}"
            )
            box.setDetailedText("\n".join(f"{key}: {value}" for key, value in row.items()))
            box.exec()
