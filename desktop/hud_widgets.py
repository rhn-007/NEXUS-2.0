"""Custom-painted HUD building blocks: background, navigation, readouts,
command bar and the expandable response panel."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from desktop.theme import (
    AMBER,
    BACKGROUND,
    DIM,
    GOLD,
    HOT,
    make_font,
    mono_font,
    rgba,
)


def align_flags(*flags):
    """Combine Qt alignment flags into the plain int drawText expects."""
    value = 0
    for flag in flags:
        value |= int(getattr(flag, "value", flag))
    return value


LEFT_CENTER = align_flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignVCenter)


# ----------------------------------------------------------------------
# Background
# ----------------------------------------------------------------------

class HudBackground(QWidget):
    """Near-black backdrop with a warm glow, a faint grid and corner brackets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = None
        self._cache_key = None

    def _build(self, width, height, ratio):
        pixmap = QPixmap(max(1, int(width * ratio)), max(1, int(height * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(rgba(BACKGROUND))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        glow = QRadialGradient(QPointF(width / 2.0, height * 0.46),
                               max(width, height) * 0.62)
        glow.setColorAt(0.0, QColor(46, 24, 6, 130))
        glow.setColorAt(0.55, QColor(18, 10, 4, 70))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, width, height, QBrush(glow))

        painter.setPen(QPen(QColor(255, 163, 58, 9), 1))
        step = 56
        for x in range(0, width, step):
            painter.drawLine(x, 0, x, height)
        for y in range(0, height, step):
            painter.drawLine(0, y, width, y)

        # Corner brackets.
        painter.setPen(QPen(QColor(255, 163, 58, 140), 2))
        inset, length = 22, 58
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            x = inset if sx > 0 else width - inset
            y = inset if sy > 0 else height - inset
            painter.drawLine(x, y, x + sx * length, y)
            painter.drawLine(x, y, x, y + sy * length)

        # Fine edge ticks beside the top brackets.
        painter.setPen(QPen(QColor(255, 163, 58, 60), 1))
        for index in range(1, 9):
            offset = inset + length + 10 + index * 9
            tick = 6 if index % 4 else 11
            painter.drawLine(offset, inset, offset, inset + tick)
            painter.drawLine(width - offset, inset, width - offset, inset + tick)

        painter.end()
        return pixmap

    def paintEvent(self, event):
        width, height = self.width(), self.height()
        ratio = self.devicePixelRatioF()
        key = (width, height, ratio)
        if self._cache is None or self._cache_key != key:
            self._cache = self._build(width, height, ratio)
            self._cache_key = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)
        painter.end()


# ----------------------------------------------------------------------
# Navigation
# ----------------------------------------------------------------------

def _draw_glyph(painter, name, cx, cy, radius, color):
    pen = QPen(color, 1.5)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    centre = QPointF(cx, cy)

    if name == "HOME":
        painter.drawEllipse(centre, radius, radius)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(centre, 2.2, 2.2)

    elif name == "ASSISTANT":
        points = [QPointF(cx + radius * math.cos(math.radians(60 * i + 30)),
                          cy + radius * math.sin(math.radians(60 * i + 30)))
                  for i in range(6)]
        painter.drawPolygon(QPolygonF(points))

    elif name == "RESEARCH":
        painter.drawEllipse(QPointF(cx - 2, cy - 2), radius * 0.68, radius * 0.68)
        painter.drawLine(QPointF(cx + radius * 0.35, cy + radius * 0.35),
                         QPointF(cx + radius, cy + radius))

    elif name == "MEMORY":
        for offset, span in ((-5.5, 1.0), (0.0, 0.7), (5.5, 1.0)):
            painter.drawLine(QPointF(cx - radius * span, cy + offset),
                             QPointF(cx + radius * span, cy + offset))

    elif name == "SETTINGS":
        painter.drawEllipse(centre, radius * 0.52, radius * 0.52)
        for index in range(6):
            angle = math.radians(60 * index)
            painter.drawLine(
                QPointF(cx + math.cos(angle) * radius * 0.78,
                        cy + math.sin(angle) * radius * 0.78),
                QPointF(cx + math.cos(angle) * radius * 1.08,
                        cy + math.sin(angle) * radius * 1.08))


class NavRail(QWidget):
    """Floating navigation: a thin spine with glowing nodes, not a sidebar."""

    selected = Signal(str)

    ITEMS = ("HOME", "ASSISTANT", "RESEARCH", "MEMORY", "SETTINGS")
    ROW = 60
    TOP = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(214, self.ROW * len(self.ITEMS) + 2 * self.TOP)
        self.setMouseTracking(True)
        self._current = self.ITEMS[0]
        self._hover = None

    def current(self):
        return self._current

    def set_current(self, name, emit=False):
        if name not in self.ITEMS:
            return
        changed = name != self._current
        self._current = name
        self.update()
        if emit and changed:
            self.selected.emit(name)

    def _item_at(self, y):
        index = int((y - self.TOP) // self.ROW)
        if 0 <= index < len(self.ITEMS):
            return self.ITEMS[index]
        return None

    def mouseMoveEvent(self, event):
        item = self._item_at(event.position().y())
        if item != self._hover:
            self._hover = item
            self.setCursor(Qt.CursorShape.PointingHandCursor if item
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self._item_at(event.position().y())
            if item:
                self.set_current(item, emit=True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        spine_x = 26.0
        first = self.TOP + self.ROW / 2.0
        last = self.TOP + self.ROW * (len(self.ITEMS) - 1) + self.ROW / 2.0
        painter.setPen(QPen(rgba(AMBER, 50), 1))
        painter.drawLine(QPointF(spine_x, first), QPointF(spine_x, last))

        for index, name in enumerate(self.ITEMS):
            cy = self.TOP + index * self.ROW + self.ROW / 2.0
            active = name == self._current
            hovered = name == self._hover

            if active:
                halo = QRadialGradient(QPointF(spine_x, cy), 22)
                halo.setColorAt(0.0, rgba(AMBER, 120))
                halo.setColorAt(1.0, rgba(AMBER, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(halo))
                painter.drawEllipse(QPointF(spine_x, cy), 22, 22)

                bar = QLinearGradient(spine_x, cy + 19, 205, cy + 19)
                bar.setColorAt(0.0, rgba(AMBER, 170))
                bar.setColorAt(1.0, rgba(AMBER, 0))
                painter.setPen(QPen(QBrush(bar), 1.5))
                painter.drawLine(QPointF(spine_x, cy + 19), QPointF(205, cy + 19))

            node_colour = rgba(HOT) if active else rgba(AMBER, 170 if hovered else 100)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(node_colour))
            radius = 4.5 if active else 2.8
            painter.drawEllipse(QPointF(spine_x, cy), radius, radius)

            text_colour = rgba(HOT) if active else rgba(GOLD if hovered else DIM)
            _draw_glyph(painter, name, 64.0, cy, 8.5, text_colour)

            painter.setFont(make_font(13, active, 2.8))
            painter.setPen(text_colour)
            painter.drawText(QRectF(88, cy - 15, 124, 30), LEFT_CENTER, name)

        painter.end()


# ----------------------------------------------------------------------
# Readouts
# ----------------------------------------------------------------------

class ReadoutPanel(QWidget):
    """A stack of small labelled values. Values are set by the owner from real data."""

    def __init__(self, keys, align_right=False, parent=None):
        super().__init__(parent)
        alignment = (Qt.AlignmentFlag.AlignRight if align_right
                     else Qt.AlignmentFlag.AlignLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._values = {}
        for index, key in enumerate(keys):
            if index:
                layout.addSpacing(16)
            label = QLabel(key)
            label.setFont(make_font(11, False, 2.6))
            label.setStyleSheet("color: rgb(150, 118, 76);")
            label.setAlignment(alignment)
            value = QLabel("--")
            value.setFont(mono_font(15, True, 1.0))
            value.setStyleSheet("color: rgb(255, 196, 110);")
            value.setAlignment(alignment)
            layout.addWidget(label)
            layout.addWidget(value)
            self._values[key] = value
        layout.addStretch(1)

    def set_value(self, key, text, hot=False):
        label = self._values.get(key)
        if label is None:
            return
        label.setText(str(text))
        label.setStyleSheet(
            "color: rgb(255, 238, 205);" if hot else "color: rgb(255, 196, 110);")


# ----------------------------------------------------------------------
# Command bar
# ----------------------------------------------------------------------

_MIC_IDLE = ""
_MIC_RECORDING = (
    "QPushButton { background: rgba(255, 90, 40, 175); color: #FFF3E0;"
    " border: 1px solid rgba(255, 200, 130, 230); border-radius: 17px; }"
)


class CommandBar(QWidget):
    """Microphone (hold to talk), text input, send button and push-to-talk status."""

    submitted = Signal(str)
    mic_pressed = Signal()
    mic_released = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._busy = False
        self._recording = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.hint = QLabel("")
        self.hint.setFont(make_font(11, False, 2.4))
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.hint)

        row = QHBoxLayout()
        row.setSpacing(12)
        outer.addLayout(row)

        self.mic = QPushButton("MIC")
        self.mic.setFont(make_font(12, True, 2.0))
        self.mic.setFixedSize(76, 40)
        self.mic.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mic.setToolTip("Hold to talk. Release to send.")
        self.mic.pressed.connect(self.mic_pressed.emit)
        self.mic.released.connect(self.mic_released.emit)
        row.addWidget(self.mic)

        self.input = QLineEdit()
        self.input.setFont(make_font(14))
        self.input.setPlaceholderText("Type a command, or hold the mic to speak...")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)

        self.send = QPushButton("SEND")
        self.send.setFont(make_font(12, True, 2.0))
        self.send.setFixedSize(84, 40)
        self.send.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.send.clicked.connect(self._send)
        row.addWidget(self.send)

        self._refresh()

    # -- state -------------------------------------------------------------

    def set_ready(self, ready):
        self._ready = bool(ready)
        self._refresh()

    def set_busy(self, busy):
        was_busy = self._busy
        self._busy = bool(busy)
        self._refresh()
        if was_busy and not self._busy and self._ready:
            self.input.setFocus()

    def set_recording(self, recording):
        self._recording = bool(recording)
        self.mic.setText("REC" if self._recording else "MIC")
        self.mic.setStyleSheet(_MIC_RECORDING if self._recording else _MIC_IDLE)
        self._refresh()

    def _refresh(self):
        usable = self._ready and not self._busy
        self.input.setEnabled(usable)
        self.send.setEnabled(usable)
        # The mic stays enabled while recording so the release is received.
        self.mic.setEnabled(usable or self._recording)

        if not self._ready:
            text = "STARTING NEXUS ..."
        elif self._recording:
            text = "RECORDING  |  RELEASE TO SEND"
        elif self._busy:
            text = "WORKING ..."
        else:
            text = "PUSH-TO-TALK  |  HOLD THE MIC BUTTON OR SPACE"
        self.hint.setText(text)
        self.hint.setStyleSheet(
            "color: rgb(255, 150, 90);" if self._recording else "color: rgb(150, 118, 76);")

    def _send(self):
        text = self.input.text().strip()
        if text and self.input.isEnabled():
            self.input.clear()
            self.submitted.emit(text)


# ----------------------------------------------------------------------
# Response panel (Home)
# ----------------------------------------------------------------------

class ResponsePanel(QWidget):
    """Latest NEXUS reply, collapsed to a few lines and expandable."""

    COLLAPSED = 78
    EXPANDED = 300
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 12, 22, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("NEXUS")
        title.setFont(make_font(11, True, 3.0))
        title.setStyleSheet("color: rgb(255, 176, 80);")
        header.addWidget(title)
        header.addStretch(1)
        self.toggle = QPushButton("EXPAND")
        self.toggle.setFont(make_font(10, True, 2.0))
        self.toggle.setFixedHeight(24)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle.clicked.connect(self._toggle)
        header.addWidget(self.toggle)
        layout.addLayout(header)

        self.body = QTextBrowser()
        self.body.setFont(make_font(14))
        self.body.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.body)

        self._apply_height()
        self.hide()

    def set_text(self, text):
        text = str(text or "").strip()
        self.body.setPlainText(text)
        self.setVisible(bool(text))
        self.changed.emit()

    def preferred_height(self):
        return (self.EXPANDED if self._expanded else self.COLLAPSED) + 62

    def _apply_height(self):
        self.body.setFixedHeight(self.EXPANDED if self._expanded else self.COLLAPSED)
        self.toggle.setText("COLLAPSE" if self._expanded else "EXPAND")

    def _toggle(self):
        self._expanded = not self._expanded
        self._apply_height()
        self.changed.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(rgba(AMBER, 60), 1))
        painter.setBrush(QBrush(QColor(8, 10, 14, 215)))
        painter.drawRoundedRect(rect, 16, 16)
        painter.end()
