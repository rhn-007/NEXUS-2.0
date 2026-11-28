"""Launch the NEXUS desktop interface.

Run from the repository root with:
    python -m desktop.main
"""

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from desktop.window import NexusWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NEXUS")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = NexusWindow()
    window.showFullScreen()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
