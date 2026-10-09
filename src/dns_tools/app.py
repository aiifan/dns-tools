"""应用装配：QApplication、主题与主窗口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .main_window import MainWindow
from .theme import apply_theme, make_app_icon


def run() -> int:
    """创建并运行应用，返回退出码。"""
    app = QApplication(sys.argv)
    app.setApplicationName("DNS Tools")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("aiifan")
    app.setWindowIcon(make_app_icon())

    apply_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()
