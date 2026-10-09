"""DNS Tools —— 面向 DNS 运维场景的桌面拨测工具。

PySide6 + dnspython，支持全部公共记录类型、Do53 / DoT / DoH
自定义服务器与反向解析。功能页面按注册表装配，可持续扩展。
"""

from __future__ import annotations

__version__ = "0.3.0"


def main() -> None:
    """控制台入口（pyproject [project.scripts] 指向此处）。"""
    from .app import run

    raise SystemExit(run())
