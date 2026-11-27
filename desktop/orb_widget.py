"""Procedural, three-dimensional amber energy orb for the NEXUS HUD.

All geometry is generated deterministically once, then projected and animated
with Qt painting. No GIFs, videos, external assets, or random per-frame
geometry are used.
"""

import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


TAU = math.tau


def _unit(vector):
    length = math.sqrt(sum(component * component for component in vector))
    if length < 1e-9:
        return (1.0, 0.0, 0.0)
    return tuple(component / length for component in vector)


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _rotate(point, yaw, pitch, roll=0.0):
    x, y, z = point
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, z = x * cy - z * sy, x * sy + z * cy
    cp, sp = math.cos(pitch), math.sin(pitch)
    y, z = y * cp - z * sp, y * sp + z * cp
    cr, sr = math.cos(roll), math.sin(roll)
    x, y = x * cr - y * sr, x * sr + y * cr
    return x, y, z


class OrbWidget(QWidget):
    """Animated energy sphere with volumetric particles, filaments and rings."""

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
        self._rng = random.Random(27011)

        # Fibonacci distribution gives a stable, even spherical particle shell.
        self._particles = []
        particle_count = 1080
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))
        for index in range(particle_count):
            y = 1.0 - (2.0 * (index + 0.5) / particle_count)
            radial = math.sqrt(max(0.0, 1.0 - y * y))
            angle = index * golden_angle
            jitter = self._rng.uniform(-0.009, 0.009)
            point = _unit((
                radial * math.cos(angle + jitter),
                y,
                radial * math.sin(angle + jitter),
            ))
            self._particles.append((point, self._rng.uniform(0.55, 1.55), self._rng.random()))

        # Precompute a sparse nearest-neighbour graph. It forms a fine organic
        # lattice without the rigid appearance of a simple wireframe cage.
        self._edges = []
        for index, (point, _size, _seed) in enumerate(self._particles):
            nearest = []
            for other_index in range(index + 1, particle_count):
                other = self._particles[other_index][0]
                distance = sum((point[k] - other[k]) ** 2 for k in range(3))
                if distance < 0.052:
                    nearest.append((distance, other_index))
            nearest.sort(key=lambda item: item[0])
            self._edges.extend((index, other_index) for _distance, other_index in nearest[:4])

        # Curved, branching surface filaments. Their paths are spherical arcs,
        # so they retain convincing volume as the orb rotates.
        self._filaments = []
        for filament_index in range(76):
            start = _unit(tuple(self._rng.uniform(-1.0, 1.0) for _ in range(3)))
            end = _unit(tuple(self._rng.uniform(-1.0, 1.0) for _ in range(3)))
            while _dot(start, end) > 0.92 or _dot(start, end) < -0.92:
                end = _unit(tuple(self._rng.uniform(-1.0, 1.0) for _ in range(3)))
            path = self._make_spherical_arc(start, end, 30,
                                            self._rng.uniform(0.008, 0.035),
                                            self._rng.uniform(0.0, TAU))
            self._filaments.append((path, self._rng.uniform(0.45, 1.25), filament_index % 5 == 0))

            # A fine branch leaves selected main filaments at an irregular point.
            if filament_index % 2 == 0:
                branch_start = path[self._rng.randint(8, 21)]
                branch_end = _unit(tuple(
                    branch_start[k] + self._rng.uniform(-0.55, 0.55) for k in range(3)
                ))
                branch = self._make_spherical_arc(
                    branch_start, branch_end, 15,
                    self._rng.uniform(0.006, 0.022), self._rng.uniform(0.0, TAU)
                )
                self._filaments.append((branch, self._rng.uniform(0.3, 0.8), False))

        # Orbital ellipses have different inclinations, eccentricity and speeds.
        self._rings = []
        for ring_index in range(8):
            yaw = self._rng.uniform(-1.1, 1.1)
            pitch = self._rng.uniform(-1.25, 1.25)
            roll = self._rng.uniform(-0.7, 0.7)
            u = _rotate((1.0, 0.0, 0.0), yaw, pitch, roll)
            v = _rotate((0.0, 1.0, 0.0), yaw, pitch, roll)
            scale = self._rng.uniform(1.02, 1.23)
            flatten = self._rng.uniform(0.48, 0.82)
            speed = self._rng.choice((-1.0, 1.0)) * self._rng.uniform(0.12, 0.31)
            self._rings.append((u, v, scale, flatten, speed, ring_index))

        self._sparks = []
        for _ in range(90):
            point = _unit(tuple(self._rng.uniform(-1.0, 1.0) for _ in range(3)))
            self._sparks.append((point, self._rng.uniform(1.1, 2.5), self._rng.uniform(0.0, TAU)))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(33)

    @staticmethod
    def _make_spherical_arc(start, end, count, amplitude, phase):
        start = _unit(start)
        end = _unit(end)
        cosine = max(-0.999, min(0.999, _dot(start, end)))
        omega = math.acos(cosine)
        sine = max(1e-6, math.sin(omega))
        tangent = _unit(_cross(start, end))
        points = []
        for index in range(count):
            t = index / max(1, count - 1)
            a = math.sin((1.0 - t) * omega) / sine
            b = math.sin(t * omega) / sine
            base = tuple(a * start[k] + b * end[k] for k in range(3))
            wave = math.sin(t * math.pi * 3.0 + phase) * amplitude
            points.append(_unit(tuple(base[k] + tangent[k] * wave for k in range(3))))
        return points

    def set_state(self, state):
        state = str(state or "idle").lower()
        self._state = state if state in self.VALID_STATES else "idle"

    def _advance(self):
        speed = {
            "idle": 0.0038,
            "listening": 0.0090,
            "thinking": 0.0150,
            "speaking": 0.0110,
            "researching": 0.0100,
            "error": 0.0060,
        }.get(self._state, 0.0038)
        self._phase = (self._phase + speed) % TAU
        target = 1.0 if self._state in {"listening", "thinking", "speaking", "researching"} else 0.0
        self._state_mix += (target - self._state_mix) * 0.08
        self.update()

    def _entity_shape(self, point, seed=0.0):
        """Break the perfect sphere into an asymmetric, vertically flowing AI form."""
        x, y, z = point
        angle = math.atan2(z, x)
        vertical = 1.0 + 0.13 * math.cos(angle * 3.0 + seed * 0.7)
        vertical += 0.045 * math.sin(angle * 7.0 - self._phase * 0.18)
        crown = 0.10 * max(0.0, y) * math.sin(angle * 4.0 + seed)
        waist = 1.0 - 0.075 * math.exp(-((y + 0.05) / 0.28) ** 2)
        x *= waist * (1.0 + 0.075 * math.sin(angle * 5.0 + self._phase * 0.11))
        z *= waist * (1.0 + 0.06 * math.cos(angle * 4.0 - self._phase * 0.13))
        y = y * vertical + crown
        return (x, y * 1.14, z)

    def _project(self, point, cx, cy, radius, yaw, pitch, roll=0.0):
        x, y, z = _rotate(point, yaw, pitch, roll)
        perspective = 0.91 + (z + 1.0) * 0.075
        return QPointF(cx + x * radius * perspective, cy + y * radius * perspective), z

    @staticmethod
    def _draw_segment(painter, a, b, color, width):
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(a, b)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        side = min(self.width(), self.height())
        cx, cy = self.width() * 0.5, self.height() * 0.5
        base_radius = side * 0.305
        state_pulse = {
            "idle": 0.012,
            "listening": 0.032,
            "thinking": 0.022,
            "speaking": 0.026,
            "researching": 0.020,
            "error": 0.008,
        }.get(self._state, 0.012)
        pulse = 1.0 + state_pulse * math.sin(self._phase * 2.0)
        radius = base_radius * pulse
        yaw = self._phase
        pitch = 0.38 + math.sin(self._phase * 0.37) * 0.045
        roll = math.sin(self._phase * 0.23) * 0.035

        # Multi-layer bloom keeps the orb luminous without painting a solid disc.
        painter.setPen(Qt.PenStyle.NoPen)
        for factor, alpha in ((2.05, 13), (1.62, 20), (1.25, 24)):
            bloom = QRadialGradient(QPointF(cx, cy), radius * factor)
            bloom.setColorAt(0.0, QColor(255, 172, 74, alpha + int(self._state_mix * 8)))
            bloom.setColorAt(0.48, QColor(255, 103, 25, alpha))
            bloom.setColorAt(1.0, QColor(255, 75, 10, 0))
            painter.setBrush(bloom)
            painter.drawEllipse(QPointF(cx, cy), radius * factor, radius * factor)

        # Split each orbital ring at the depth plane. Rear arcs sit behind
        # the sphere; front arcs are painted later so the rings truly weave
        # through the particle shell instead of looking like flat overlays.
        rear_ring_segments = []
        front_ring_segments = []
        for u, v, scale, flatten, speed, ring_index in self._rings:
            ring_phase = self._phase * speed + ring_index * 0.47
            points = []
            for step in range(145):
                angle = TAU * step / 144.0 + ring_phase
                vector = tuple(
                    (u[k] * math.cos(angle) + v[k] * math.sin(angle) * flatten) * scale
                    for k in range(3)
                )
                screen, depth = self._project(vector, cx, cy, radius, yaw, pitch, roll)
                points.append((screen, depth))
            for index in range(len(points) - 1):
                a, da = points[index]
                b, db = points[index + 1]
                segment = (a, b)
                if (da + db) * 0.5 > 0.0:
                    front_ring_segments.append(segment)
                else:
                    rear_ring_segments.append(segment)

        for a, b in rear_ring_segments:
            self._draw_segment(painter, a, b, QColor(255, 142, 65, 25), 0.7)

        # Rotate and project the spherical particle shell.
        projected = []
        for point, size, seed in self._particles:
            shaped = self._entity_shape(point, seed)
            screen, depth = self._project(shaped, cx, cy, radius, yaw, pitch, roll)
            projected.append((screen, depth, size, seed))

        # Fine interconnected surface web, with hidden-side lines subdued.
        for first, second in self._edges:
            a, da, _sa, _ra = projected[first]
            b, db, _sb, _rb = projected[second]
            depth = (da + db) * 0.5
            if depth < -0.32:
                continue
            alpha = int(22 + max(0.0, depth) * 48)
            self._draw_segment(painter, a, b, QColor(255, 139, 53, alpha), 0.55)

        # Organic electrical filaments are drawn in two passes for a luminous core.
        for points, strength, branching in self._filaments:
            transformed = [
                self._project(self._entity_shape(point, strength),
                              cx, cy, radius * (1.006 if branching else 1.0),
                              yaw, pitch, roll)
                for point in points
            ]
            for index in range(len(transformed) - 1):
                a, da = transformed[index]
                b, db = transformed[index + 1]
                depth = (da + db) * 0.5
                if depth < -0.28:
                    continue
                alpha = int((18 + max(0.0, depth) * 42) * strength)
                self._draw_segment(painter, a, b, QColor(255, 105, 29, alpha), 2.0 if branching else 1.45)
                if depth > 0.05:
                    self._draw_segment(painter, a, b,
                                       QColor(255, 190, 111, min(150, int(alpha * 1.35))),
                                       0.48 if branching else 0.38)

        # Fine radial energy threads converge toward the bright reactor.
        for index in range(34):
            angle = TAU * index / 34.0 + self._phase * 0.13
            start = (math.cos(angle) * 0.93, math.sin(angle) * 0.93, 0.0)
            end = (math.cos(angle + 0.10) * 0.16, math.sin(angle + 0.10) * 0.16, 0.0)
            a, da = self._project(start, cx, cy, radius, yaw, pitch, roll)
            b, db = self._project(end, cx, cy, radius, yaw, pitch, roll)
            if da > -0.15:
                self._draw_segment(painter, a, b, QColor(255, 139, 54, 24), 0.7)

        # Particles are depth sorted so the near-side sparks sit above the web.
        for screen, depth, size, seed in sorted(projected, key=lambda item: item[1]):
            if depth < -0.62:
                continue
            alpha = max(24, min(205, int(72 + (depth + 1.0) * 68)))
            dot = size * (0.70 + (depth + 1.0) * 0.24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 105 + int(max(0.0, depth) * 42), 31, alpha // 3))
            painter.drawEllipse(screen, dot * 2.5, dot * 2.5)
            painter.setBrush(QColor(255, 139 + int(max(0.0, depth) * 35), 62, alpha))
            painter.drawEllipse(screen, dot, dot)
            if depth > 0.45 and seed > 0.78:
                painter.setBrush(QColor(255, 231, 185, min(235, alpha + 30)))
                painter.drawEllipse(screen, max(0.65, dot * 0.38), max(0.65, dot * 0.38))

        # Front orbital arcs cross over the sphere, completing the 3D weave.
        for a, b in front_ring_segments:
            self._draw_segment(painter, a, b, QColor(255, 171, 91, 118), 1.0)

        # Intermittent bright sparks around the sphere.
        for point, size, phase_offset in self._sparks:
            twinkle = 0.5 + 0.5 * math.sin(self._phase * 2.2 + phase_offset)
            if twinkle < 0.72:
                continue
            screen, depth = self._project(self._entity_shape(point, phase_offset),
                                          cx, cy, radius * 1.075, yaw, pitch, roll)
            if depth < -0.10:
                continue
            alpha = int(35 + twinkle * 105)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 188, 113, alpha))
            painter.drawEllipse(screen, size * twinkle, size * twinkle)

        # White-hot centre with amber plasma falloff and a soft corona.
        core_radius = radius * (0.172 + self._state_mix * 0.012)
        core = QRadialGradient(QPointF(cx - core_radius * 0.10, cy - core_radius * 0.12),
                               core_radius * 2.35)
        core.setColorAt(0.0, QColor(255, 255, 237, 255))
        core.setColorAt(0.12, QColor(255, 238, 194, 255))
        core.setColorAt(0.31, QColor(255, 185, 91, 238))
        core.setColorAt(0.58, QColor(255, 112, 34, 145))
        core.setColorAt(1.0, QColor(255, 79, 13, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(QPointF(cx, cy), core_radius * 1.82, core_radius * 2.65)

        # A fine inner highlight gives the core a glassy, high-energy centre.
        highlight = QRadialGradient(QPointF(cx - core_radius * 0.22, cy - core_radius * 0.25),
                                    core_radius * 0.72)
        highlight.setColorAt(0.0, QColor(255, 255, 246, 230))
        highlight.setColorAt(0.55, QColor(255, 230, 174, 95))
        highlight.setColorAt(1.0, QColor(255, 210, 130, 0))
        painter.setBrush(highlight)
        painter.drawEllipse(QPointF(cx, cy), core_radius * 0.60, core_radius * 0.92)

        # Vertical neural strands and a shifting crown make the silhouette
        # read as a digital entity rather than a perfectly spherical plasma ball.
        for strand in range(11):
            angle = TAU * strand / 11.0 + self._phase * 0.035
            points = []
            for step in range(34):
                t = step / 33.0
                y = -0.96 + t * 1.92
                width = 0.11 + 0.72 * abs(y) ** 0.72
                wobble = 0.035 * math.sin(t * 9.0 + strand * 1.7 + self._phase * 0.5)
                points.append((math.cos(angle) * width + wobble, y, math.sin(angle) * width))
            projected_strand = [
                self._project(point, cx, cy, radius * 0.92, yaw, pitch, roll)
                for point in points
            ]
            for index in range(len(projected_strand) - 1):
                a, da = projected_strand[index]
                b, db = projected_strand[index + 1]
                if (da + db) * 0.5 > -0.18:
                    alpha = 26 + int(max(0.0, (da + db) * 0.5) * 54)
                    self._draw_segment(painter, a, b, QColor(255, 91, 39, alpha), 0.72)

        for arc_index in range(5):
            arc_points = []
            start = -0.92 + arc_index * 0.16
            for step in range(48):
                t = step / 47.0
                angle = start + t * (1.42 + 0.18 * math.sin(self._phase * 0.2 + arc_index))
                y = 0.48 + 0.34 * math.sin(t * math.pi) + 0.035 * math.sin(t * 13 + self._phase)
                r = 0.55 + 0.11 * math.sin(t * math.pi * 2 + arc_index)
                arc_points.append((math.cos(angle) * r, y, math.sin(angle) * r))
            projected_arc = [
                self._project(point, cx, cy, radius * 1.04, yaw, pitch, roll)
                for point in arc_points
            ]
            for index in range(len(projected_arc) - 1):
                a, da = projected_arc[index]
                b, db = projected_arc[index + 1]
                if (da + db) * 0.5 > -0.1:
                    self._draw_segment(painter, a, b, QColor(255, 171, 100, 82), 0.9)

        painter.end()
