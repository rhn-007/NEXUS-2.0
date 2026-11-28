"""NEXUS fullscreen command-centre window.

Owns the pages, the navigation, the command bar, the floating companion and the
two background workers (the assistant and the PC statistics). It only displays
what NEXUS really reports: the activity label from ui.status, the push-to-talk
recording state, Piper playback and real PC statistics.
"""

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
)

from ai.ollama import DEFAULT_MODEL
from desktop import data_access, system_stats
from desktop.assistant_worker import AssistantWorker
from desktop.audio_levels import envelope_at
from desktop.companion import CompanionWindow
from desktop.hud_widgets import CommandBar, HudBackground, NavRail
from desktop.pages import (
    AssistantPage,
    HomePage,
    MemoryPage,
    ResearchPage,
    SettingsPage,
)
from desktop.stats_worker import StatsWorker
from desktop.status_logic import describe_state, mic_status, state_from_status
from desktop.theme import STYLE_SHEET, make_font, mono_font
from ui.status import get_status

PAGE_ORDER = ("HOME", "ASSISTANT", "RESEARCH", "MEMORY", "SETTINGS")
QUALITIES = ("low", "balanced", "high")
COMPANION_MODES = ("minimised", "always", "off")
ERROR_SECONDS = 6.0


class NexusWindow(QMainWindow):
    command_requested = Signal(str)
    listen_start_requested = Signal()
    listen_stop_requested = Signal()
    shutdown_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NEXUS")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(STYLE_SHEET)

        self._settings = QSettings("NEXUS", "NexusDesktop")
        quality = self._choice("orb_quality", "balanced", QUALITIES)
        self._companion_mode = self._choice("companion_mode", "minimised", COMPANION_MODES)

        # Real state, updated only from worker signals and ui.status.
        self._ready = False
        self._start_failed = False
        self._busy = False
        self._recording = False
        self._speaking = False
        self._talk_held = False
        self._error_until = 0.0
        self._state = "thinking"
        self._speech_levels = None
        self._speech_hop = 0.03
        self._speech_t0 = 0.0
        self._stats = {}
        self._fact_count = None
        self._last_page = "HOME"

        self._build_ui(quality)
        self._build_companion()
        self._start_workers()
        self._start_timers()

        QShortcut(QKeySequence("Escape"), self, activated=self.showMinimized)
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)

        self._apply_state("thinking")
        self._refresh_readouts()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _choice(self, key, default, allowed):
        value = str(self._settings.value(key, default))
        return value if value in allowed else default

    def _build_ui(self, quality):
        root = HudBackground()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(64, 46, 64, 30)
        outer.setSpacing(12)

        header = QHBoxLayout()
        brand = QLabel("N E X U S")
        brand.setFont(make_font(18, True, 6.0))
        brand.setStyleSheet("color: rgb(255, 170, 70);")
        header.addWidget(brand)
        header.addStretch(1)
        self.system_status = QLabel("STARTING NEXUS")
        self.system_status.setFont(make_font(12, False, 4.0))
        self.system_status.setStyleSheet("color: rgb(170, 134, 88);")
        header.addWidget(self.system_status)
        header.addStretch(1)
        self.indicators = QLabel("")
        self.indicators.setFont(mono_font(12, False, 1.5))
        self.indicators.setStyleSheet("color: rgb(190, 150, 96);")
        header.addWidget(self.indicators)
        outer.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(8)
        self.nav = NavRail()
        self.nav.selected.connect(self._select_page)
        body.addWidget(self.nav, 0, Qt.AlignmentFlag.AlignVCenter)

        self.pages = QStackedWidget()
        self.home_page = HomePage(quality)
        self.assistant_page = AssistantPage()
        self.research_page = ResearchPage()
        self.memory_page = MemoryPage()
        self.settings_page = SettingsPage(quality, self._companion_mode)
        for page in (self.home_page, self.assistant_page, self.research_page,
                     self.memory_page, self.settings_page):
            self.pages.addWidget(page)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)

        self.command_bar = CommandBar()
        self.command_bar.setMaximumWidth(1100)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.command_bar, 10)
        row.addStretch(1)
        outer.addLayout(row)

        self.command_bar.submitted.connect(self._submit)
        self.command_bar.mic_pressed.connect(self._begin_talk)
        self.command_bar.mic_released.connect(self._end_talk)
        self.command_bar.input.installEventFilter(self)
        self.research_page.research_requested.connect(self._submit)
        self.settings_page.quality_changed.connect(self._on_quality_changed)
        self.settings_page.companion_changed.connect(self._on_companion_changed)
        self.settings_page.fullscreen_requested.connect(self._toggle_fullscreen)

        self.settings_page.set_info("LANGUAGE MODEL", DEFAULT_MODEL)
        self.settings_page.set_info("DATABASE", data_access.database_path())
        self.settings_page.set_info("VOICE MODEL", "--")

    def _build_companion(self):
        self.companion = CompanionWindow()
        self.companion.restore_requested.connect(self.restore_from_companion)

    def _start_workers(self):
        self.worker_thread = QThread(self)
        self.worker = AssistantWorker()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.initialize)
        self.command_requested.connect(self.worker.process_command)
        self.listen_start_requested.connect(self.worker.start_listening)
        self.listen_stop_requested.connect(self.worker.stop_listening)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.ready.connect(self._on_ready)
        self.worker.response.connect(self._on_response)
        self.worker.failed.connect(self._on_failed)
        self.worker.user_text.connect(self._on_user_text)
        self.worker.busy_changed.connect(self._on_busy)
        self.worker.recording_changed.connect(self._on_recording)
        self.worker.speech_started.connect(self._on_speech_started)
        self.worker.speech_ended.connect(self._on_speech_ended)
        self.worker.stopped.connect(self.worker_thread.quit)
        self.worker_thread.start()

        self.stats_thread = QThread(self)
        self.stats_worker = StatsWorker()
        self.stats_worker.moveToThread(self.stats_thread)
        self.stats_thread.started.connect(self.stats_worker.start)
        self.stats_worker.updated.connect(self._on_stats)
        self.stats_thread.start()

    def _start_timers(self):
        # Follows the real activity state and audio level.
        self._activity_timer = QTimer(self)
        self._activity_timer.timeout.connect(self._poll_activity)
        self._activity_timer.start(40)

        # Clock, readouts and slow refreshes.
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._on_clock)
        self._clock_timer.start(1000)

    # ------------------------------------------------------------------
    # Navigation, window state, companion
    # ------------------------------------------------------------------

    def _select_page(self, name):
        if name not in PAGE_ORDER:
            return
        self._last_page = name
        self.pages.setCurrentIndex(PAGE_ORDER.index(name))
        self.nav.set_current(name)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _update_companion(self):
        mode = self._companion_mode
        wanted = mode == "always" or (mode == "minimised" and self.isMinimized())
        if wanted and not self.companion.isVisible():
            self.companion.show()
        elif not wanted and self.companion.isVisible():
            self.companion.hide()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_companion()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_companion()

    def restore_from_companion(self):
        """Clicking the companion brings back the fullscreen window and last workspace."""
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._select_page(self._last_page)
        self._update_companion()

    def _on_quality_changed(self, quality):
        if quality not in QUALITIES:
            return
        self._settings.setValue("orb_quality", quality)
        self.home_page.orb.set_quality(quality)

    def _on_companion_changed(self, mode):
        if mode not in COMPANION_MODES:
            return
        self._companion_mode = mode
        self._settings.setValue("companion_mode", mode)
        self._update_companion()

    # ------------------------------------------------------------------
    # Commands and push-to-talk
    # ------------------------------------------------------------------

    def _submit(self, text):
        text = str(text or "").strip()
        if not text or not self._ready or self._busy:
            return
        self.assistant_page.add_user(text)
        self._busy = True
        self._sync_controls()
        self.command_requested.emit(text)

    def _begin_talk(self):
        if self._talk_held or not self._ready or self._busy or self._recording:
            return
        self._talk_held = True
        self.listen_start_requested.emit()

    def _end_talk(self):
        if not self._talk_held:
            return
        self._talk_held = False
        self.listen_stop_requested.emit()

    def _handle_space(self, event):
        """Hold Space to talk. Returns True if the key event was used."""
        if event.key() != Qt.Key.Key_Space:
            return False
        if event.type() == QEvent.Type.KeyPress:
            if self._talk_held:
                return True
            typing = self.command_bar.input.hasFocus() and bool(self.command_bar.input.text())
            if typing or event.isAutoRepeat():
                return False
            if self._ready and not self._busy:
                self._begin_talk()
                return True
            return False
        if self._talk_held:
            if not event.isAutoRepeat():
                self._end_talk()
            return True
        return False

    def eventFilter(self, obj, event):
        if obj is self.command_bar.input and event.type() in (
                QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if self._handle_space(event):
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if not self._handle_space(event):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not self._handle_space(event):
            super().keyReleaseEvent(event)

    # ------------------------------------------------------------------
    # Worker signals
    # ------------------------------------------------------------------

    def _on_ready(self):
        self._ready = True
        try:
            voice = Path(self.worker.assistant.speaker.model).name
        except Exception:
            voice = "--"
        self.settings_page.set_info("VOICE MODEL", voice)
        self._refresh_fact_count()
        self._sync_controls()

    def _on_response(self, text):
        self.assistant_page.add_assistant(text)
        self.home_page.set_response(text)
        self._refresh_fact_count()

    def _on_failed(self, message):
        if not self._ready:
            # NEXUS never finished starting: say so instead of showing "starting".
            self._start_failed = True
            self.command_bar.hint.setText("NEXUS COULD NOT START")
        self._error_until = time.monotonic() + ERROR_SECONDS
        self.assistant_page.add_error(message)
        self.home_page.set_response(f"SYSTEM ERROR\n{message}")
        # A failed start-up leaves the controls disabled; a failed command does not.
        self._sync_controls()

    def _on_user_text(self, text):
        self.assistant_page.add_user(text, spoken=True)

    def _on_busy(self, busy):
        self._busy = bool(busy)
        self._sync_controls()

    def _on_recording(self, recording):
        self._recording = bool(recording)
        self.command_bar.set_recording(self._recording)
        if not self._recording:
            self._talk_held = False
        self._sync_controls()

    def _on_speech_started(self, levels, hop):
        self._speech_levels = levels
        self._speech_hop = float(hop) if hop else 0.03
        self._speech_t0 = time.monotonic()
        self._speaking = True

    def _on_speech_ended(self):
        self._speaking = False
        self._speech_levels = None

    def _on_stats(self, data):
        self._stats = data or {}
        self._refresh_indicators()

    def _sync_controls(self):
        self.command_bar.set_ready(self._ready)
        self.command_bar.set_busy(self._busy)
        self.research_page.set_busy(self._busy or not self._ready)

    # ------------------------------------------------------------------
    # Live state
    # ------------------------------------------------------------------

    def _compute_state(self):
        if time.monotonic() < self._error_until or self._start_failed:
            return "error"
        if not self._ready:
            return "thinking"
        return state_from_status(
            get_status(),
            recording=self._recording,
            speaking=self._speaking,
            busy=self._busy)

    def _poll_activity(self):
        state = self._compute_state()
        if state != self._state:
            self._apply_state(state)

        level = 0.0
        if self._recording:
            level = self.worker.mic_level()
        elif self._speaking:
            level = envelope_at(
                self._speech_levels, self._speech_hop, time.monotonic() - self._speech_t0)
        self.home_page.orb.set_level(level)
        self.companion.set_level(level)

    def _apply_state(self, state):
        self._state = state
        self.home_page.orb.set_state(state)
        self.companion.set_state(state)
        if self._start_failed:
            caption = "STARTUP FAILED"
        elif not self._ready and state != "error":
            caption = "STARTING UP"
        else:
            caption = describe_state(state)
        self.home_page.caption.setText(caption)
        self.system_status.setText(caption)
        self.research_page.set_activity(state == "researching")
        self._refresh_readouts()

    def _refresh_fact_count(self):
        totals = data_access.summary_counts()
        self._fact_count = totals.get("facts")

    def _refresh_readouts(self):
        home = self.home_page
        state = self._state
        home.left.set_value("CORE", describe_state(state), hot=state != "idle")
        home.left.set_value("MICROPHONE", mic_status(self._ready, self._recording, self._busy),
                            hot=self._recording)
        home.left.set_value("VOICE", "SPEAKING" if self._speaking else "STANDBY",
                            hot=self._speaking)
        home.left.set_value("RESEARCH", "ACTIVE" if state == "researching" else "IDLE",
                            hot=state == "researching")

        home.right.set_value("LANGUAGE MODEL", DEFAULT_MODEL)
        home.right.set_value("MEMORY ENTRIES",
                             "--" if self._fact_count is None else self._fact_count)
        fps = home.orb.measured_fps
        rendering = f"{fps:.0f} FPS  |  {home.orb.quality.upper()}" if fps else "PAUSED"
        home.right.set_value("RENDERING", rendering)
        home.right.set_value("INPUT", "PUSH-TO-TALK")
        self.settings_page.set_info("ORB RENDERING", rendering)

    def _refresh_indicators(self):
        stats = self._stats
        text = (f"CPU {system_stats.format_percent(stats.get('cpu'))}   "
                f"MEM {system_stats.format_percent(stats.get('memory'))}   "
                f"PWR {system_stats.format_battery(stats.get('battery'))}   "
                f"{datetime.now().strftime('%H:%M')}")
        self.indicators.setText(text)

    def _on_clock(self):
        self._refresh_indicators()
        self._refresh_readouts()
        if int(time.monotonic()) % 30 == 0:
            self._refresh_fact_count()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._activity_timer.stop()
        self._clock_timer.stop()
        self.companion.close()

        if self.worker_thread.isRunning():
            self.command_bar.setEnabled(False)
            self.shutdown_requested.emit()
            self.worker_thread.wait(10000)
            if self.worker_thread.isRunning():
                self.worker_thread.quit()
                self.worker_thread.wait(2000)

        if self.stats_thread.isRunning():
            self.stats_thread.quit()
            self.stats_thread.wait(2000)

        event.accept()
