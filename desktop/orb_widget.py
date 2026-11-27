"""Procedural amber energy-orb widget for the NEXUS desktop UI.

This first rendering pass is deliberately self-contained and uses Qt painting.
The detailed particle/filament renderer will be refined against the supplied
visual references in the dedicated orb phase.
"""

import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class OrbWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(220, 220)
        self._phase = 0.0
        self._state = "idle"
        self._rng = random.Random(27)
        self._particles = []
        for _ in range(950):
            z = self._rng.uniform(-1.0, 1.0)
            angle = self._rng.uniform(0.0, math.tau)
            radius = math.sqrt(max(0.0, 1.0 - z * z))
            self._particles.append((radius * math.cos(angle), radius * math.sin(angle), z,
                                    self._rng.uniform(0.55, 1.7)))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(33)

    def set_state(self, state):
        state = str(state or "idle").lower()
        self._state = state if state in {"idle", "listening", "thinking", "speaking", "researching", "error"} else "idle"

    def _advance(self):
        speed = {"idle": 0.003, "listening": 0.009, "thinking": 0.016,
                 "speaking": 0.012, "researching": 0.011, "error": 0.006}.get(self._state, 0.003)
        self._phase = (self._phase + speed) % math.tau
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        cx, cy = self.width() / 2, self.height() / 2
        radius = side * 0.34
        pulse = 1.0 + 0.018 * math.sin(self._phase * 2.0)
        radius *= pulse

        # Soft outer bloom and bright central reactor.
        glow = QRadialGradient(QPointF(cx, cy), radius * 1.75)
        glow.setColorAt(0.0, QColor(255, 157, 54, 48))
        glow.setColorAt(0.48, QColor(255, 105, 22, 22))
        glow.setColorAt(1.0, QColor(255, 90, 10, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), radius * 1.75, radius * 1.75)

        # Intersecting orbital paths.
        for index in range(5):
            angle = self._phase * (0.35 + index * 0.09) + index * 0.63
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(math.degrees(angle))
            painter.scale(1.0, 0.30 + index * 0.055)
            alpha = 95 if index % 2 else 145
            painter.setPen(QPen(QColor(255, 157, 65, alpha), 1.0 if index else 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), radius * (1.02 + index * 0.055), radius * (1.02 + index * 0.055))
            painter.restore()

        # Spherical particle shell with depth shading and fine connecting lines.
        projected = []
        ca, sa = math.cos(self._phase), math.sin(self._phase)
        tilt = 0.48
        ct, st = math.cos(tilt), math.sin(tilt)
        for x, y, z, size in self._particles:
            xr = x * ca - z * sa
            zr = x * sa + z * ca
            yr = y * ct - zr * st
            depth = y * st + zr * ct
            scale = 0.78 + (depth + 1.0) * 0.11
            px = cx + xr * radius * scale
            py = cy + yr * radius * scale
            brightness = int(75 + (depth + 1.0) * 85)
            projected.append((px, py, depth, size, brightness))

        # Sparse nearby connections create a filament-like web.
        stride = 19
        for i in range(0, len(projected) - stride, stride):
            a = projected[i]
            b = projected[i + stride]
            if abs(a[2] - b[2]) < 0.38:
                painter.setPen(QPen(QColor(255, 145, 55, 22 + int(max(a[2], 0) * 24)), 0.65))
                painter.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))

        for px, py, depth, size, brightness in projected:
            alpha = max(35, min(220, brightness + int(depth * 35)))
            color = QColor(255, 112 + max(0, int(depth * 35)), 35, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            dot = size * (0.65 + (depth + 1) * 0.22)
            painter.drawEllipse(QPointF(px, py), dot, dot)

        core_radius = radius * 0.19
        core = QRadialGradient(QPointF(cx - core_radius * 0.12, cy - core_radius * 0.15), core_radius * 2.0)
        core.setColorAt(0.0, QColor(255, 245, 208, 255))
        core.setColorAt(0.22, QColor(255, 190, 104, 245))
        core.setColorAt(0.58, QColor(255, 112, 35, 155))
        core.setColorAt(1.0, QColor(255, 90, 15, 0))
        painter.setBrush(core)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), core_radius * 2.0, core_radius * 2.0)
        painter.end()
