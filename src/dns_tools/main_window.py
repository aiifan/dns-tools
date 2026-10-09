"""主窗口：QTabWidget 按页面注册表装配标签页。"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtWidgets import QMainWindow, QTabWidget

from . import __version__
from .pages import PAGE_CLASSES
from .store import get_store


class MainWindow(QMainWindow):
    """主窗口。

    页面来自 ``dns_tools.pages.PAGE_CLASSES`` 注册表，
    新增功能页面只需注册，无需改动本文件。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"DNS Tools v{__version__}")
        self.setMinimumSize(QSize(920, 600))
        self.resize(QSize(1080, 720))

        self._store = get_store()
        self._restore_geometry()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        for page_cls in PAGE_CLASSES:
            self.tabs.addTab(page_cls(), page_cls.TITLE)

    def _restore_geometry(self) -> None:
        data = self._store.get_setting("window_geometry")
        if data:
            try:
                self.restoreGeometry(QByteArray.fromBase64(data.encode("ascii")))
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        geometry = self.saveGeometry().toBase64().data().decode("ascii")
        self._store.set_setting("window_geometry", geometry)
        super().closeEvent(event)
