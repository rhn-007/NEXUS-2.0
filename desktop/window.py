"""Fullscreen NEXUS command-centre window (initial UI foundation)."""

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from desktop.assistant_worker import AssistantWorker
from desktop.orb_widget import OrbWidget


class NexusWindow(QMainWindow):
    command_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NEXUS")
        self.setMinimumSize(1100, 700)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #070B10; color: #E8EDF2; }
            QLabel { color: #E8EDF2; }
            QPushButton { background: rgba(255,145,55,22); color: #FFC17C;
                border: 1px solid rgba(255,157,75,90); border-radius: 8px;
                padding: 9px 14px; }
            QPushButton:hover { background: rgba(255,145,55,45); }
            QLineEdit { background: #101923; border: 1px solid #394451;
                border-radius: 9px; padding: 12px; color: #F3F5F7; }
        """)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 20, 26, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        brand = QLabel("N E X U S")
        brand.setStyleSheet("color:#FFAA58; font-size:18px; font-weight:700; letter-spacing:4px;")
        self.system_status = QLabel("INITIALIZING SYSTEMS")
        self.system_status.setStyleSheet("color:#91A0AE; letter-spacing:2px;")
        header.addWidget(brand)
        header.addStretch(1)
        header.addWidget(self.system_status)
        layout.addLayout(header)

        self.pages = QStackedWidget()
        self.home_page = QWidget()
        home_layout = QVBoxLayout(self.home_page)
        home_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb = OrbWidget()
        self.orb.setFixedSize(520, 520)
        self.state_label = QLabel("ALL SYSTEMS STANDING BY")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("color:#D9985B; letter-spacing:3px; font-size:11px;")
        home_layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        home_layout.addWidget(self.state_label)
        self.pages.addWidget(self.home_page)
        layout.addWidget(self.pages, 1)

        nav = QHBoxLayout()
        self.nav_buttons = {}
        for name in ("HOME", "ASSISTANT", "RESEARCH", "MEMORY", "SETTINGS"):
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, label=name: self._select_page(label))
            nav.addWidget(button)
            self.nav_buttons[name] = button
        layout.addLayout(nav)

        command_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Enter a command for NEXUS...")
        self.command_input.returnPressed.connect(self._submit_command)
        self.send_button = QPushButton("SEND")
        self.send_button.clicked.connect(self._submit_command)
        command_row.addWidget(self.command_input, 1)
        command_row.addWidget(self.send_button)
        layout.addLayout(command_row)

        self.setCentralWidget(root)
        self._setup_worker()
        QShortcut(QKeySequence("Escape"), self, activated=self.showMinimized)

    def _setup_worker(self):
        self.thread = QThread(self)
        self.worker = AssistantWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.initialize)
        self.command_requested.connect(self.worker.process_command)
        self.worker.ready.connect(lambda: self.system_status.setText("ALL SYSTEMS ONLINE"))
        self.worker.response.connect(self._show_response)
        self.worker.state_changed.connect(self._set_state)
        self.worker.failed.connect(self._show_error)
        self.thread.start()

    def _select_page(self, name):
        if name == "HOME":
            self.pages.setCurrentWidget(self.home_page)
            return
        # Workspaces are added in subsequent UI phases; keep navigation live.
        self.state_label.setText(f"{name} WORKSPACE — IMPLEMENTATION IN PROGRESS")
        self.pages.setCurrentWidget(self.home_page)

    def _submit_command(self):
        command = self.command_input.text().strip()
        if not command:
            return
        self.command_input.clear()
        self.system_status.setText("PROCESSING REQUEST")
        self.command_requested.emit(command)

    def _show_response(self, response):
        self.system_status.setText("ALL SYSTEMS ONLINE")
        self.state_label.setText((response[:180].replace("\n", " ") or "READY"))

    def _set_state(self, state):
        self.orb.set_state(state)
        self.state_label.setText(state.upper())
        if state == "thinking":
            self.system_status.setText("PROCESSING REQUEST")

    def _show_error(self, message):
        self.orb.set_state("error")
        self.system_status.setText("SYSTEM ERROR")
        self.state_label.setText(str(message)[:180])

    def closeEvent(self, event):
        if self.thread.isRunning():
            self.worker.shutdown()
            self.thread.quit()
            self.thread.wait(5000)
        event.accept()
