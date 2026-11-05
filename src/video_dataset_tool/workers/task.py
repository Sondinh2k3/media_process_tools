import logging

from PySide6.QtCore import QThread, Signal


class Task(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.succeeded.emit(self.function())
        except Exception as exc:
            logging.exception("Background task failed")
            self.failed.emit(str(exc))
