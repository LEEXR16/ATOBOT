"""main.py - ATOBOT desktop GUI. Start it with run_gui.bat."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui import theme
from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ATOBOT")
    app.setStyle("Fusion")                 # consistent base for the dark style sheet
    app.setStyleSheet(theme.QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
