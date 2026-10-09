"""软件介绍页：应用信息、功能清单、技术栈与扩展说明。"""

from __future__ import annotations

import importlib.metadata
import platform

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..theme import make_app_icon

_REPO_URL = "https://github.com/aiifan/dns-tools"


def _dist_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "未安装"


class AboutPage(QWidget):
    """软件介绍页面。"""

    TITLE = "软件介绍"

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageRoot")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)

        # ---- 头部 ----
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(QSize(72, 72)))
        header.addWidget(logo)
        header.addSpacing(14)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("DNS Tools")
        title.setProperty("h1", True)
        subtitle = QLabel(f"v{__version__} · DNS 运维拨测工具 · MIT License")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        header_box = QWidget()
        header_box.setLayout(header)
        layout.addWidget(header_box)
        layout.addWidget(self._separator())

        self._add_text_section(
            layout,
            "简介",
            "DNS Tools 是一款面向 DNS 运维场景的桌面拨测工具，基于 PySide6 与 dnspython 构建，"
            "用于对域名 / IP 进行快速解析验证与故障定位。界面跟随系统明暗主题，"
            "拨测参数自动记忆，架构采用页面注册机制，功能页面可持续扩展。",
        )

        self._add_rich_section(
            layout,
            "当前功能",
            "<ul style='margin:0; padding-left:18px;'>"
            "<li><b>域名拨测</b>：单域名 / IP 拨测，覆盖全部公共可查询记录类型"
            "（A、AAAA、CNAME、MX、TXT、NS、SOA、SRV、CAA、SVCB、HTTPS、DNSKEY、DS 等 70+ 种）</li>"
            "<li><b>全部记录模式</b>：一键并发查询所有记录类型，自动汇总「有记录 / 无记录 / 错误」</li>"
            "<li><b>反向解析</b>：输入 IP 地址自动执行 PTR 反查</li>"
            "<li><b>多协议服务器</b>：Do53（IP / IP:端口）、DoT（tls://）、DoH（https://），"
            "支持一次填写多台对比</li>"
            "<li><b>结果操作</b>：双击记录值一键复制，每类记录展示 TTL、耗时与 CNAME 链</li>"
            "<li><b>防呆校验</b>：域名 / IP / 服务器格式校验，错误输入即时提示</li>"
            "<li><b>配置存储</b>：SQLite 单文件（%APPDATA%\\dns-tools\\data.db）——"
            "拨测目标与 DNS 服务器使用历史（点击输入框即可回看，输入时模糊过滤，LRU 上限 10 条）、"
            "记录类型使用计数（常用列表自动学习）、拨测参数与窗口状态记忆</li>"
            "</ul>",
        )

        self._add_text_section(
            layout,
            "技术栈",
            f"Python {platform.python_version()} · PySide6 {_dist_version('pyside6')} · "
            f"dnspython {_dist_version('dnspython')}（含 DoH 扩展）",
        )

        run_code = QLabel("uv sync\nuv run dns-tools")
        run_code.setObjectName("code")
        self._add_heading(layout, "运行方式")
        layout.addWidget(run_code)

        self._add_rich_section(
            layout,
            "路线图（规划中）",
            "<ul style='margin:0; padding-left:18px;'>"
            "<li>批量域名拨测 / 定时拨测</li>"
            "<li>拨测历史与结果导出（CSV / Excel）</li>"
            "<li>DNSSEC 验证、UDP / TCP 指定、EDNS 选项</li>"
            "<li>DNS 服务器批量对比、域名健康检查</li>"
            "</ul>",
        )

        self._add_text_section(
            layout,
            "扩展开发",
            "主窗口按 dns_tools/pages/__init__.py 中的 PAGE_CLASSES 注册表装配标签页："
            "在 pages/ 目录新建页面类（QWidget 子类并定义 TITLE 属性），注册一行即可挂载新页，"
            "无需改动主窗口代码。",
        )

        self._add_heading(layout, "开源信息")
        repo = QLabel(f'仓库：<a href="{_REPO_URL}">github.com/aiifan/dns-tools</a>')
        repo.setOpenExternalLinks(True)
        layout.addWidget(repo)
        license_note = QLabel("许可协议：MIT License · © 2026 aiifan")
        license_note.setObjectName("muted")
        layout.addWidget(license_note)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # 构建辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName("separator")
        line.setFixedHeight(1)
        return line

    @staticmethod
    def _add_heading(layout: QVBoxLayout, text: str) -> None:
        heading = QLabel(text)
        heading.setProperty("h2", True)
        layout.addWidget(heading)

    def _add_text_section(self, layout: QVBoxLayout, title: str, body: str) -> None:
        self._add_heading(layout, title)
        label = QLabel(body)
        label.setWordWrap(True)
        layout.addWidget(label)

    def _add_rich_section(self, layout: QVBoxLayout, title: str, html: str) -> None:
        self._add_heading(layout, title)
        label = QLabel(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)
