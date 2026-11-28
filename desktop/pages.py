"""The five workspaces: Home, Assistant, Research, Memory and Settings.

Every control on these pages does something real, and every value shown comes
from NEXUS itself (its state, its SQLite data, the PC) or is empty.
"""

import html
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from desktop import data_access
from desktop.hud_widgets import ReadoutPanel, ResponsePanel
from desktop.orb_widget import OrbWidget
from desktop.theme import AMBER, make_font, rgba


def _page_title(text, subtitle=""):
    """Title block used at the top of every workspace."""
    box = QVBoxLayout()
    box.setSpacing(2)
    title = QLabel(text)
    title.setFont(make_font(22, True, 7.0))
    title.setStyleSheet("color: rgb(255, 196, 110);")
    box.addWidget(title)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setFont(make_font(11, False, 2.6))
        sub.setStyleSheet("color: rgb(150, 118, 76);")
        box.addWidget(sub)
    return box


def _small_label(text):
    label = QLabel(text)
    label.setFont(make_font(11, False, 2.4))
    label.setStyleSheet("color: rgb(150, 118, 76);")
    return label


# ----------------------------------------------------------------------
# Home
# ----------------------------------------------------------------------

class HomePage(QWidget):
    """The orb, flanked by live readouts, with the latest reply underneath."""

    LEFT_KEYS = ("CORE", "MICROPHONE", "VOICE", "RESEARCH")
    RIGHT_KEYS = ("LANGUAGE MODEL", "MEMORY ENTRIES", "RENDERING", "INPUT")

    def __init__(self, quality="balanced", parent=None):
        super().__init__(parent)
        self.orb = OrbWidget(self, quality=quality)
        self.left = ReadoutPanel(self.LEFT_KEYS, align_right=False, parent=self)
        self.right = ReadoutPanel(self.RIGHT_KEYS, align_right=True, parent=self)

        self.caption = QLabel("STANDING BY", self)
        self.caption.setFont(make_font(18, True, 9.0))
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setStyleSheet("color: rgb(255, 190, 100);")

        self.response = ResponsePanel(self)
        self.response.changed.connect(self._layout_children)

        self._decor = None
        self._decor_key = None
        self._orb_centre = QPointF(0, 0)
        self._orb_side = 0

    def set_response(self, text):
        self.response.set_text(text)

    # -- layout ------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_children()

    def _layout_children(self):
        width, height = self.width(), self.height()
        if width < 50 or height < 50:
            return

        reserved = 0
        if self.response.isVisible():
            reserved = self.response.preferred_height() + 16

        usable = max(160, height - reserved - 44)
        side = int(min(width * 0.58, usable * 1.02))
        centre_x = width / 2.0
        centre_y = (height - reserved) / 2.0 - 14

        self.orb.setGeometry(int(centre_x - side / 2), int(centre_y - side / 2), side, side)
        self._orb_centre = QPointF(centre_x, centre_y)
        self._orb_side = side

        caption_y = min(centre_y + side * 0.44, height - reserved - 40)
        self.caption.setGeometry(int(centre_x - 260), int(caption_y), 520, 32)

        panel_w = 210
        reach = side * 0.46
        left_x = max(8, int(centre_x - reach - panel_w - 12))
        right_x = min(width - panel_w - 8, int(centre_x + reach + 12))
        panel_h = 280
        panel_y = int(centre_y - panel_h / 2)
        self.left.setGeometry(left_x, panel_y, panel_w, panel_h)
        self.right.setGeometry(right_x, panel_y, panel_w, panel_h)

        if reserved:
            panel_width = int(min(940, width - 80))
            self.response.setGeometry(
                int((width - panel_width) / 2),
                height - self.response.preferred_height() - 8,
                panel_width,
                self.response.preferred_height())

        self._decor = None
        self.update()

    # -- decoration ----------------------------------------------------------

    def _build_decor(self, ratio):
        pixmap = QPixmap(max(1, int(self.width() * ratio)),
                         max(1, int(self.height() * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx, cy = self._orb_centre.x(), self._orb_centre.y()
        side = float(self._orb_side)

        def circle(radius, alpha, width=1.0):
            painter.setPen(QPen(rgba(AMBER, alpha), width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        circle(side * 0.455, 46)
        circle(side * 0.215, 22)

        painter.setPen(QPen(rgba(AMBER, 62), 1))
        for index in range(180):
            angle = math.radians(index * 2)
            inner = side * 0.462
            outer = side * (0.478 if index % 10 == 0 else 0.469)
            painter.drawLine(
                QPointF(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                QPointF(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer))

        painter.setPen(QPen(rgba(AMBER, 125), 2))
        radius = side * 0.495
        arc_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        for start in (35, 125, 215, 305):
            painter.drawArc(arc_rect, int(start * 16), int(26 * 16))

        painter.end()
        return pixmap

    def paintEvent(self, event):
        if self._orb_side <= 0:
            return
        ratio = self.devicePixelRatioF()
        key = (self.width(), self.height(), self._orb_side, ratio)
        if self._decor is None or self._decor_key != key:
            self._decor = self._build_decor(ratio)
            self._decor_key = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._decor)
        painter.end()


# ----------------------------------------------------------------------
# Assistant
# ----------------------------------------------------------------------

class AssistantPage(QWidget):
    """Full conversation log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 60, 10)
        layout.setSpacing(18)
        layout.addLayout(_page_title("ASSISTANT", "CONVERSATION LOG"))

        self.view = QTextBrowser()
        self.view.setFont(make_font(15))
        self.view.setOpenLinks(False)
        self.view.setPlaceholderText("Nothing said yet. Type below, or hold the mic and speak.")
        layout.addWidget(self.view, 1)

    def add_message(self, who, text, colour="#FFB050"):
        safe = html.escape(str(text)).replace("\n", "<br>")
        self.view.append(
            f'<p style="margin-bottom: 14px;">'
            f'<b style="color: {colour}; font-size: 11px;">{who}</b><br>'
            f'<span style="color: #EADFCB; font-size: 15px;">{safe}</span></p>')
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def add_user(self, text, spoken=False):
        self.add_message("YOU (VOICE)" if spoken else "YOU", text, "#E6C9A0")

    def add_assistant(self, text):
        self.add_message("NEXUS", text, "#FFB050")

    def add_error(self, text):
        self.add_message("SYSTEM", text, "#FF7A50")


# ----------------------------------------------------------------------
# Research
# ----------------------------------------------------------------------

class ResearchPage(QWidget):
    """Start research and browse what NEXUS has already researched."""

    research_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions = []
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 60, 10)
        layout.setSpacing(16)

        head = QHBoxLayout()
        head.addLayout(_page_title("RESEARCH", "SOURCES, FINDINGS AND HISTORY"))
        head.addStretch(1)
        self.status = QLabel("IDLE")
        self.status.setFont(make_font(13, True, 4.0))
        self.status.setStyleSheet("color: rgb(255, 196, 110);")
        head.addWidget(self.status, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.topic = QLineEdit()
        self.topic.setFont(make_font(14))
        self.topic.setPlaceholderText("Topic to research ...")
        self.topic.returnPressed.connect(self._start)
        row.addWidget(self.topic, 1)
        self.start_button = QPushButton("START RESEARCH")
        self.start_button.setFont(make_font(12, True, 2.0))
        self.start_button.setFixedHeight(40)
        self.start_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.start_button.clicked.connect(self._start)
        row.addWidget(self.start_button)
        layout.addLayout(row)

        body = QHBoxLayout()
        body.setSpacing(24)
        left = QVBoxLayout()
        left.addWidget(_small_label("PAST RESEARCH"))
        self.list = QListWidget()
        self.list.setFont(make_font(13))
        self.list.currentRowChanged.connect(self._show_details)
        left.addWidget(self.list, 1)
        body.addLayout(left, 2)

        right = QVBoxLayout()
        right.addWidget(_small_label("DETAILS"))
        self.details = QTextBrowser()
        self.details.setFont(make_font(14))
        self.details.setPlaceholderText("Select a research session.")
        right.addWidget(self.details, 1)
        body.addLayout(right, 3)
        layout.addLayout(body, 1)

        foot = QHBoxLayout()
        self.summary = _small_label("")
        foot.addWidget(self.summary, 1)
        refresh = QPushButton("REFRESH")
        refresh.setFont(make_font(11, True, 2.0))
        refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        refresh.clicked.connect(self.refresh)
        foot.addWidget(refresh)
        layout.addLayout(foot)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def set_activity(self, researching):
        self.status.setText("RESEARCHING" if researching else "IDLE")
        self.status.setStyleSheet(
            "color: rgb(255, 238, 205);" if researching else "color: rgb(255, 196, 110);")

    def set_busy(self, busy):
        self._busy = bool(busy)
        self.start_button.setEnabled(not busy)
        self.topic.setEnabled(not busy)

    def _start(self):
        topic = self.topic.text().strip()
        if topic and not self._busy:
            self.topic.clear()
            self.research_requested.emit(f"research {topic}")

    def refresh(self):
        sessions = data_access.research_sessions()
        self.list.clear()
        self.details.clear()
        if sessions is None:
            self._sessions = []
            self.summary.setText("NO RESEARCH DATABASE YET")
            return
        self._sessions = sessions
        for session in sessions:
            when = str(session.get("completed_at") or session.get("created_at") or "")[:10]
            title = session.get("topic") or session.get("original_query") or "Untitled"
            meta = f'{str(session.get("status") or "").upper()}  |  {session.get("sources", 0)} SOURCES  |  {when}'
            item = QListWidgetItem(f"{title}\n{meta}")
            self.list.addItem(item)
        self.summary.setText(f"{len(sessions)} RESEARCH SESSIONS STORED")
        if sessions:
            self.list.setCurrentRow(0)

    def _show_details(self, row):
        if row < 0 or row >= len(self._sessions):
            self.details.clear()
            return
        session = self._sessions[row]
        parts = [f'<p><b style="color:#FFB050; font-size:16px;">{html.escape(str(session.get("topic") or ""))}</b></p>']
        summary = session.get("summary")
        if summary:
            parts.append(f'<p>{html.escape(str(summary)).replace(chr(10), "<br>")}</p>')
        findings = data_access.research_findings(session["id"]) or []
        if findings:
            parts.append('<p><b style="color:#E6C9A0;">FINDINGS</b></p><ul>')
            parts.extend(f'<li>{html.escape(str(f["claim"]))}</li>' for f in findings)
            parts.append("</ul>")
        sources = data_access.research_sources(session["id"]) or []
        if sources:
            parts.append('<p><b style="color:#E6C9A0;">SOURCES</b></p><ul>')
            for source in sources:
                label = source.get("title") or source.get("url") or ""
                publisher = f' ({html.escape(str(source["publisher"]))})' if source.get("publisher") else ""
                parts.append(f"<li>{html.escape(str(label))}{publisher}</li>")
            parts.append("</ul>")
        self.details.setHtml("".join(parts))


# ----------------------------------------------------------------------
# Memory
# ----------------------------------------------------------------------

class MemoryPage(QWidget):
    """Read-only view of what NEXUS remembers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 60, 10)
        layout.setSpacing(16)

        head = QHBoxLayout()
        head.addLayout(_page_title("MEMORY", "WHAT NEXUS HAS LEARNED ABOUT YOU"))
        head.addStretch(1)
        self.counts = _small_label("")
        head.addWidget(self.counts, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.search = QLineEdit()
        self.search.setFont(make_font(14))
        self.search.setPlaceholderText("Search memory ...")
        self.search.textChanged.connect(self._filter)
        row.addWidget(self.search, 1)
        refresh = QPushButton("REFRESH")
        refresh.setFont(make_font(12, True, 2.0))
        refresh.setFixedHeight(40)
        refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.list = QListWidget()
        self.list.setFont(make_font(14))
        layout.addWidget(self.list, 1)

        self.note = _small_label("")
        layout.addWidget(self.note)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        facts = data_access.memory_facts()
        totals = data_access.summary_counts()
        self.list.clear()
        self._rows = []

        def shown(value):
            return "--" if value is None else str(value)

        self.counts.setText(
            f'FACTS {shown(totals["facts"])}   |   KNOWLEDGE {shown(totals["knowledge"])}'
            f'   |   RESEARCH {shown(totals["research"])}   |   CONVERSATION LOG {shown(totals["conversations"])}')

        if facts is None:
            self.note.setText("NO MEMORY DATABASE YET")
            return

        for fact in facts:
            text = f'{fact["key"]}\n{fact["value"]}'
            self._rows.append(text.lower())
            self.list.addItem(QListWidgetItem(text))
        self.note.setText(
            f"SHOWING {len(facts)} MOST RECENT FACTS  |  READ-ONLY" if facts
            else "NO FACTS STORED YET")
        self._filter(self.search.text())

    def _filter(self, text):
        needle = str(text or "").strip().lower()
        for index in range(self.list.count()):
            self.list.item(index).setHidden(
                bool(needle) and needle not in self._rows[index])


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------

class SettingsPage(QWidget):
    """Settings that take effect immediately, plus read-only system information."""

    quality_changed = Signal(str)
    companion_changed = Signal(str)
    fullscreen_requested = Signal()

    QUALITY_CHOICES = (
        ("Low  -  lightest on the CPU", "low"),
        ("Balanced", "balanced"),
        ("High  -  sharpest orb", "high"),
    )
    COMPANION_CHOICES = (
        ("Show when the main window is minimised", "minimised"),
        ("Always show", "always"),
        ("Off", "off"),
    )

    def __init__(self, quality="balanced", companion="minimised", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 60, 10)
        layout.setSpacing(18)
        layout.addLayout(_page_title("SETTINGS", "INTERFACE AND SYSTEM"))

        layout.addWidget(_small_label("ORB QUALITY"))
        self.quality = QComboBox()
        self.quality.setFont(make_font(13))
        for text, value in self.QUALITY_CHOICES:
            self.quality.addItem(text, value)
        self.quality.setCurrentIndex(max(0, self.quality.findData(quality)))
        self.quality.currentIndexChanged.connect(
            lambda _i: self.quality_changed.emit(self.quality.currentData()))
        layout.addWidget(self.quality, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(_small_label("FLOATING COMPANION ORB"))
        self.companion = QComboBox()
        self.companion.setFont(make_font(13))
        for text, value in self.COMPANION_CHOICES:
            self.companion.addItem(text, value)
        self.companion.setCurrentIndex(max(0, self.companion.findData(companion)))
        self.companion.currentIndexChanged.connect(
            lambda _i: self.companion_changed.emit(self.companion.currentData()))
        layout.addWidget(self.companion, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(_small_label("WINDOW"))
        self.fullscreen = QPushButton("TOGGLE FULLSCREEN  (F11)")
        self.fullscreen.setFont(make_font(12, True, 2.0))
        self.fullscreen.setFixedHeight(40)
        self.fullscreen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fullscreen.clicked.connect(self.fullscreen_requested.emit)
        layout.addWidget(self.fullscreen, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addSpacing(10)
        layout.addWidget(_small_label("SYSTEM INFORMATION"))
        self.info = ReadoutPanel(("LANGUAGE MODEL", "VOICE MODEL", "DATABASE", "ORB RENDERING"))
        layout.addWidget(self.info)
        layout.addStretch(1)

    def set_info(self, key, text):
        self.info.set_value(key, text)
