"""Colours, fonts and the global style sheet for the NEXUS desktop interface."""

from PySide6.QtGui import QColor, QFont

# Palette: near-black with amber / gold energy light. No blue or cyan.
BACKGROUND = (4, 6, 9)
AMBER = (255, 163, 58)
GOLD = (255, 205, 120)
HOT = (255, 232, 190)
DIM = (150, 118, 76)
TEXT = (240, 228, 208)
FAINT = (120, 104, 82)


def rgba(rgb, alpha=255):
    return QColor(rgb[0], rgb[1], rgb[2], alpha)


def make_font(px=13, bold=False, spacing=0.0, family="Segoe UI"):
    """Pixel-sized font with optional letter spacing (QSS cannot do spacing)."""
    font = QFont(family)
    font.setPixelSize(px)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def mono_font(px=12, bold=False, spacing=0.0):
    return make_font(px, bold, spacing, family="Consolas")


STYLE_SHEET = """
QWidget { color: #F0E4D0; }
QLabel { background: transparent; }
QToolTip { background: #14100a; color: #FFD9A0; border: 1px solid #6b4a1e; padding: 4px; }

QLineEdit {
    background: rgba(12, 14, 18, 215);
    border: 1px solid rgba(255, 160, 60, 70);
    border-radius: 19px;
    padding: 9px 18px;
    color: #F6EEDF;
    selection-background-color: rgba(255, 150, 40, 120);
}
QLineEdit:focus { border: 1px solid rgba(255, 185, 90, 190); }
QLineEdit:disabled { color: #6b6256; border-color: rgba(255, 255, 255, 28); }

QPushButton {
    background: rgba(255, 150, 50, 20);
    color: #FFC47A;
    border: 1px solid rgba(255, 160, 60, 85);
    border-radius: 17px;
    padding: 8px 18px;
}
QPushButton:hover { background: rgba(255, 150, 50, 48); }
QPushButton:pressed { background: rgba(255, 150, 50, 90); }
QPushButton:disabled {
    color: #6b6256;
    border-color: rgba(255, 255, 255, 28);
    background: transparent;
}

QTextBrowser, QListWidget {
    background: transparent;
    border: none;
    color: #EADFCB;
    selection-background-color: rgba(255, 150, 40, 90);
}
QListWidget::item {
    padding: 9px 6px;
    border-bottom: 1px solid rgba(255, 160, 60, 28);
}
QListWidget::item:selected { background: rgba(255, 150, 40, 42); color: #FFD9A0; }
QListWidget::item:hover { background: rgba(255, 150, 40, 20); }

QComboBox {
    background: rgba(12, 14, 18, 215);
    border: 1px solid rgba(255, 160, 60, 80);
    border-radius: 14px;
    padding: 6px 14px;
    color: #FFD9A0;
    min-width: 190px;
}
QComboBox:hover { border-color: rgba(255, 185, 90, 190); }
QComboBox QAbstractItemView {
    background: #0d0f13;
    color: #FFD9A0;
    border: 1px solid rgba(255, 160, 60, 90);
    selection-background-color: rgba(255, 150, 40, 80);
}

QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical {
    background: rgba(255, 160, 60, 95); border-radius: 4px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
