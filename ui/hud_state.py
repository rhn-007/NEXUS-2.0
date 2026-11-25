"""
NEXUS HUD logic

Everything the HUD window needs that is not drawing: which state NEXUS is
in, the maths for the rotating globe, and the thread-safe hand-off between
the assistant threads and the window. It does not import tkinter, so it can
be tested on any machine.
"""

import math
import queue
import re
import threading


ANSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

STATE_BOOTING = "booting"
STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"

STATE_LABELS = {
    STATE_BOOTING: "STARTING",
    STATE_IDLE: "STANDING BY",
    STATE_LISTENING: "LISTENING",
    STATE_THINKING: "THINKING",
    STATE_SPEAKING: "SPEAKING",
}

MODE_LABELS = {
    "voice": "PUSH-TO-TALK",
    "continuous": "CONTINUOUS LISTENING",
    "keyboard": "KEYBOARD",
}

# How fast the rings turn in each state (1.0 = the idle pace).
STATE_SPEED = {
    STATE_BOOTING: 2.5,
    STATE_IDLE: 1.0,
    STATE_LISTENING: 1.5,
    STATE_THINKING: 3.2,
    STATE_SPEAKING: 2.0,
}


def derive_state(
    status,
    recording=False,
    mode="voice",
    speaking=False,
    booting=False
):
    """
    Work out the HUD state from what NEXUS already reports: the status
    label from ui.status, whether the microphone is recording, the input
    mode, and whether a reply is being spoken.
    """

    if booting:
        return STATE_BOOTING

    label = str(status or "").strip().lower()

    if speaking or label.startswith("speak"):
        return STATE_SPEAKING

    if label and not label.startswith("listen"):
        return STATE_THINKING

    if recording or label.startswith("listen") or mode == "continuous":
        return STATE_LISTENING

    return STATE_IDLE


def pulse_amount(state, seconds):
    """A number from 0 to 1 that drives the pulsing ring."""

    if state == STATE_LISTENING:
        return 0.5 + 0.5 * math.sin(seconds * 3.0)

    if state == STATE_BOOTING:
        return 0.5 + 0.5 * math.sin(seconds * 6.0)

    if state == STATE_SPEAKING:
        # Two waves of different speed, so it moves like a voice.
        value = (
            0.5
            + 0.3 * math.sin(seconds * 9.0)
            + 0.2 * math.sin(seconds * 5.3 + 1.0)
        )
        return min(1.0, max(0.0, value))

    return 0.0


def clean_text(text):
    """Remove terminal control codes before text goes in the chat log."""

    return ANSI_PATTERN.sub("", str(text)).replace("\r", "")


# ==========================================================
# GLOBE MATHS
# ==========================================================

def sphere_points(count):
    """Evenly spread points on a unit sphere (Fibonacci spiral)."""

    golden_angle = math.pi * (3.0 - math.sqrt(5.0))

    points = []

    for index in range(count):

        y = 1.0 - 2.0 * (index + 0.5) / count

        radius = math.sqrt(max(0.0, 1.0 - y * y))

        theta = golden_angle * index

        points.append(
            (math.cos(theta) * radius, y, math.sin(theta) * radius)
        )

    return points


def rotate_point(point, yaw, tilt):
    """Spin a point around the vertical axis, then tip it toward the viewer."""

    x, y, z = point

    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)

    x, z = x * cos_yaw + z * sin_yaw, -x * sin_yaw + z * cos_yaw

    cos_tilt, sin_tilt = math.cos(tilt), math.sin(tilt)

    y, z = y * cos_tilt - z * sin_tilt, y * sin_tilt + z * cos_tilt

    return x, y, z


def depth_bucket(z, levels):
    """Map depth (-1 far, 1 near) to a shade index from 0 to levels - 1."""

    index = int((z + 1.0) / 2.0 * levels)

    return max(0, min(levels - 1, index))


def polar(angle_degrees, radius):
    """
    Offset from the centre for an angle measured counter-clockwise from
    3 o'clock, the way tkinter measures arcs, in canvas coordinates.
    """

    radians = math.radians(angle_degrees)

    return math.cos(radians) * radius, -math.sin(radians) * radius


# ==========================================================
# HAND-OFF BETWEEN THREADS
# ==========================================================

class HudBridge:
    """
    Shared by the assistant threads and the window thread. The assistant
    side only writes text and flags; the window reads them on its own
    thread, because tkinter must only be touched from one thread.
    """

    def __init__(self):

        self._log = queue.SimpleQueue()

        self._lock = threading.Lock()

        self._speaking = 0

        self._booting = True

        self.close_requested = threading.Event()

    def write_log(self, text):

        text = clean_text(text)

        if text:
            self._log.put(text)

    def drain_log(self):

        pieces = []

        while True:

            try:
                pieces.append(self._log.get_nowait())
            except queue.Empty:
                break

        return "".join(pieces)

    def begin_speaking(self):

        with self._lock:
            self._speaking += 1

    def end_speaking(self):

        with self._lock:
            self._speaking = max(0, self._speaking - 1)

    @property
    def speaking(self):

        with self._lock:
            return self._speaking > 0

    def set_ready(self):

        with self._lock:
            self._booting = False

    @property
    def booting(self):

        with self._lock:
            return self._booting


class TeeStream:
    """
    Stands in for sys.stdout: everything still reaches the terminal, and a
    copy goes to the HUD chat log.
    """

    def __init__(self, original, bridge):

        self._original = original

        self._bridge = bridge

    def write(self, text):

        written = None

        if self._original is not None:

            try:
                written = self._original.write(text)
            except Exception:
                pass

        try:
            self._bridge.write_log(text)
        except Exception:
            pass

        return len(text) if written is None else written

    def flush(self):

        if self._original is not None:

            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self):

        try:
            return bool(self._original and self._original.isatty())
        except Exception:
            return False

    def __getattr__(self, name):

        if self._original is None:
            raise AttributeError(name)

        return getattr(self._original, name)
