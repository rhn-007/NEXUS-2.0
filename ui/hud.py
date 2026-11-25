"""
NEXUS HUD window

A desktop window with a glowing ring display, a chat log and a text box.
Built with tkinter (part of Python), so nothing extra is installed.

The window only draws and collects typed text. What NEXUS is doing comes in
through `snapshot`, and typed text goes out through `on_submit`. See
hud_main.py for how it is connected to the assistant.
"""

import random
import sys
import time

from ui.hud_state import (
    STATE_BOOTING,
    STATE_LABELS,
    STATE_LISTENING,
    STATE_SPEAKING,
    STATE_SPEED,
    depth_bucket,
    polar,
    pulse_amount,
    rotate_point,
    sphere_points,
)


BACKGROUND = "#070d16"
CYAN = "#52e6ff"
CYAN_MID = "#1f8fb3"
CYAN_FAINT = "#16384a"
YELLOW = "#f2c230"
TEXT = "#9fe9ff"

# Layers drawn from the widest and darkest to the thinnest and brightest,
# which fakes a glow. Each layer is (line width at default size, colour).
GLOW_RING = ((9, "#0b2a3a"), (5, "#10506c"), (2, CYAN))
GLOW_BRACKET = ((7, "#0b2a3a"), (3, CYAN))
BAND = ((22, "#0d3550"), (16, "#1a6f9c"), (10, "#3aa8d8"))
GLOW_YELLOW = ((7, "#4a3a0a"), (3, YELLOW))
GLOW_SCANNER = ((7, "#1a5a70"), (3, "#d6fbff"))

# Globe dots, from far (dim) to near (bright).
GLOBE_SHADES = ("#1c2e3a", "#35505f", "#6d8c9b", "#b9d3de")

# Reference size the line widths and fonts are written for.
REFERENCE_RADIUS = 300.0

# Static rings: (radius as a fraction of the display, layers).
RINGS = (
    (0.98, ((1, "#12303f"),)),
    (0.74, GLOW_RING),
    (0.545, ((1, CYAN_MID),)),
    (0.50, ((1, CYAN_FAINT),)),
)

# Turning arcs: (radius, length in degrees, start angle, degrees per second
# at idle speed, layers, dash pattern or None).
ARCS = (
    (0.93, 50, 20, 6, GLOW_BRACKET, None),
    (0.93, 25, 140, -4, GLOW_BRACKET, None),
    (0.93, 14, 255, 9, GLOW_BRACKET, None),
    (0.66, 215, 200, -8, BAND, None),
    (0.66, 55, 60, -8, BAND, None),
    (0.575, 75, 110, 30, GLOW_YELLOW, None),
    (0.615, 22, 300, 30, ((3, YELLOW),), (2, 4)),
)

# The scanner arc speeds up the most when NEXUS is thinking.
SCANNER = (0.70, 40, 0, 40, GLOW_SCANNER, None)

TICK_COUNT = 120
TICK_INNER = 0.80
TICK_SHORT = 0.84
TICK_LONG = 0.88
TICK_SPEED = 4

GLOBE_RADIUS = 0.46
GLOBE_TILT = 0.4
GLOBE_SPEED = 14

SCATTER_COUNT = 150


class HudWindow:

    def __init__(
        self,
        bridge,
        snapshot,
        on_submit,
        fps=30,
        dots=420
    ):
        """
        bridge    -- HudBridge shared with the assistant threads.
        snapshot  -- callable returning (state, mode label).
        on_submit -- callable that receives text typed in the box.
        """

        import tkinter as tk

        self.tk = tk
        self.bridge = bridge
        self.snapshot = snapshot
        self.on_submit = on_submit
        self.fps = max(5, int(fps))

        self.speed = STATE_SPEED[STATE_BOOTING]
        self.seconds = 0.0
        self.last_frame = time.perf_counter()
        self.state = STATE_BOOTING
        self.mode_label = ""
        self.scale = None
        self.error_reported = False
        self.globe_yaw = 0.0
        self.tick_angle = 0.0
        self.scatter_angle = 0.0

        self.root = tk.Tk()
        self.root.title("NEXUS")
        self.root.geometry("920x860")
        self.root.minsize(640, 640)
        self.root.configure(bg=BACKGROUND)

        self._build_widgets()
        self._build_display(dots)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<F11>", self._toggle_fullscreen)

        self.entry.focus_set()

        self.append_log(
            "NEXUS HUD ready. Type below, or use your voice as usual.\n"
        )

    # ======================================================
    # WIDGETS
    # ======================================================

    def _build_widgets(self):

        tk = self.tk

        self.entry = tk.Entry(
            self.root,
            bg="#0b1624",
            fg="#e6fbff",
            insertbackground=CYAN,
            relief="flat",
            font=("Consolas", 11),
            highlightthickness=1,
            highlightbackground=CYAN_FAINT,
            highlightcolor=CYAN
        )
        self.entry.pack(side="bottom", fill="x", padx=18, pady=(4, 16))
        self.entry.bind("<Return>", self._submit)

        self.log = tk.Text(
            self.root,
            height=8,
            bg=BACKGROUND,
            fg=TEXT,
            relief="flat",
            font=("Consolas", 10),
            wrap="word",
            state="disabled",
            highlightthickness=1,
            highlightbackground=CYAN_FAINT
        )
        self.log.pack(side="bottom", fill="x", padx=18, pady=(0, 6))

        self.canvas = tk.Canvas(
            self.root,
            bg=BACKGROUND,
            highlightthickness=0,
            width=900,
            height=560
        )
        self.canvas.pack(side="top", fill="both", expand=True)

    def _build_display(self, dots):

        canvas = self.canvas

        random.seed(7)

        # Faint specks scattered outside the rings.
        self.scatter = []

        for _ in range(SCATTER_COUNT):

            angle = random.uniform(0, 360)
            radius = random.uniform(0.99, 1.2)

            item = canvas.create_rectangle(
                0, 0, 0, 0,
                fill=random.choice(("#5d8798", "#3a5a68", "#27404c")),
                outline=""
            )

            self.scatter.append((item, angle, radius))

        # Static rings.
        self.rings = []

        for radius, layers in RINGS:

            items = [
                canvas.create_oval(0, 0, 0, 0, outline=color, width=width)
                for width, color in layers
            ]

            self.rings.append((radius, layers, items))

        # Ticks.
        self.ticks = []

        for index in range(TICK_COUNT):

            long_tick = index % 5 == 0

            item = canvas.create_line(
                0, 0, 0, 0,
                fill="#3fb6d6" if long_tick else "#2a8aa8",
                width=2 if long_tick else 1
            )

            self.ticks.append((item, long_tick))

        # Turning arcs.
        self.arcs = []

        for spec in ARCS:
            self.arcs.append(self._make_arc(spec))

        self.scanner = self._make_arc(SCANNER)

        # Pulse rings, shown while listening, speaking and starting.
        self.pulse = [
            canvas.create_oval(
                0, 0, 0, 0, outline=color, width=width, state="hidden"
            )
            for width, color in ((4, "#0f4660"), (1, CYAN))
        ]
        self.pulse_visible = False

        # Globe.
        self.points = sphere_points(max(60, int(dots)))
        self.buckets = [-1] * len(self.points)
        self.globe = [
            canvas.create_rectangle(0, 0, 0, 0, fill=GLOBE_SHADES[0], outline="")
            for _ in self.points
        ]

        self.title = canvas.create_text(
            0, 0,
            text="N . E . X . U . S",
            fill=CYAN,
            font=("Consolas", 16, "bold")
        )

        self.status = canvas.create_text(
            0, 0,
            text="",
            fill=TEXT,
            font=("Consolas", 11)
        )

    def _make_arc(self, spec):

        radius, extent, start, speed, layers, dash = spec

        items = []

        for width, color in layers:

            options = {
                "start": start,
                "extent": extent,
                "style": "arc",
                "outline": color,
                "width": width,
            }

            if dash:
                options["dash"] = dash

            items.append(self.canvas.create_arc(0, 0, 0, 0, **options))

        return {
            "radius": radius,
            "extent": extent,
            "angle": float(start),
            "speed": speed,
            "layers": layers,
            "items": items,
        }

    # ======================================================
    # RUNNING
    # ======================================================

    def run(self):

        self.root.after(30, self._frame)
        self.root.mainloop()

    def close(self):

        self.bridge.close_requested.set()

        try:
            self.root.destroy()
        except Exception:
            pass

    def _toggle_fullscreen(self, _event=None):

        current = bool(self.root.attributes("-fullscreen"))

        self.root.attributes("-fullscreen", not current)

    def _submit(self, _event=None):

        text = self.entry.get().strip()

        self.entry.delete(0, "end")

        if text:
            self.on_submit(text)

    def append_log(self, text):

        log = self.log

        log.configure(state="normal")
        log.insert("end", text)

        lines = int(log.index("end-1c").split(".")[0])

        if lines > 600:
            log.delete("1.0", f"{lines - 500}.0")

        log.see("end")
        log.configure(state="disabled")

    # ======================================================
    # ANIMATION
    # ======================================================

    def _frame(self):

        started = time.perf_counter()

        try:
            self._tick(started)
        except Exception as error:
            # Keep the window alive; say so once instead of every frame.
            if not self.error_reported:
                self.error_reported = True
                print(f"HUD drawing error: {error}", file=sys.stderr)

        if self.bridge.close_requested.is_set():
            self.close()
            return

        elapsed_ms = (time.perf_counter() - started) * 1000

        delay = max(1, int(1000 / self.fps - elapsed_ms))

        self.root.after(delay, self._frame)

    def _canvas_size(self):

        return self.canvas.winfo_width(), self.canvas.winfo_height()

    def _tick(self, now):

        delta = min(0.1, max(0.0, now - self.last_frame))

        self.last_frame = now
        self.seconds += delta

        text = self.bridge.drain_log()

        if text:
            self.append_log(text)

        self.state, self.mode_label = self.snapshot()

        # Ease toward the speed for this state instead of jumping.
        target = STATE_SPEED.get(self.state, 1.0)

        self.speed += (target - self.speed) * min(1.0, delta * 4.0)

        width, height = self._canvas_size()

        if width < 50 or height < 120:
            return

        center_x = width / 2
        center_y = (height + 20) / 2
        unit = min(width, height - 70) / 2 * 0.82

        self._apply_scale(unit / REFERENCE_RADIUS)

        self._draw_rings(center_x, center_y, unit)
        self._draw_ticks(center_x, center_y, unit, delta)
        self._draw_arcs(center_x, center_y, unit, delta)
        self._draw_pulse(center_x, center_y, unit)
        self._draw_scatter(center_x, center_y, unit, delta)
        self._draw_globe(center_x, center_y, unit, delta)

        self.canvas.coords(self.title, center_x, 26)

        label = STATE_LABELS.get(self.state, "")

        if self.mode_label:
            label = f"{label}  |  {self.mode_label}"

        self.canvas.coords(self.status, center_x, height - 20)
        self.canvas.itemconfigure(self.status, text=label)

    def _apply_scale(self, scale):
        """Resize line widths only when the window size changed."""

        if self.scale is not None and abs(scale - self.scale) < 0.01:
            return

        self.scale = scale

        for _radius, layers, items in self.rings:
            self._set_widths(items, layers, scale)

        for arc in self.arcs + [self.scanner]:
            self._set_widths(arc["items"], arc["layers"], scale)

        self._set_widths(
            self.pulse, ((4, ""), (1, "")), scale
        )

    def _set_widths(self, items, layers, scale):

        for item, (width, _color) in zip(items, layers):

            self.canvas.itemconfigure(item, width=max(1, round(width * scale)))

    def _circle(self, item, center_x, center_y, radius):

        self.canvas.coords(
            item,
            center_x - radius, center_y - radius,
            center_x + radius, center_y + radius
        )

    def _draw_rings(self, center_x, center_y, unit):

        for radius, _layers, items in self.rings:

            for item in items:
                self._circle(item, center_x, center_y, radius * unit)

    def _draw_ticks(self, center_x, center_y, unit, delta):

        self.tick_angle += TICK_SPEED * self.speed * delta

        for index, (item, long_tick) in enumerate(self.ticks):

            angle = self.tick_angle + index * 360.0 / TICK_COUNT

            outer = TICK_LONG if long_tick else TICK_SHORT

            x1, y1 = polar(angle, TICK_INNER * unit)
            x2, y2 = polar(angle, outer * unit)

            self.canvas.coords(
                item,
                center_x + x1, center_y + y1,
                center_x + x2, center_y + y2
            )

    def _draw_arcs(self, center_x, center_y, unit, delta):

        for arc in self.arcs + [self.scanner]:

            arc["angle"] = (arc["angle"] + arc["speed"] * self.speed * delta) % 360

            radius = arc["radius"] * unit

            for item in arc["items"]:

                self._circle(item, center_x, center_y, radius)

                self.canvas.itemconfigure(item, start=arc["angle"])

    def _draw_pulse(self, center_x, center_y, unit):

        active = self.state in (
            STATE_LISTENING, STATE_SPEAKING, STATE_BOOTING
        )

        if active != self.pulse_visible:

            self.pulse_visible = active

            for item in self.pulse:
                self.canvas.itemconfigure(
                    item, state="normal" if active else "hidden"
                )

        if not active:
            return

        amount = pulse_amount(self.state, self.seconds)

        radius = (0.70 + 0.20 * amount) * unit

        for item in self.pulse:
            self._circle(item, center_x, center_y, radius)

    def _draw_scatter(self, center_x, center_y, unit, delta):

        self.scatter_angle += 1.5 * self.speed * delta

        for item, angle, radius in self.scatter:

            x, y = polar(angle + self.scatter_angle, radius * unit)

            self.canvas.coords(
                item,
                center_x + x - 1, center_y + y - 1,
                center_x + x + 1, center_y + y + 1
            )

    def _draw_globe(self, center_x, center_y, unit, delta):

        self.globe_yaw += GLOBE_SPEED * self.speed * delta * 3.14159265 / 180

        swell = 1.0

        if self.state in (STATE_LISTENING, STATE_SPEAKING):
            swell += 0.03 * pulse_amount(self.state, self.seconds)

        radius = GLOBE_RADIUS * unit * swell

        levels = len(GLOBE_SHADES)

        for index, point in enumerate(self.points):

            x, y, z = rotate_point(point, self.globe_yaw, GLOBE_TILT)

            screen_x = center_x + x * radius
            screen_y = center_y - y * radius

            half = 0.8 + (z + 1.0) * 0.6

            item = self.globe[index]

            self.canvas.coords(
                item,
                screen_x - half, screen_y - half,
                screen_x + half, screen_y + half
            )

            bucket = depth_bucket(z, levels)

            if bucket != self.buckets[index]:

                self.buckets[index] = bucket

                self.canvas.itemconfigure(item, fill=GLOBE_SHADES[bucket])
