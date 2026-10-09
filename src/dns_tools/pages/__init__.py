"""功能页面注册表。

新增页面步骤：
1. 在本目录新建页面模块，页面类为 QWidget 子类并定义类属性 ``TITLE``（标签页标题）；
2. 将页面类追加到下方 ``PAGE_CLASSES`` 列表，主窗口会自动装配为标签页。
"""

from __future__ import annotations

from .about import AboutPage
from .lookup import LookupPage

#: 标签页顺序即列表顺序；后续功能页面（批量拨测 / 历史记录等）在此追加
PAGE_CLASSES = [LookupPage, AboutPage]

__all__ = ["PAGE_CLASSES", "LookupPage", "AboutPage"]
