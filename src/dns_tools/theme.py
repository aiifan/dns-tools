"""界面主题：跟随 Windows 系统明暗模式，统一 QSS 样式。

设计约定：
- 整体为浅灰底 + 白色卡片（暗色为深灰底 + 深色卡片）
- 仅关键操作按钮使用彩色（primaryBtn），其余控件保持中性色
- 需要语义色时通过 objectName 引用（danger / success / muted 等）
"""

from __future__ import annotations

import sys
from pathlib import Path
from string import Template

_LIGHT = {
    "bg": "#f3f5f7",
    "card": "#ffffff",
    "border": "#e1e5ea",
    "text": "#1f2329",
    "muted": "#5b6570",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "select": "#e8f0fe",
    "alt": "#f8fafc",
    "danger": "#d92d20",
    "success": "#1a7f37",
}

_DARK = {
    "bg": "#171a20",
    "card": "#21252d",
    "border": "#323843",
    "text": "#e6e8eb",
    "muted": "#98a2b3",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "select": "#293549",
    "alt": "#1d2129",
    "danger": "#ff7875",
    "success": "#3fb950",
}

_QSS = Template(
    """
* { font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif; }
QMainWindow, QWidget#pageRoot { background-color: ${bg}; }
QWidget { color: ${text}; }
QLabel { background: transparent; }
QLabel[h1="true"] { font-size: 22pt; font-weight: 700; color: ${text}; }
QLabel[h2="true"] { font-size: 12pt; font-weight: 600; color: ${text}; }
QLabel#muted { color: ${muted}; }
QLabel#danger { color: ${danger}; }
QLabel#success { color: ${success}; }
QLabel#code {
    font-family: "Consolas", "Cascadia Mono", monospace;
    background-color: ${bg}; border: 1px solid ${border};
    border-radius: 6px; padding: 8px 10px; color: ${text};
}
QFrame#separator { border: none; border-top: 1px solid ${border}; }

QGroupBox {
    background-color: ${card}; border: 1px solid ${border};
    border-radius: 10px; margin-top: 15px; padding: 8px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 10px; padding: 0 5px;
    color: ${muted}; background-color: ${card};
}

QLineEdit, QComboBox, QSpinBox {
    background-color: ${card}; color: ${text};
    border: 1px solid ${border}; border-radius: 6px;
    padding: 5px 8px; min-height: 20px;
    selection-background-color: ${accent}; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid ${accent}; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: ${muted}; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QLineEdit { border: none; background: transparent; padding: 0; min-height: 0; }
QAbstractItemView {
    background-color: ${card}; color: ${text}; border: 1px solid ${border};
    selection-background-color: ${accent}; selection-color: #ffffff; outline: none;
}
QComboBox QAbstractItemView {
    background-color: ${card}; color: ${text}; border: 1px solid ${border};
    selection-background-color: ${accent}; selection-color: #ffffff; outline: none;
}
QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: none; background: transparent; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: ${select}; }

QPushButton {
    background-color: ${card}; color: ${text};
    border: 1px solid ${border}; border-radius: 6px; padding: 6px 16px;
}
QPushButton:hover { border-color: ${accent}; color: ${accent}; }
QPushButton:pressed { background-color: ${select}; }
QPushButton:disabled { color: ${muted}; border-color: ${border}; }
QPushButton#primaryBtn {
    background-color: ${accent}; color: #ffffff; border: 1px solid ${accent};
    font-weight: 600; padding: 6px 24px;
}
QPushButton#primaryBtn:hover {
    background-color: ${accent_hover}; border-color: ${accent_hover}; color: #ffffff;
}
QPushButton#primaryBtn:disabled {
    background-color: ${border}; border-color: ${border}; color: ${muted};
}

QTabWidget::pane { border: none; background: transparent; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent; color: ${muted};
    padding: 9px 24px; border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: ${text}; }
QTabBar::tab:selected { color: ${accent}; border-bottom: 2px solid ${accent}; font-weight: 600; }

QTreeWidget {
    background-color: ${card}; alternate-background-color: ${alt};
    border: 1px solid ${border}; border-radius: 10px; padding: 4px;
}
QTreeWidget::item { padding: 5px 2px; border: none; }
QTreeWidget::item:hover { background-color: ${select}; }
QTreeWidget::item:selected { background-color: ${select}; color: ${text}; }
QHeaderView::section {
    background-color: ${bg}; color: ${muted}; border: none;
    border-bottom: 1px solid ${border}; padding: 7px 8px; font-weight: 600;
}

QProgressBar { border: none; background: transparent; max-height: 3px; }
QProgressBar::chunk { background-color: ${accent}; }

QToolTip {
    background-color: ${card}; color: ${text};
    border: 1px solid ${border}; padding: 4px 8px;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: ${border}; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: ${muted}; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
)


def is_system_dark() -> bool:
    """检测 Windows 当前是否为暗色应用主题。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except OSError:
        return False


def theme_colors(dark: bool) -> dict[str, str]:
    """返回指定主题的语义色表（danger / success / text / ...）。"""
    return dict(_DARK if dark else _LIGHT)


def apply_theme(app) -> bool:
    """为 QApplication 应用主题样式，返回是否为暗色。"""
    dark = is_system_dark()
    app.setStyle("Fusion")
    app.setStyleSheet(_QSS.substitute(_DARK if dark else _LIGHT))
    return dark


def make_logo_pixmap(size: int = 96):
    """绘制默认 logo（圆角方块 + DNS 字样，图标文件缺失时的回退方案）。"""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2563eb"))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    painter.setPen(QPen(QColor("#ffffff")))
    font = QFont("Segoe UI")
    font.setPixelSize(max(10, int(size * 0.34)))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "DNS")
    painter.end()
    return pixmap


def asset_path(*parts: str) -> Path:
    """assets 资源路径（兼容 PyInstaller onefile 的 _MEIPASS 运行时目录）。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base.joinpath("assets", *parts)


def app_icon_path() -> Path | None:
    """自定义图标文件（assets/icon.ico）路径；不存在时返回 None。"""
    path = asset_path("icon.ico")
    return path if path.is_file() else None


def make_app_icon():
    """应用图标：优先 assets/icon.ico，缺失时回退动态绘制。"""
    from PySide6.QtGui import QIcon

    ico = app_icon_path()
    if ico is not None:
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon
    return QIcon(make_logo_pixmap(256))
