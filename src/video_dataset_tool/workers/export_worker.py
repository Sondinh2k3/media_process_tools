import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.models import ExportResult
from ..services.export_service import export_clip
from ..storage.database import Database
from ..storage.repositories import Repository


class ExportWorker(QThread):
    progress = Signal(int)
    result_ready = Signal(object)
    processing = Signal()

    def __init__(self, request, output_root, parent=None, database_path=None):
        super().__init__(parent)
        self.request = request
        self.output_root = Path(output_root)
        self.cancel_event = threading.Event()
        self.database_path = database_path

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        database = None
        result = None
        try:
            if self.database_path:
                database = Database(self.database_path)
                repository = Repository(database)
                repository.set_processing(self.request.id)
            self.processing.emit()
            result = export_clip(
                self.request, self.output_root, self.cancel_event, self.progress.emit
            )
            if database:
                repository.finish_clip(self.request.id, result)
        except Exception:
            logging.exception("Could not persist export outcome")
            result = ExportResult(
                "failed",
                output_path=result.output_path if result else None,
                error_message="Không lưu được trạng thái xuất vào database. Kiểm tra dung lượng/quyền ghi. Nếu clip đã tạo, file vẫn được giữ nguyên; xem log và lịch sử sau khi mở lại.",
            )
            if database:
                try:
                    repository.finish_clip(self.request.id, result)
                except Exception:
                    logging.exception("Database remains unavailable")
        finally:
            if database:
                database.close()
        self.result_ready.emit(result)
