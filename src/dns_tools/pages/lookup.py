"""域名拨测页：单域名 / IP 的全记录类型拨测。"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import (
    ALL_TYPES_LABEL,
    LookupParams,
    LookupResult,
    common_types,
    parse_server,
    queryable_types,
    run_lookup,
    validate_target,
)
from ..theme import is_system_dark, theme_colors
from ..store import get_store


class _Signals(QObject):
    done = Signal(object)


class _LookupWorker:
    """daemon 线程执行拨测，完成后经 Qt 信号回到主线程（自动队列投递）。"""

    def __init__(self, params: LookupParams, on_done) -> None:
        self._signals = _Signals()
        self._signals.done.connect(on_done)
        self._params = params
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="dns-lookup"
        )

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            result = run_lookup(self._params)
        except Exception as exc:  # 兜底：任何未预见异常都不允许击穿 UI
            result = LookupResult(
                target=self._params.target,
                query_name=self._params.target,
                is_ip=False,
                rdtype_label=self._params.rdtype,
                server_display=self._params.server.strip() or "系统默认 DNS",
                fatal_error=f"内部错误：{exc!r}",
            )
        self._signals.done.emit(result)


class NoWheelComboBox(QComboBox):
    """禁用滚轮切换选项的 QComboBox，避免鼠标滚轮误触改变记录类型。"""

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        event.ignore()


class HistoryLineEdit(QLineEdit):
    """带历史建议的输入框：获得焦点即展示历史（搜索引擎式），输入时模糊过滤。"""

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        super().focusInEvent(event)
        completer = self.completer()
        if completer is None:
            return
        completer.setCompletionPrefix(self.text())
        if completer.completionCount() > 0:
            completer.popup().setMinimumWidth(self.width())
            completer.complete()


class LookupPage(QWidget):
    """域名拨测页面。"""

    TITLE = "域名拨测"

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageRoot")
        self._store = get_store()
        self._worker: _LookupWorker | None = None
        self._build_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # ---- 参数区 ----
        group = QGroupBox("拨测参数")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        align_right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        self._target_model = QStringListModel()
        self.target_edit = HistoryLineEdit()
        self.target_edit.setPlaceholderText("域名或 IP：example.com / 8.8.8.8（点击输入框可查看历史）")
        self.target_edit.setClearButtonEnabled(True)
        self.target_edit.setMinimumWidth(320)
        self.target_edit.setCompleter(self._make_history_completer(self._target_model))

        self.type_combo = NoWheelComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.type_combo.setMaxVisibleItems(20)
        self.type_combo.lineEdit().setPlaceholderText("输入类型名模糊查找")
        self.type_combo.setToolTip(
            "默认列出常用记录类型；直接输入类型名（不区分大小写）可从全部 74 种类型中模糊查找\n"
            "「全部记录」并发查询所有公共记录类型（域名输入时不含 PTR）"
        )
        self.type_combo.addItem(ALL_TYPES_LABEL)
        self.type_combo.addItems(self._current_common_types())
        self.type_combo.setCurrentIndex(0)
        # 模糊查找走 QCompleter 独立建议弹窗：
        # 下拉列表固定为常用集不重建，不抢输入框焦点，文本可自由增删
        type_completer = QCompleter([ALL_TYPES_LABEL] + queryable_types(), self)
        type_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        type_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        type_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.type_combo.setCompleter(type_completer)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(3)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setToolTip("单条查询的超时时间（秒），作用于每一个记录类型查询")

        self._server_model = QStringListModel()
        self.server_edit = HistoryLineEdit()
        self.server_edit.setPlaceholderText(
            "可选：223.5.5.5 · 223.5.5.5:5353 · tls://223.5.5.5 · https://223.5.5.5/dns-query"
        )
        self.server_edit.setToolTip(
            "DNS 服务器，留空使用系统默认。点击输入框可查看最近使用的服务器（自动记录，上限 10 条）。\n"
            "支持多台（空格 / 逗号分隔）：\n"
            "· 223.5.5.5 —— 普通 DNS（UDP+TCP）\n"
            "· 223.5.5.5:5353 —— 指定端口\n"
            "· [2001:db8::1]:53 —— IPv6\n"
            "· tls://223.5.5.5:853 —— DoT\n"
            "· https://223.5.5.5/dns-query —— DoH"
        )
        self.server_edit.setClearButtonEnabled(True)
        self.server_edit.setCompleter(self._make_history_completer(self._server_model))

        self.query_btn = QPushButton("开始拨测")
        self.query_btn.setObjectName("primaryBtn")
        self.query_btn.setDefault(True)

        grid.addWidget(QLabel("目标"), 0, 0, align_right)
        grid.addWidget(self.target_edit, 0, 1, 1, 5)
        grid.addWidget(QLabel("记录类型"), 1, 0, align_right)
        grid.addWidget(self.type_combo, 1, 1)
        grid.addWidget(QLabel("超时（秒）"), 1, 2, align_right)
        grid.addWidget(self.timeout_spin, 1, 3)
        grid.addWidget(QLabel("DNS 服务器"), 2, 0, align_right)
        grid.addWidget(self.server_edit, 2, 1, 1, 3)
        grid.addWidget(self.query_btn, 2, 4, 1, 2)
        for column in range(1, 6):
            grid.setColumnStretch(column, 1)

        # ---- 提示行 ----
        self.hint_label = QLabel("")
        self.hint_label.setObjectName("hint")
        self.hint_label.setWordWrap(True)

        # ---- 结果树 ----
        self.result_tree = QTreeWidget()
        self.result_tree.setColumnCount(3)
        self.result_tree.setHeaderLabels(["记录类型", "TTL", "记录值"])
        self.result_tree.setAlternatingRowColors(True)
        header = self.result_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.result_tree.itemDoubleClicked.connect(self._copy_record)

        # ---- 底部状态行 ----
        bottom = QHBoxLayout()
        self.summary_label = QLabel("输入目标后点击「开始拨测」或按 Enter 开始")
        self.summary_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(160)
        self.progress.hide()
        bottom.addWidget(self.summary_label, 1)
        bottom.addWidget(self.progress)

        root.addWidget(group)
        root.addWidget(self.hint_label)
        root.addWidget(self.result_tree, 1)
        root.addLayout(bottom)

        # ---- 信号 ----
        self.query_btn.clicked.connect(self._on_query)
        self.target_edit.returnPressed.connect(self._on_query)
        self.server_edit.returnPressed.connect(self._on_query)

    # ------------------------------------------------------------------
    # 拨测流程
    # ------------------------------------------------------------------
    def _build_params(self) -> LookupParams | None:
        """校验输入并组装参数；校验失败返回 None 并给出提示。"""
        self._set_hint("")
        try:
            target, is_ip = validate_target(self.target_edit.text())
        except ValueError as exc:
            self._set_hint(str(exc))
            return None

        rdtype = self.type_combo.currentText().strip()
        if not rdtype:
            self._set_hint("请选择或输入记录类型（支持模糊查找）")
            return None
        if rdtype != ALL_TYPES_LABEL:
            matches = [t for t in queryable_types() if t.upper() == rdtype.upper()]
            if not matches:
                self._set_hint(f"未知的记录类型：{rdtype}（可输入类型名模糊查找）")
                return None
            rdtype = matches[0]
            # 回写标准类型名，避免小写等非标准输入流入后续流程与参数记忆
            self.type_combo.setCurrentText(rdtype)

        if is_ip and rdtype not in (ALL_TYPES_LABEL, "PTR"):
            self._set_hint("目标是 IP 地址，仅支持「全部记录」或「PTR」进行反向解析")
            return None
        if not is_ip and rdtype == "PTR":
            self._set_hint("PTR 为反向解析记录，请输入 IP 地址（如 8.8.8.8）")
            return None

        server = self.server_edit.text().strip()
        if server:
            try:
                parse_server(server)
            except ValueError as exc:
                self._set_hint(str(exc))
                return None

        return LookupParams(
            target=target,
            rdtype=rdtype,
            server=server,
            timeout=float(self.timeout_spin.value()),
        )

    def _on_query(self) -> None:
        if self._worker is not None:
            return
        params = self._build_params()
        if params is None:
            return
        self._record_query(params)
        self._set_busy(True)
        self._worker = _LookupWorker(params, self._on_result)
        self._worker.start()

    def _on_result(self, result: LookupResult) -> None:
        self._worker = None
        self._set_busy(False)
        if result.fatal_error:
            self.result_tree.clear()
            self._set_object_name(self.summary_label, "summary")
            self.summary_label.setText("拨测失败")
            self._set_hint("拨测失败：" + result.fatal_error)
            return
        self._set_hint("")
        self._render_result(result)

    # ------------------------------------------------------------------
    # 结果渲染
    # ------------------------------------------------------------------
    def _render_result(self, result: LookupResult) -> None:
        colors = theme_colors(is_system_dark())
        tree = self.result_tree
        tree.clear()

        if result.all_nxdomain:
            warn = QTreeWidgetItem(
                [f"域名不存在（NXDOMAIN）：{result.query_name}", "", ""]
            )
            self._paint_item(warn, colors["danger"], bold=True)
            detail = QTreeWidgetItem(
                ["权威侧确认该域名不存在，全部记录类型均返回 NXDOMAIN", "", ""]
            )
            self._paint_item(detail, colors["danger"])
            warn.addChild(detail)
            tree.addTopLevelItem(warn)
            tree.expandAll()
        else:
            monospace = QFont("Consolas")
            monospace.setStyleHint(QFont.StyleHint.Monospace)
            for item in result.results:
                if item.records:
                    head = QTreeWidgetItem(
                        [
                            item.rdtype,
                            f"{len(item.records)} 条",
                            item.cname_note or "",
                        ]
                    )
                    self._paint_item(head, colors["text"], bold=True)
                    head.setToolTip(0, f"耗时 {item.elapsed_ms:.0f} ms")
                    if item.cname_note:
                        head.setToolTip(2, item.cname_note)
                    for record in item.records:
                        child = QTreeWidgetItem(["", str(item.ttl or "-"), record])
                        child.setFont(2, monospace)
                        child.setToolTip(2, record)
                        head.addChild(child)
                    tree.addTopLevelItem(head)
                    head.setExpanded(True)
                elif item.error:
                    head = QTreeWidgetItem([item.rdtype, "错误", item.error])
                    self._paint_item(head, colors["danger"])
                    head.setToolTip(2, f"{item.error}（耗时 {item.elapsed_ms:.0f} ms）")
                    tree.addTopLevelItem(head)
                    head.setExpanded(True)

        found = len(result.found_results)
        errors = len(result.error_results)
        empty = result.empty_count
        total = len(result.results)
        self._set_object_name(self.summary_label, "summary")
        self.summary_label.setText(
            f"拨测完成：有记录 {found} 种 · 无记录 {empty} 种 · 错误 {errors} 个"
            f"（共 {total} 种类型） · 服务器 {result.server_display} · "
            f"总耗时 {result.elapsed_ms / 1000:.2f} s"
        )

    @staticmethod
    def _paint_item(item: QTreeWidgetItem, color: str, bold: bool = False) -> None:
        brush = QBrush(QColor(color))
        for column in range(3):
            item.setForeground(column, brush)
        if bold:
            font = item.font(0)
            font.setBold(True)
            for column in range(3):
                item.setFont(column, font)

    def _copy_record(self, item: QTreeWidgetItem, column: int) -> None:
        """双击子项复制记录值。"""
        if item.parent() is None:
            return
        value = item.text(2)
        if not value:
            return
        QGuiApplication.clipboard().setText(value)
        self._set_hint(f"已复制到剪贴板：{value[:80]}", "success")
        QTimer.singleShot(3000, lambda: self._set_hint(""))

    # ------------------------------------------------------------------
    # 状态与设置
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self.query_btn.setEnabled(not busy)
        self.query_btn.setText("拨测中…" if busy else "开始拨测")
        if busy:
            self.progress.setRange(0, 0)
            self.progress.show()
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.progress.hide()

    def _set_hint(self, message: str, kind: str = "danger") -> None:
        self.hint_label.setText(message)
        self._set_object_name(self.hint_label, kind if message else "hint")

    @staticmethod
    def _set_object_name(widget: QWidget, name: str) -> None:
        """切换 objectName 后重刷样式（objectName 变更不会自动触发 repolish）。"""
        widget.setObjectName(name)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)

    # ------------------------------------------------------------------
    # 下拉列表与持久化
    # ------------------------------------------------------------------
    @staticmethod
    def _make_history_completer(model: QStringListModel) -> QCompleter:
        """创建历史建议 completer：不区分大小写、包含匹配、独立弹窗。"""
        completer = QCompleter(model)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        return completer

    def _current_common_types(self) -> list[str]:
        """基础常用集 + 数据库使用记录补充的非常用类型。"""
        base = common_types()
        extra = [t for t in self._store.list_used_rdtypes() if t not in base]
        return base + extra

    def _reload_history_models(self) -> None:
        """刷新目标 / 服务器历史建议列表（不影响输入框当前文本）。"""
        self._server_model.setStringList(self._store.list_servers())
        self._target_model.setStringList(self._store.list_targets())

    def _reload_type_items(self) -> None:
        """刷新记录类型常用集（保留当前输入文本）。"""
        current = self.type_combo.currentText()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItems([ALL_TYPES_LABEL] + self._current_common_types())
        self.type_combo.blockSignals(False)
        pos = self.type_combo.findText(current)
        if pos >= 0:
            self.type_combo.setCurrentIndex(pos)
        else:
            self.type_combo.setCurrentText(current)

    def _record_query(self, params: LookupParams) -> None:
        """记录本次拨测上下文：目标与服务器历史 + 单值参数 + 单类型使用计数。"""
        store = self._store
        store.set_setting("last_target", params.target)
        store.set_setting("last_server", params.server)
        store.set_setting("last_rdtype", params.rdtype)
        store.set_setting("last_timeout", str(params.timeout))
        store.add_target(params.target)
        if params.server:
            store.add_server(params.server)
        self._reload_history_models()
        if params.rdtype != ALL_TYPES_LABEL:
            store.touch_rdtype(params.rdtype)
            self._reload_type_items()

    def _load_settings(self) -> None:
        store = self._store
        target = store.get_setting("last_target")
        if target:
            self.target_edit.setText(target)
        rdtype = store.get_setting("last_rdtype", ALL_TYPES_LABEL) or ALL_TYPES_LABEL
        index = self.type_combo.findText(rdtype)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        else:
            # 上次保存的是非常用类型（如 NAPTR），直接作为输入文本恢复
            self.type_combo.setCurrentText(rdtype)
        try:
            timeout = float(store.get_setting("last_timeout") or "3")
            if 1 <= timeout <= 30:
                self.timeout_spin.setValue(int(timeout))
        except (TypeError, ValueError):
            pass
        self._reload_history_models()
        last_server = store.get_setting("last_server")
        if last_server:
            self.server_edit.setText(last_server)
