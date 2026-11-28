"""Floating NEXUS companion: a small, frameless, always-on-top orb.

Click it to bring the main window back. Drag it to move it. It never takes
keyboard focus, so it does not interrupt whatever the user is typing.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from desktop.orb_widget import OrbWidget


class CompanionWindow(QWidget):
    restore_requested = Signal()

    SIZE = 176
    MARGIN = 28
    DRAG_THRESHOLD = 6

    def __init__(self):
        flags = (Qt.WindowType.Tool
                 | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        # No parent: a parented window would be minimised along with the main one.
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setWindowTitle("NEXUS companion")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("NEXUS - click to open")

        self.orb = OrbWidget(self, quality="companion", transparent=True)
        self.orb.setGeometry(0, 0, self.SIZE, self.SIZE)
        # Let clicks fall through to this window.
        self.orb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._press_point = None
        self._press_origin = None
        self._dragged = False

        self.place_top_right()

    def place_top_right(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.SIZE - self.MARGIN, area.top() + self.MARGIN)

    def set_state(self, state):
        self.orb.set_state(state)

    def set_level(self, level):
        self.orb.set_level(level)

    # -- click to restore, drag to move --------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_point = event.globalPosition().toPoint()
            self._press_origin = self.frameGeometry().topLeft()
            self._dragged = False

    def mouseMoveEvent(self, event):
        if self._press_point is None:
            return
        delta = event.globalPosition().toPoint() - self._press_point
        if delta.manhattanLength() > self.DRAG_THRESHOLD:
            self._dragged = True
        if self._dragged:
            self.move(self._press_origin + delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_point is not None:
            clicked = not self._dragged
            self._press_point = None
            if clicked:
                self.restore_requested.emit()
