"""NEXUS desktop command centre and workspace navigation."""
import html

from PySide6.QtCore import Qt, Signal, QThread, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QPushButton, QStackedWidget, QTextBrowser, QVBoxLayout,
    QWidget, QSplitter
)

from desktop.assistant_worker import AssistantWorker
from desktop.orb_widget import OrbWidget
from desktop.companion import CompanionOrb


STYLE = """
QMainWindow, QWidget { background:#070B10; color:#E7EDF3; }
QLabel { color:#DCE4EB; }
QPushButton {
  background:rgba(255,145,55,16); color:#F6B978;
  border:1px solid rgba(255,157,75,65); border-radius:9px;
  padding:9px 15px; font-size:11px; letter-spacing:1px;
}
QPushButton:hover { background:rgba(255,145,55,34); border-color:#C98245; }
QPushButton:checked { background:rgba(255,145,55,42); border-color:#FFAA58; color:#FFE0B8; }
QPushButton:disabled { color:#66717D; border-color:#29333D; }
QLineEdit {
  background:#0C141D; border:1px solid #354352; border-radius:10px;
  padding:13px; color:#F4F6F8; selection-background-color:#9C5B2E;
}
QListWidget, QTextBrowser {
  background:#0A1119; border:1px solid #263441; border-radius:10px;
  padding:9px; color:#DDE5EC;
}
QListWidget::item { padding:12px 9px; border-bottom:1px solid #1B2732; }
QListWidget::item:selected { background:#332315; color:#FFD4A2; }
QSplitter::handle { background:#1A2631; width:2px; }
"""


def _label(text, color="#8998A6", size=10, bold=False):
    label = QLabel(text)
    weight = "700" if bold else "400"
    label.setStyleSheet(
        f"color:{color};font-size:{size}px;font-weight:{weight};letter-spacing:1px;"
    )
    return label


class NexusWindow(QMainWindow):
    command_requested = Signal(str)
    snapshot_requested = Signal(str)
    shutdown_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NEXUS")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(STYLE)
        self._snapshots = {}
        self._chat_count = 0
        self._active_page = "HOME"

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 20, 28, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        brand = QLabel("N E X U S")
        brand.setStyleSheet(
            "color:#FFAD60;font-size:20px;font-weight:700;letter-spacing:5px;"
        )
        self.system_status = _label("INITIALIZING SYSTEMS", "#93A2AF", 10, True)
        header.addWidget(brand)
        header.addStretch(1)
        header.addWidget(self.system_status)
        layout.addLayout(header)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.nav_buttons = {}
        for name in ("HOME", "ASSISTANT", "RESEARCH", "MEMORY", "SETTINGS"):
            button = QPushButton(name)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, label=name: self._select_page(label))
            nav.addWidget(button)
            self.nav_buttons[name] = button
        layout.addLayout(nav)

        self.pages = QStackedWidget()
        self._build_home()
        self._build_assistant()
        self._build_research()
        self._build_memory()
        self._build_settings()
        layout.addWidget(self.pages, 1)

        command_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText(
            "Enter a command for NEXUS  ·  Try: research <topic>"
        )
        self.command_input.setEnabled(False)
        self.command_input.returnPressed.connect(self._submit_command)
        self.send_button = QPushButton("TRANSMIT")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self._submit_command)
        command_row.addWidget(self.command_input, 1)
        command_row.addWidget(self.send_button)
        layout.addLayout(command_row)

        footer = QHBoxLayout()
        footer.addWidget(_label("LOCAL-FIRST INTELLIGENCE", "#596978", 8))
        footer.addStretch(1)
        footer.addWidget(_label("NEXUS DESKTOP", "#596978", 8))
        layout.addLayout(footer)

        self.setCentralWidget(root)
        self._setup_worker()
        self.companion = CompanionOrb(self)
        self.companion.restore_requested.connect(self._restore_from_companion)
        self._select_page("HOME")
        QShortcut(QKeySequence("Escape"), self, activated=self.showMinimized)

    def _panel(self, title, subtitle=""):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:rgba(12,20,29,205);border:1px solid #263441;border-radius:12px;}"
        )
        box = QVBoxLayout(frame)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(8)
        box.addWidget(_label(title, "#FFB36C", 10, True))
        if subtitle:
            box.addWidget(_label(subtitle, "#81909D", 9))
        return frame, box

    def _build_home(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(4, 8, 4, 4)
        top = QHBoxLayout()
        left, left_box = self._panel("SYSTEM OVERVIEW", "LIVE CORE STATUS")
        self.home_core = _label("CORE  ·  INITIALIZING", "#D9A06C", 10, True)
        self.home_model = _label("AI ENGINE  ·  LOADING", "#A7B4C0", 9)
        self.home_voice = _label("VOICE  ·  LOADING", "#A7B4C0", 9)
        left_box.addWidget(self.home_core)
        left_box.addWidget(self.home_model)
        left_box.addWidget(self.home_voice)
        left_box.addStretch(1)
        left.setMinimumWidth(190)

        right, right_box = self._panel("ACTIVITY", "PERSISTENT KNOWLEDGE")
        self.home_research = _label("RESEARCH RECORDS  ·  —", "#A7B4C0", 9)
        self.home_memory = _label("PERSONAL FACTS  ·  —", "#A7B4C0", 9)
        right_box.addWidget(self.home_research)
        right_box.addWidget(self.home_memory)
        right_box.addStretch(1)
        right.setMinimumWidth(190)

        orb_column = QVBoxLayout()
        orb_column.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb = OrbWidget()
        self.orb.setFixedSize(480, 480)
        orb_column.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        self.state_label = _label("INITIALIZING NEXUS", "#DDA36E", 10, True)
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orb_column.addWidget(self.state_label)
        top.addWidget(left, 1)
        top.addLayout(orb_column, 3)
        top.addWidget(right, 1)
        outer.addLayout(top, 1)
        outer.addWidget(_label(
            "AWARE  ·  ADAPTIVE  ·  READY TO ASSIST",
            "#667887", 9
        ), 0, Qt.AlignmentFlag.AlignHCenter)
        self.pages.addWidget(page)

    def _build_assistant(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.addWidget(_label("ASSISTANT", "#FFB36C", 11, True))
        layout.addWidget(_label(
            "Conversation with your existing NEXUS core. Replies appear here while the command bar remains available.",
            "#8494A2", 9
        ))
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setHtml(
            "<div style='color:#8494A2;padding:20px'>"
            "NEXUS conversation workspace ready. Submit a message below to begin."
            "</div>"
        )
        layout.addWidget(self.chat_view, 1)
        self.pages.addWidget(page)

    def _build_research(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        heading = QHBoxLayout()
        heading.addWidget(_label("RESEARCH LIBRARY", "#FFB36C", 11, True))
        heading.addStretch(1)
        self.research_search = QLineEdit()
        self.research_search.setPlaceholderText("Search saved research...")
        self.research_search.setMaximumWidth(360)
        self.research_search.textChanged.connect(self._filter_research)
        heading.addWidget(self.research_search)
        layout.addLayout(heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.research_list = QListWidget()
        self.research_list.setMinimumWidth(250)
        self.research_list.currentItemChanged.connect(self._show_research_item)
        self.research_document = QTextBrowser()
        self.research_document.setOpenExternalLinks(True)
        self.research_document.setHtml(
            "<h2 style='color:#FFB36C'>Your research library</h2>"
            "<p style='color:#91A0AE'>Saved research sessions from the existing SQLite research store will appear here.</p>"
            "<p style='color:#91A0AE'>To start a new session, use the command bar: <b>research [topic]</b>.</p>"
        )
        splitter.addWidget(self.research_list)
        splitter.addWidget(self.research_document)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)
        self.pages.addWidget(page)

    def _build_memory(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.addWidget(_label("MEMORY", "#FFB36C", 11, True))
        layout.addWidget(_label(
            "A read-only view of facts already stored by NEXUS. This workspace does not rewrite or delete memory.",
            "#8494A2", 9
        ))
        self.memory_list = QListWidget()
        layout.addWidget(self.memory_list, 1)
        self.pages.addWidget(page)

    def _build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.addWidget(_label("SYSTEM CONFIGURATION", "#FFB36C", 11, True))
        layout.addWidget(_label(
            "Current runtime configuration. Settings are shown read-only until persistent controls are implemented.",
            "#8494A2", 9
        ))
        self.settings_view = QTextBrowser()
        layout.addWidget(self.settings_view, 1)
        self.settings_view.setHtml("<p style='color:#91A0AE'>Waiting for NEXUS initialization...</p>")
        self.pages.addWidget(page)

    def _setup_worker(self):
        self.thread = QThread(self)
        self.worker = AssistantWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.initialize)
        self.command_requested.connect(self.worker.process_command)
        self.snapshot_requested.connect(self.worker.load_snapshot)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.ready.connect(self._on_ready)
        self.worker.response.connect(self._show_response)
        self.worker.state_changed.connect(self._set_state)
        self.worker.failed.connect(self._show_error)
        self.worker.snapshot_ready.connect(self._on_snapshot)
        self.worker.stopped.connect(self.thread.quit)
        self.thread.start()

    def _on_ready(self):
        self.system_status.setText("ALL SYSTEMS ONLINE")
        self.command_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.state_label.setText("ALL SYSTEMS ARE ONLINE")
        for section in ("memory", "research", "settings"):
            self.snapshot_requested.emit(section)

    def _select_page(self, name):
        index = {"HOME": 0, "ASSISTANT": 1, "RESEARCH": 2, "MEMORY": 3, "SETTINGS": 4}[name]
        self._active_page = name
        self.pages.setCurrentIndex(index)
        for label, button in self.nav_buttons.items():
            button.setChecked(label == name)
        if name in ("MEMORY", "RESEARCH", "SETTINGS") and name.lower() not in self._snapshots:
            self.snapshot_requested.emit(name.lower())

    def _submit_command(self):
        command = self.command_input.text().strip()
        if not command:
            return
        self.command_input.clear()
        self.command_input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.system_status.setText("PROCESSING REQUEST")
        self.command_requested.emit(command)

    def _show_response(self, response):
        safe = html.escape(str(response or ""))
        self._chat_count += 1
        self.chat_view.append(
            f"<div style='margin:12px 4px;color:#FFB36C;font-weight:600'>"
            f"NEXUS</div><div style='color:#E0E7ED;white-space:pre-wrap'>{safe}</div>"
        )
        self.system_status.setText("ALL SYSTEMS ONLINE")
        self.state_label.setText("RESPONSE READY")
        self.command_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.snapshot_requested.emit("memory")
        self.snapshot_requested.emit("research")

    def _set_state(self, state):
        self.orb.set_state(state)
        if hasattr(self, "companion"):
            self.companion.set_state(state)
        self.state_label.setText(state.upper())
        if state in ("thinking", "researching", "speaking"):
            self.system_status.setText(state.upper())

    def _show_error(self, message):
        self.orb.set_state("error")
        self.system_status.setText("SYSTEM ERROR")
        self.state_label.setText(str(message)[:180])
        self.command_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.chat_view.append(
            f"<p style='color:#FF8A75'>NEXUS error: {html.escape(str(message))}</p>"
        )

    def _on_snapshot(self, section, payload):
        self._snapshots[section] = payload
        if "error" in payload:
            error = html.escape(str(payload["error"]))
            if section == "settings":
                self.settings_view.setHtml(f"<p style='color:#FF9B86'>{error}</p>")
            return

        if section == "settings":
            model = html.escape(str(payload.get("model", "Unknown")))
            voice = html.escape(str(payload.get("voice", "Unknown")))
            speed = html.escape(str(payload.get("speech_speed", "Unknown")))
            mode = html.escape(str(payload.get("input_mode", "Unknown")))
            database = html.escape(str(payload.get("database", "Unknown")))
            self.settings_view.setHtml(
                "<h2 style='color:#FFB36C'>AI ENGINE</h2>"
                f"<p>Local model: <b>{model}</b></p>"
                "<h2 style='color:#FFB36C'>VOICE</h2>"
                f"<p>Voice model: {voice}<br>Speech length scale: {speed}<br>Input mode: {mode}</p>"
                "<h2 style='color:#FFB36C'>STORAGE</h2>"
                f"<p>Existing database: {database}</p>"
                "<p style='color:#91A0AE'>Controls are intentionally read-only in this phase.</p>"
            )
            self.home_model.setText(f"AI ENGINE  ·  {payload.get('model', 'Unknown')}")
            self.home_voice.setText(f"VOICE  ·  {payload.get('input_mode', 'Unknown').upper()}")
        elif section == "memory":
            self.memory_list.clear()
            facts = payload.get("facts", [])
            for fact in facts:
                item = QListWidgetItem(f"{fact['key'].replace('_', ' ').title()}\n{fact['value']}")
                self.memory_list.addItem(item)
            self.home_memory.setText(f"PERSONAL FACTS  ·  {len(facts)}")
        elif section == "research":
            sessions = payload.get("sessions", [])
            topics = payload.get("topics", [])
            self.home_research.setText(f"RESEARCH SESSIONS  ·  {len(sessions)}")
            self.research_list.clear()
            for session in sessions:
                label = f"{session.get('topic', 'Untitled')}  ·  {session.get('status', 'unknown')}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, session)
                self.research_list.addItem(item)
            if not sessions and not topics:
                self.research_document.setHtml(
                    "<h2 style='color:#FFB36C'>No saved research yet</h2>"
                    "<p style='color:#91A0AE'>Start research from the command bar with: research [topic]</p>"
                )

        elif section.startswith("research_detail:"):
            session = payload.get("session")
            if not session:
                self.research_document.setHtml(
                    "<p style='color:#FF9B86'>This research session could not be loaded.</p>"
                )
                return
            title = html.escape(str(session.get("topic") or "Research session"))
            summary = html.escape(str(session.get("summary") or "No synthesis was saved."))
            status = html.escape(str(session.get("status") or "unknown"))
            created = html.escape(str(session.get("created_at") or ""))
            parts = [
                f"<h1 style='color:#FFB36C'>{title}</h1>",
                f"<p style='color:#91A0AE'>STATUS: {status.upper()} &nbsp; · &nbsp; {created}</p>",
                f"<div style='color:#E0E7ED;white-space:pre-wrap'>{summary}</div>",
                "<h2 style='color:#FFB36C'>SOURCES</h2>",
            ]
            sources = session.get("sources", [])
            if sources:
                for source in sources:
                    source_title = html.escape(str(source.get("title") or "Untitled source"))
                    url = str(source.get("url") or "")
                    safe_url = html.escape(url, quote=True)
                    publisher = html.escape(str(source.get("publisher") or "Publisher unknown"))
                    if url.lower().startswith(("https://", "http://")):
                        parts.append(
                            f"<p><a href='{safe_url}' style='color:#F2B477'>{source_title}</a>"
                            f"<br><span style='color:#91A0AE'>{publisher}</span></p>"
                        )
                    else:
                        parts.append(f"<p>{source_title} — {publisher}</p>")
            else:
                parts.append("<p style='color:#91A0AE'>No source records were attached to this session.</p>")
            findings = session.get("findings", [])
            if findings:
                parts.append("<h2 style='color:#FFB36C'>FINDINGS</h2>")
                for finding in findings:
                    claim = html.escape(str(finding.get("claim") or ""))
                    evidence = html.escape(str(finding.get("evidence") or ""))
                    confidence = float(finding.get("confidence") or 0)
                    parts.append(
                        f"<p style='color:#E0E7ED'><b>{claim}</b>"
                        f"<br><span style='color:#91A0AE'>{evidence}</span>"
                        f"<br><span style='color:#D79B62'>Confidence: {confidence:.0%}</span></p>"
                    )
            self.research_document.setHtml("".join(parts))

    def _filter_research(self, text):
        term = text.casefold().strip()
        for index in range(self.research_list.count()):
            item = self.research_list.item(index)
            item.setHidden(term not in item.text().casefold())

    def _show_research_item(self, current, previous):
        if current is None:
            return
        session = current.data(Qt.ItemDataRole.UserRole) or {}
        title = html.escape(str(session.get("topic") or "Research session"))
        summary = html.escape(str(session.get("summary") or "No synthesis was saved for this session."))
        status = html.escape(str(session.get("status") or "unknown"))
        created = html.escape(str(session.get("created_at") or ""))
        document = (
            f"<h1 style='color:#FFB36C'>{title}</h1>"
            f"<p style='color:#91A0AE'>STATUS: {status.upper()} &nbsp; · &nbsp; {created}</p>"
            f"<div style='color:#E0E7ED;white-space:pre-wrap'>{summary}</div>"
            "<p style='color:#91A0AE'>Loading saved source records and findings...</p>"
        )
        self.research_document.setHtml(document)
        session_id = session.get("id")
        if session_id is not None:
            self.snapshot_requested.emit(f"research_detail:{session_id}")

    def _restore_from_companion(self):
        self.companion.hide()
        self.showNormal()
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._select_page(self._active_page)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "companion"):
            if self.isMinimized():
                self.companion.set_state(self.orb._state)
                self.companion.show_at_corner()
            else:
                self.companion.hide()

    def closeEvent(self, event):
        if hasattr(self, "companion"):
            self.companion.hide()
        if self.thread.isRunning():
            self.command_input.setEnabled(False)
            self.send_button.setEnabled(False)
            self.shutdown_requested.emit()
            self.thread.wait(10000)
            if self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(2000)
        event.accept()
