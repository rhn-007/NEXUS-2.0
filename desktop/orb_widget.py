"""Procedural reactor-style energy entity for the NEXUS desktop HUD.

Geometry and particle identities are generated once. Frames only update
rotations, pulse envelopes and projections; no image, GIF or video assets.
"""
import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

TAU = math.tau


def _unit(v):
    length = math.sqrt(sum(x * x for x in v))
    if length < 1e-9:
        return (1.0, 0.0, 0.0)
    return tuple(x / length for x in v)


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _rotate(p, yaw, pitch, roll=0.0):
    x, y, z = p
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, z = x * cy - z * sy, x * sy + z * cy
    cp, sp = math.cos(pitch), math.sin(pitch)
    y, z = y * cp - z * sp, y * sp + z * cp
    cr, sr = math.cos(roll), math.sin(roll)
    return x * cr - y * sr, x * sr + y * cr, z


class OrbWidget(QWidget):
    """Transparent, animated spherical reactor with a layered energy core."""

    VALID_STATES = {"idle", "listening", "thinking", "speaking", "researching", "error"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setMinimumSize(220, 220)

        self._phase = 0.0
        self._state = "idle"
        self._state_mix = 0.0
        self._audio_level = 0.0
        self._rng = random.Random(27011)

        # Stable, slightly irregular spherical particle cloud.
        self._particles = []
        count = 1240
        golden = math.pi * (3.0 - math.sqrt(5.0))
        for i in range(count):
            y = 1.0 - 2.0 * (i + 0.5) / count
            radial = math.sqrt(max(0.0, 1.0 - y * y))
            angle = i * golden + self._rng.uniform(-0.025, 0.025)
            point = _unit((
                radial * math.cos(angle) + self._rng.gauss(0, 0.012),
                y + self._rng.gauss(0, 0.009),
                radial * math.sin(angle) + self._rng.gauss(0, 0.012),
            ))
            # Seed, size and brightness remain attached to this particle.
            self._particles.append((
                point,
                self._rng.choices((0.55, 0.85, 1.15, 1.65, 2.15), (16, 34, 32, 15, 3))[0],
                self._rng.random(),
                self._rng.uniform(0.0, TAU),
            ))

        # Irregular local connections; a small number of longer links create
        # the circuitry-like diagonals visible in the reference.
        self._edges = []
        for i, (point, _size, _seed, _phase) in enumerate(self._particles):
            near = []
            for j in range(i + 1, count):
                other = self._particles[j][0]
                d2 = sum((point[k] - other[k]) ** 2 for k in range(3))
                if d2 < 0.047:
                    near.append((d2, j))
            near.sort(key=lambda item: item[0])
            for _d, j in near[:self._rng.choice((2, 3, 3, 4))]:
                if self._rng.random() < 0.78:
                    self._edges.append((i, j, self._rng.random()))

        # Branching electrical paths. Each path is a stable spherical walk
        # with bends and occasional forks, not a repeated geometric lattice.
        self._filaments = []
        for fi in range(112):
            start = _unit(tuple(self._rng.uniform(-1, 1) for _ in range(3)))
            direction = _unit(tuple(self._rng.uniform(-1, 1) for _ in range(3)))
            length = self._rng.randint(13,  thirty := 30)
            points = [start]
            current = start
            for step in range(1, length):
                blend = tuple(
                    current[k] * 0.72 + direction[k] * 0.28
                    + self._rng.uniform(-0.16, 0.16)
                    for k in range(3)
                )
                current = _unit(blend)
                points.append(current)
            strength = self._rng.uniform(0.42, 1.25)
            self._filaments.append((points, strength, fi % 7 == 0))
            if fi % 2 == 0:
                branch_at = self._rng.randint(4, length - 4)
                branch_start = points[branch_at]
                branch_dir = _unit(tuple(
                    branch_start[k] + self._rng.uniform(-0.8, 0.8)
                    for k in range(3)
                ))
                branch = [branch_start]
                current = branch_start
                for _ in range(self._rng.randint(7, 13)):
                    current = _unit(tuple(
                        current[k] * 0.68 + branch_dir[k] * 0.32
                        + self._rng.uniform(-0.18, 0.18)
                        for k in range(3)
                    ))
                    branch.append(current)
                self._filaments.append((branch, strength * 0.62, False))

        # Independent elliptical orbital bands with varied eccentricity,
        # inclination, depth and angular velocity.
        self._rings = []
        for ri in range(11):
            yaw = self._rng.uniform(-1.4, 1.4)
            pitch = self._rng.uniform(-1.45, 1.45)
            roll = self._rng.uniform(-1.0, 1.0)
            u = _rotate((1, 0, 0), yaw, pitch, roll)
            v = _rotate((0, 1, 0), yaw, pitch, roll)
            self._rings.append({
                "u": u, "v": v,
                "scale": self._rng.uniform(0.94, 1.25),
                "flatten": self._rng.uniform(0.48, 0.94),
                "speed": self._rng.choice((-1, 1)) * self._rng.uniform(0.10, 0.34),
                "phase": self._rng.uniform(0, TAU),
                "width": self._rng.choice((0.55, 0.75, 1.0, 1.35)),
                "bright": self._rng.random(),
            })

        # Dense inner reactor rings around the white-gold focal point.
        self._reactor_rings = []
        for ri in range(6):
            self._reactor_rings.append((
                self._rng.uniform(0.115, 0.285),
                self._rng.uniform(0.72, 1.0),
                self._rng.uniform(-0.45, 0.45),
                self._rng.uniform(0.45, 1.0),
                self._rng.uniform(0.4, 1.8),
                self._rng.uniform(0, TAU),
            ))

        # Stable motes distributed both on and just outside the shell.
        self._sparks = []
        for _ in range(190):
            p = _unit(tuple(self._rng.uniform(-1, 1) for _ in range(3)))
            self._sparks.append((
                p, self._rng.uniform(0.7, 2.2),
                self._rng.uniform(0, TAU), self._rng.uniform(1.02, 1.23),
            ))

        # Short luminous streaks that rotate with the field.
        self._streaks = []
        for _ in range(74):
            p = _unit(tuple(self._rng.uniform(-1, 1) for _ in range(3)))
            tangent = _unit(_cross(p, (0, 1, 0)))
            self._streaks.append((
                p, tangent, self._rng.uniform(0.018, 0.085),
                self._rng.uniform(0, TAU), self._rng.uniform(0.5, 1.0),
            ))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(33)

    def set_state(self, state):
        state = str(state or "idle").lower()
        self._state = state if state in self.VALID_STATES else "idle"

    def set_audio_level(self, level):
        """Accept a normalized live audio envelope (0.0–1.0) from an audio source."""
        try:
            self._audio_level = max(0.0, min(1.0, float(level)))
        except (TypeError, ValueError):
            self._audio_level = 0.0

    def _advance(self):
        speeds = {
            "idle": 0.0032, "listening": 0.010, "thinking": 0.015,
            "speaking": 0.011, "researching": 0.012, "error": 0.005,
        }
        self._phase = (self._phase + speeds[self._state]) % TAU
        active = self._state in {"listening", "thinking", "speaking", "researching"}
        target = 1.0 if active else 0.0
        self._state_mix += (target - self._state_mix) * 0.075
        self._audio_level *= 0.90
        self.update()

    def _shape(self, p, seed=0.0):
        x, y, z = p
        angle = math.atan2(z, x)
        # Preserve a spherical silhouette but introduce small organic lobes.
        lobe = 1.0 + 0.035 * math.sin(angle * 5 + seed * 5)
        lobe += 0.022 * math.sin(y * 13 + seed * 8 + self._phase * 0.2)
        waist = 1.0 - 0.035 * math.exp(-((y + 0.02) / 0.32) ** 2)
        return (
            x * lobe * waist,
            y * (1.0 + 0.035 * math.sin(angle * 3 + seed)) * 1.04,
            z * lobe * waist,
        )

    def _project(self, p, cx, cy, radius, yaw, pitch, roll=0.0):
        x, y, z = _rotate(p, yaw, pitch, roll)
        perspective = 0.91 + (z + 1.0) * 0.075
        return QPointF(cx + x * radius * perspective, cy + y * radius * perspective), z

    @staticmethod
    def _line(painter, a, b, color, width):
        painter.setPen(QPen(
            color, width, Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
        ))
        painter.drawLine(a, b)

    def _draw_ring(self, painter, cx, cy, radius, yaw, pitch, roll,
                   u, v, scale, flatten, phase, color, width, segments=112):
        projected = []
        for i in range(segments + 1):
            a = TAU * i / segments + phase
            p = tuple(
                (u[k] * math.cos(a) + v[k] * math.sin(a) * flatten) * scale
                for k in range(3)
            )
            projected.append(self._project(p, cx, cy, radius, yaw, pitch, roll))
        for i in range(segments):
            a, da = projected[i]
            b, db = projected[i + 1]
            depth = (da + db) * 0.5
            alpha = int(color.alpha() * (0.28 + 0.72 * max(0.0, depth + 0.12)))
            self._line(painter, a, b, QColor(color.red(), color.green(), color.blue(), alpha), width)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        side = min(self.width(), self.height())
        cx, cy = self.width() * 0.5, self.height() * 0.5
        pulse = 1.0 + 0.012 * math.sin(self._phase * 2.0)
        pulse += self._audio_level * 0.025
        if self._state == "error":
            pulse += 0.008 * math.sin(self._phase * 4.0)
        radius = side * 0.365 * pulse
        yaw = self._phase * 0.82
        pitch = 0.34 + math.sin(self._phase * 0.29) * 0.055
        roll = math.sin(self._phase * 0.19) * 0.045
        error = self._state == "error"
        hot = self._state in {"thinking", "speaking", "researching"}
        glow_r = 255 if not error else 255
        glow_g = 112 if not error else 75
        glow_b = 28 if not error else 20

        # Broad volumetric corona and a more concentrated plasma halo.
        painter.setPen(Qt.PenStyle.NoPen)
        for factor, alpha in ((2.05, 10), (1.62, 16), (1.28, 25), (0.92, 24)):
            grad = QRadialGradient(QPointF(cx, cy), radius * factor)
            grad.setColorAt(0.0, QColor(255, 190, 104, alpha + int(self._state_mix * 8)))
            grad.setColorAt(0.42, QColor(glow_r, glow_g, glow_b, alpha))
            grad.setColorAt(1.0, QColor(255, 75, 10, 0))
            painter.setBrush(grad)
            painter.drawEllipse(QPointF(cx, cy), radius * factor, radius * factor)

        # Rear orbital structures.
        for ring in self._rings:
            phase = self._phase * ring["speed"] + ring["phase"]
            self._draw_ring(
                painter, cx, cy, radius, yaw, pitch, roll,
                ring["u"], ring["v"], ring["scale"], ring["flatten"], phase,
                QColor(255, 139, 55, 38 + int(ring["bright"] * 45)),
                ring["width"] * 0.78,
            )

        # Dense particle shell and stable projected coordinates.
        projected = []
        for p, size, seed, phase in self._particles:
            shaped = self._shape(p, seed)
            screen, depth = self._project(shaped, cx, cy, radius, yaw, pitch, roll)
            projected.append((screen, depth, size, seed, phase))

        # Fine web connections, deliberately varied in opacity and length.
        for i, j, seed in self._edges:
            a, da, *_ = projected[i]
            b, db, *_ = projected[j]
            depth = (da + db) * 0.5
            if depth < -0.42:
                continue
            shimmer = 0.65 + 0.35 * math.sin(self._phase * 1.7 + seed * 19)
            alpha = int((17 + max(0.0, depth) * 42) * shimmer)
            self._line(painter, a, b, QColor(255, 137, 48, alpha), 0.48 + seed * 0.28)

        # Jagged electrical filaments and their finer inner highlights.
        for points, strength, bright in self._filaments:
            path = [
                self._project(self._shape(p, strength), cx, cy,
                              radius * (1.012 if bright else 0.995),
                              yaw, pitch, roll)
                for p in points
            ]
            for k in range(len(path) - 1):
                a, da = path[k]
                b, db = path[k + 1]
                depth = (da + db) * 0.5
                if depth < -0.30:
                    continue
                flicker = 0.72 + 0.28 * math.sin(self._phase * 2.1 + k * 0.7 + strength * 9)
                alpha = int((22 + max(0.0, depth) * 76) * strength * flicker)
                self._line(painter, a, b, QColor(255, 105, 27, alpha),
                           1.15 if bright else 0.68)
                if bright and depth > -0.05:
                    self._line(painter, a, b, QColor(255, 205, 126, min(150, alpha)),
                               0.42)

        # Dynamic radial traces converge on the central reactor.
        for i in range(48):
            a = TAU * i / 48 + self._phase * (0.10 if i % 2 else -0.07)
            wobble = 0.025 * math.sin(self._phase * 1.8 + i * 2.3)
            start = (math.cos(a) * 0.91, math.sin(a) * 0.91, wobble)
            mid = (math.cos(a + 0.08) * 0.46, math.sin(a + 0.08) * 0.46, -wobble)
            end = (math.cos(a + 0.13) * 0.24, math.sin(a + 0.13) * 0.24, 0.0)
            p1, d1 = self._project(start, cx, cy, radius, yaw, pitch, roll)
            p2, d2 = self._project(mid, cx, cy, radius, yaw, pitch, roll)
            p3, d3 = self._project(end, cx, cy, radius, yaw, pitch, roll)
            if (d1 + d2) > -0.2:
                self._line(painter, p1, p2, QColor(255, 151, 62, 52), 0.72)
            if (d2 + d3) > -0.2:
                self._line(painter, p2, p3, QColor(255, 190, 102, 68), 0.82)

        # Moving streaks add directional motion without changing particle IDs.
        for p, tangent, length, phase, strength in self._streaks:
            drift = self._phase * (0.13 + strength * 0.10) + phase
            center = _unit(tuple(p[k] + tangent[k] * math.sin(drift) * 0.045 for k in range(3)))
            tail = _unit(tuple(center[k] - tangent[k] * length for k in range(3)))
            head = _unit(tuple(center[k] + tangent[k] * length * 0.35 for k in range(3)))
            a, da = self._project(self._shape(tail, phase), cx, cy, radius * 1.01, yaw, pitch, roll)
            b, db = self._project(self._shape(head, phase), cx, cy, radius * 1.01, yaw, pitch, roll)
            if (da + db) * 0.5 > -0.12:
                alpha = int(35 + strength * 95)
                self._line(painter, a, b, QColor(255, 179, 91, alpha), 0.7 + strength * 0.55)

        # Depth-sorted particle points.
        for screen, depth, size, seed, phase in sorted(projected, key=lambda item: item[1]):
            if depth < -0.68:
                continue
            twinkle = 0.72 + 0.28 * math.sin(self._phase * (1.3 + seed) + phase)
            alpha = max(20, min(225, int((62 + (depth + 1.0) * 73) * twinkle)))
            dot = size * (0.64 + (depth + 1.0) * 0.24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 105, 27, alpha // 4))
            painter.drawEllipse(screen, dot * 2.4, dot * 2.4)
            painter.setBrush(QColor(255, 137 + int(max(0, depth) * 40), 55, alpha))
            painter.drawEllipse(screen, dot, dot)
            if depth > 0.48 and seed > 0.72:
                painter.setBrush(QColor(255, 235, 190, min(235, alpha + 25)))
                painter.drawEllipse(screen, max(0.55, dot * 0.34), max(0.55, dot * 0.34))

        # Escaping motes and occasional bright perimeter sparks.
        for p, size, phase, scale in self._sparks:
            twinkle = 0.5 + 0.5 * math.sin(self._phase * 2.0 + phase)
            if twinkle < 0.67:
                continue
            screen, depth = self._project(self._shape(p, phase), cx, cy,
                                          radius * scale, yaw, pitch, roll)
            if depth < -0.05:
                continue
            alpha = int(25 + twinkle * 125)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 192, 117, alpha))
            painter.drawEllipse(screen, size * twinkle, size * twinkle)

        # Front orbital arcs complete the layered spherical volume.
        for ring in self._rings:
            phase = self._phase * ring["speed"] + ring["phase"]
            self._draw_ring(
                painter, cx, cy, radius, yaw, pitch, roll,
                ring["u"], ring["v"], ring["scale"], ring["flatten"], phase,
                QColor(255, 171, 91, 100 + int(ring["bright"] * 65)),
                ring["width"],
            )

        # Inner reactor: offset, independently rotating rings form a bright
        # circular aperture rather than a plain glowing ball.
        for ri, (r, flatten, tilt, speed, width, phase) in enumerate(self._reactor_rings):
            u = _rotate((1, 0, 0), tilt + self._phase * speed * 0.10,
                        0.18 * math.sin(self._phase * 0.25 + ri), 0)
            v = _rotate((0, 1, 0), tilt, 0.18 * math.sin(self._phase * 0.25 + ri), 0)
            self._draw_ring(
                painter, cx, cy, radius, yaw, pitch, roll,
                u, v, r, flatten, phase + self._phase * speed,
                QColor(255, 174 + ri * 8, 91, 115 + ri * 17),
                width,
                segments=84,
            )

        # Reactor corona, brilliant white-gold nucleus and a small optical
        # highlight. Core brightness rises with active states and audio input.
        energy = self._state_mix * 0.22 + self._audio_level * 0.34
        if self._state == "thinking":
            energy += 0.10
        if self._state == "researching":
            energy += 0.06
        core_r = radius * (0.105 + energy * 0.025)
        corona = QRadialGradient(QPointF(cx, cy), core_r * 4.4)
        corona.setColorAt(0.0, QColor(255, 244, 205, 245))
        corona.setColorAt(0.16, QColor(255, 190, 94, 225))
        corona.setColorAt(0.48, QColor(255, 112, 30, 112))
        corona.setColorAt(1.0, QColor(255, 70, 10, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(corona)
        painter.drawEllipse(QPointF(cx, cy), core_r * 4.4, core_r * 4.4)

        core = QRadialGradient(QPointF(cx - core_r * 0.10, cy - core_r * 0.12), core_r)
        core.setColorAt(0.0, QColor(255, 255, 250, 255))
        core.setColorAt(0.22, QColor(255, 249, 222, 255))
        core.setColorAt(0.52, QColor(255, 219, 153, 245))
        core.setColorAt(0.78, QColor(255, 150, 59, 190))
        core.setColorAt(1.0, QColor(255, 96, 22, 0))
        painter.setBrush(core)
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        highlight = QRadialGradient(QPointF(cx - core_r * 0.20, cy - core_r * 0.23), core_r * 0.42)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 255))
        highlight.setColorAt(0.62, QColor(255, 250, 224, 210))
        highlight.setColorAt(1.0, QColor(255, 231, 175, 0))
        painter.setBrush(highlight)
        painter.drawEllipse(QPointF(cx - core_r * 0.12, cy - core_r * 0.10),
                            core_r * 0.42, core_r * 0.42)

        # Error remains within the same identity; only its energy hue shifts.
        if error:
            warning = QRadialGradient(QPointF(cx, cy), radius * 1.18)
            warning.setColorAt(0.55, QColor(255, 45, 18, 12))
            warning.setColorAt(0.82, QColor(255, 55, 18, 42))
            warning.setColorAt(1.0, QColor(255, 35, 12, 0))
            painter.setBrush(warning)
            painter.drawEllipse(QPointF(cx, cy), radius * 1.18, radius * 1.18)

        painter.end()
