import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .core.paths import app_data_dir
from .ui.main_window import MainWindow


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Video Dataset Tool V1")
    parser.add_argument("--data-dir", type=Path, help="Thư mục database/settings/log cho dataset")
    parser.add_argument("--smoke-exit-ms", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    application = QApplication(sys.argv[:1])
    application.setApplicationName("VideoDatasetTool")
    application.setOrganizationName("VideoDatasetTool")
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Sans Serif", 10))
    application.setStyleSheet("""
        QMainWindow { background: #f3f5f7; }
        QPushButton { min-height: 25px; padding: 3px 8px; }
        QLineEdit, QComboBox, QDoubleSpinBox { min-height: 24px; }
        QListWidget, QTableWidget, QPlainTextEdit, QLineEdit { background: #ffffff; }
        QSplitter::handle { background: #d7dee4; }
        QStatusBar { background: #e6eeeb; }
    """)

    def report_exception(exc_type, exc_value, traceback):
        logging.error("Unhandled UI error", exc_info=(exc_type, exc_value, traceback))
        QMessageBox.warning(
            application.activeWindow(),
            "Không thể thực hiện",
            "Thao tác gặp lỗi. Dữ liệu đã lưu vẫn được giữ nguyên. Kiểm tra dung lượng/quyền truy cập; chi tiết trong application.log.",
        )

    sys.excepthook = report_exception
    try:
        data_dir = args.data_dir or app_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            data_dir / "application.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8"
        )
        logging.basicConfig(level=logging.INFO, handlers=[handler])
        window = MainWindow(data_dir)
        window.show()
        if args.smoke_exit_ms:
            QTimer.singleShot(args.smoke_exit_ms, window.close)
        return application.exec()
    except Exception as exc:
        logging.exception("Application startup failed")
        message = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Không thể khởi động ứng dụng. Kiểm tra thư mục dữ liệu và quyền ghi; chi tiết trong application.log nếu có."
        )
        QMessageBox.critical(None, "Không khởi động được", message)
        return 1
