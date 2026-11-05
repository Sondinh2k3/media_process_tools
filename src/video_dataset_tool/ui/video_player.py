from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from ..core.timecode import format_timecode


class Timeline(QSlider):
    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.in_ms = 0
        self.out_ms = 0
        self.setMinimumHeight(32)
        self.setToolTip("Tua theo thời gian; vị trí xác nhận hiển thị ở đồng hồ phía trên.")

    def set_marks(self, in_ms: int, out_ms: int):
        self.in_ms, self.out_ms = in_ms, out_ms
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.maximum() <= 0:
            return
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self
        )
        painter = QPainter(self)
        painter.setPen(QColor("#208b70"))
        points = []
        for value, label in ((self.in_ms, "IN"), (self.out_ms, "OUT")):
            x = (
                groove.x()
                + handle.width() // 2
                + QStyle.sliderPositionFromValue(
                    0,
                    self.maximum(),
                    max(0, min(self.maximum(), value)),
                    groove.width() - handle.width(),
                )
            )
            points.append(x)
            painter.drawLine(x, 2, x, self.height() - 2)
            painter.drawText(max(0, min(self.width() - 26, x)), 11, label)
        painter.fillRect(
            points[0], self.height() - 5, max(0, points[1] - points[0]), 4, QColor("#208b70")
        )


class VideoPlayer(QWidget):
    playback_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.5)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.video.setMinimumSize(320, 200)
        self.player.setVideoOutput(self.video)
        self.preview_end = None
        self.pending_seek = None
        self.duration_ms = 0
        self.fps = 0.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video, 1)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b42318")
        layout.addWidget(self.error_label)
        controls = QHBoxLayout()
        self.play_button = QPushButton("Phát / Dừng")
        self.play_button.clicked.connect(self.toggle)
        controls.addWidget(self.play_button)
        for text, delta in (("−1s", -1000), ("+1s", 1000)):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, d=delta: self.seek_relative(d))
            controls.addWidget(button)
        self.clock = QLabel("00:00:00.000 / 00:00:00.000")
        controls.addWidget(self.clock, 1)
        self.rate = QComboBox()
        for rate in (0.25, 0.5, 1, 1.5, 2):
            self.rate.addItem(f"{rate}×", rate)
        self.rate.setCurrentIndex(2)
        self.rate.setToolTip("Tốc độ phát phụ thuộc codec và backend Qt.")
        self.rate.currentIndexChanged.connect(
            lambda: self.player.setPlaybackRate(self.rate.currentData())
        )
        controls.addWidget(self.rate)
        layout.addLayout(controls)
        audio_row = QHBoxLayout()
        for text, direction in (("◀ ≈1 frame", -1), ("≈1 frame ▶", 1)):
            button = QPushButton(text)
            button.setToolTip("Di chuyển xấp xỉ theo FPS; không bảo đảm chính xác từng frame.")
            button.clicked.connect(lambda checked=False, d=direction: self.step(d))
            audio_row.addWidget(button)
        self.mute = QPushButton("Tắt tiếng")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self.audio.setMuted)
        audio_row.addStretch()
        audio_row.addWidget(self.mute)
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(50)
        volume.setMaximumWidth(120)
        volume.setToolTip("Âm lượng")
        volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        audio_row.addWidget(volume)
        layout.addLayout(audio_row)
        self.timeline = Timeline()
        layout.addWidget(self.timeline)
        self.timeline.sliderReleased.connect(lambda: self.seek(self.timeline.value()))
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.seekableChanged.connect(self.timeline.setEnabled)
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.player.errorOccurred.connect(self.handle_error)

    def open(self, path, metadata, position=0):
        self.preview_end = None
        self.error_label.clear()
        self.duration_ms = metadata.duration_ms
        self.fps = metadata.fps
        self.pending_seek = position
        self.timeline.setRange(0, self.duration_ms)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()
        self.position_changed(0)

    @Slot(QMediaPlayer.MediaStatus)
    def media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.pending_seek is not None:
            self.player.setPosition(self.pending_seek)
            self.pending_seek = None

    @Slot("qint64")
    def duration_changed(self, duration):
        if duration > 0:
            self.duration_ms = duration
            self.timeline.setRange(0, min(duration, 2_147_483_647))

    @Slot("qint64")
    def position_changed(self, position):
        self.clock.setText(
            f"{format_timecode(max(0, position))} / {format_timecode(self.duration_ms)}"
        )
        if not self.timeline.isSliderDown():
            self.timeline.setValue(position)
        if self.preview_end is not None and position >= self.preview_end:
            self.player.pause()
            self.preview_end = None

    @Slot(QMediaPlayer.Error, str)
    def handle_error(self, error, message):
        if error != QMediaPlayer.Error.NoError:
            text = "Không phát được video. Kiểm tra codec, file nguồn và cài đặt FFmpeg/Qt Multimedia. Bạn vẫn có thể thử xuất clip nếu FFprobe đọc được file."
            self.error_label.setText(text)
            self.playback_error.emit(text)

    def toggle(self):
        self.preview_end = None
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, position):
        self.preview_end = None
        self.player.setPosition(max(0, min(self.duration_ms, position)))

    def seek_relative(self, delta):
        self.seek(self.player.position() + delta)

    def step(self, direction):
        self.player.pause()
        if self.fps > 0:
            self.seek_relative(round(1000 / self.fps) * direction)

    def preview(self, start, end):
        self.seek(start)
        self.preview_end = end
        self.player.play()

    def clear_source(self):
        self.preview_end = None
        self.pending_seek = None
        self.player.setSource(QUrl())
        self.duration_ms = 0
        self.timeline.setRange(0, 0)
        self.timeline.set_marks(0, 0)
        self.position_changed(0)

    def shutdown(self):
        self.clear_source()
        self.player.setVideoOutput(None)
        self.player.setAudioOutput(None)
