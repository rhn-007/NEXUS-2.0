"""Small always-on-top orb shown while the main NEXUS window is minimized."""
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from desktop.orb_widget import OrbWidget


class CompanionOrb(QWidget):
    restore_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NEXUS Companion")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(190, 190)
        self.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.orb = OrbWidget(self)
        self.orb.setFixedSize(190, 190)
        self.orb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.orb)
        self._press_global = None
        self._press_window = None
        self._dragging = False

    def set_state(self, state):
        self.orb.set_state(state)

    def show_at_corner(self):
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 22, area.top() + 24)
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_window = self.frameGeometry().topLeft()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._press_global is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            current = event.globalPosition().toPoint()
            delta = current - self._press_global
            if not self._dragging and delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragging = True

            if self._dragging:
                target = self._press_window + delta
                screen = QGuiApplication.screenAt(current) or QGuiApplication.primaryScreen()
                if screen is not None:
                    area = screen.availableGeometry()
                    max_x = area.right() - self.width() + 1
                    max_y = area.bottom() - self.height() + 1
                    target.setX(max(area.left(), min(target.x(), max_x)))
                    target.setY(max(area.top(), min(target.y(), max_y)))
                self.move(target)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_global is not None:
            was_dragging = self._dragging
            self._press_global = None
            self._press_window = None
            self._dragging = False
            if not was_dragging:
                self.restore_requested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
