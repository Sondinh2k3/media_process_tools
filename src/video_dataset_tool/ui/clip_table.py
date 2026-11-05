from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
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


class ClipTableModel(QAbstractTableModel):
    HEADERS = ["Clip", "Nhóm", "Video nguồn", "IN", "OUT", "Chế độ", "Trạng thái", "Ghi chú / lỗi"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = []

    def replace_rows(self, rows):
        self.beginResetModel()
        self.values = [
            [
                Path(row["output_path"]).name if row["output_path"] else row["id"][:12],
                CATEGORIES[row["category"]],
                row["display_name"]
                + (" · mất nguồn" if row["source_availability"] == "missing" else ""),
                format_timecode(row["requested_in_ms"]),
                format_timecode(row["requested_out_ms"]),
                row["cut_mode"],
                STATUS_LABELS[row["status"]],
                row["error_message"] or row["notes"] or "",
            ]
            for row in rows
        ]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.values)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return self.values[index.row()][index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                self.HEADERS[section] if orientation == Qt.Orientation.Horizontal else section + 1
            )
        return None


class ClipTable(QWidget):
    PAGE_SIZE = 200
    csv_requested = Signal()
    error = Signal(str)

    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.rows = []
        self.page = 0
        self.total = 0
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
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Tìm tên nguồn, loại vật, ghi chú…")
        for widget in (self.source_filter, self.category_filter, self.status_filter, self.search):
            bar.addWidget(widget)
        layout.addLayout(bar)
        self.table = QTableView()
        self.model = ClipTableModel(self)
        self.table.setModel(self.model)
        self.table.setWordWrap(False)
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
        self.previous_button = QPushButton("‹ Trước")
        self.next_button = QPushButton("Sau ›")
        self.previous_button.clicked.connect(lambda: self.change_page(-1))
        self.next_button.clicked.connect(lambda: self.change_page(1))
        buttons.addWidget(self.previous_button)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.reset_filters)
        for combo in (self.source_filter, self.category_filter, self.status_filter):
            combo.currentIndexChanged.connect(self.reset_filters)
        self.search.textChanged.connect(self.schedule_search)
        self.search.returnPressed.connect(self.reset_filters)
        self.refresh_sources()

    def schedule_search(self):
        self.count_label.setText("Đang chờ tìm kiếm…")
        self.search_timer.start()

    @Slot()
    def reset_filters(self):
        self.search_timer.stop()
        self.page = 0
        self.refresh()

    def change_page(self, delta):
        self.page = max(0, min(self.page + delta, max(0, (self.total - 1) // self.PAGE_SIZE)))
        self.refresh()

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
        selected = self.selected()
        selected_id = selected["id"] if selected else None
        filters = (
            self.source_filter.currentData(),
            self.category_filter.currentData(),
            self.status_filter.currentData(),
            self.search.text(),
        )
        self.total = self.repository.count_clips(*filters)
        self.page = min(self.page, max(0, (self.total - 1) // self.PAGE_SIZE))
        offset = self.page * self.PAGE_SIZE
        self.rows = self.repository.clips(*filters, limit=self.PAGE_SIZE, offset=offset)
        self.model.replace_rows(self.rows)
        for index, row in enumerate(self.rows):
            if row["id"] == selected_id:
                self.table.selectRow(index)
                break
        start = offset + 1 if self.total else 0
        self.count_label.setText(f"{start}–{offset + len(self.rows)} / {self.total} clip")
        self.previous_button.setEnabled(self.page > 0)
        self.next_button.setEnabled(offset + len(self.rows) < self.total)

    def selected(self):
        index = self.table.currentIndex().row()
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
