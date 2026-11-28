"""Qt widget that shows the NEXUS energy orb.

The picture itself is produced by desktop.orb_engine (numpy light buffer with
bloom). This widget only owns the animation timer, hands the engine its state
and real audio level, and paints the finished frame.

    orb = OrbWidget()
    orb.set_state("thinking")      # idle | listening | thinking | speaking |
                                   # researching | error
    orb.set_level(0.4)             # real microphone / Piper loudness, 0..1
    orb.set_quality("high")        # low | balanced | high | companion
"""

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from desktop.orb_engine import QUALITY, VALID_STATES, OrbEngine


class OrbWidget(QWidget):
    """Animated energy orb. Pauses itself while hidden or minimised."""

    VALID_STATES = set(VALID_STATES)

    def __init__(self, parent=None, quality="balanced", transparent=False):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setMinimumSize(160, 160)

        self._transparent = bool(transparent)
        self._state = "idle"
        self._level = 0.0
        self._last_tick = time.perf_counter()
        self._frame_ms = 0.0
        self._fps = 0.0

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._advance)

        self._install_engine(quality)

    # ------------------------------------------------------------------
    # Engine management
    # ------------------------------------------------------------------

    def _install_engine(self, quality):
        self._engine = OrbEngine(quality, transparent=self._transparent)
        self._engine.set_state(self._state)
        self._engine.set_level(self._level)
        self._image_format = (QImage.Format.Format_ARGB32_Premultiplied
                              if self._transparent else QImage.Format.Format_RGB32)
        self._image = self._make_image()
        self._timer.setInterval(max(10, int(1000 / self._engine.fps)))
        self._last_tick = time.perf_counter()

    def _make_image(self):
        # The image points at the engine's buffer (no copy). The engine is kept
        # alive by self._engine and refills the buffer in place every frame.
        frame = self._engine.frame
        height, width = frame.shape[0], frame.shape[1]
        return QImage(frame.data, width, height, width * 4, self._image_format)

    def set_quality(self, quality):
        quality = quality if quality in QUALITY else "balanced"
        if quality == self._engine.quality:
            return
        self._install_engine(quality)
        self.update()

    @property
    def quality(self):
        return self._engine.quality

    # ------------------------------------------------------------------
    # State and audio
    # ------------------------------------------------------------------

    def set_state(self, state):
        state = str(state or "idle").lower()
        self._state = state if state in self.VALID_STATES else "idle"
        self._engine.set_state(self._state)

    def state(self):
        return self._state

    def set_level(self, level):
        self._level = max(0.0, min(1.0, float(level)))
        self._engine.set_level(self._level)

    @property
    def measured_fps(self):
        """Frames per second actually being produced (0 while paused)."""
        return self._fps

    # ------------------------------------------------------------------
    # Animation loop
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._last_tick = time.perf_counter()
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()
        self._fps = 0.0

    def _advance(self):
        started = time.perf_counter()
        dt = started - self._last_tick
        self._last_tick = started
        self._engine.step(dt)
        self._engine.render()
        self._image = self._make_image()
        self.update()
        spent = time.perf_counter() - started
        self._frame_ms += (spent * 1000.0 - self._frame_ms) * 0.1
        if dt > 0:
            self._fps += (1.0 / dt - self._fps) * 0.1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if not self._transparent:
            # Light adds to the dark background instead of covering it.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        side = float(min(self.width(), self.height()))
        target = QRectF((self.width() - side) / 2.0,
                        (self.height() - side) / 2.0, side, side)
        painter.drawImage(target, self._image)
        painter.end()
