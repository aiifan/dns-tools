"""SQLite 本地存储。

集中保存应用配置，替代注册表式的分散存储，单文件可见、可备份：

- ``settings``        单值配置（窗口几何、最后一次拨测参数等）
- ``dns_servers``     DNS 服务器使用历史（去重、最近使用优先、LRU 上限）
- ``lookup_targets`` 拨测目标使用历史（域名 / IP，去重、最近使用优先、LRU 上限）
- ``rdtype_usage``    记录类型使用计数（用于动态组合常用类型集）

默认数据库位置：``%APPDATA%\\dns-tools\\data.db``（Linux 为 ~/.local/share）。
测试或其他环境可通过 ``configure_db_path()`` 在首次 ``get_store()`` 前覆盖路径。
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

#: 服务器历史 LRU 上限
SERVER_HISTORY_LIMIT = 10

#: 拨测目标历史 LRU 上限
TARGET_HISTORY_LIMIT = 10

#: 常用类型集之外，按使用记录最多额外展示的类型数
RDTYPE_EXTRA_LIMIT = 7

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dns_servers (
    server    TEXT PRIMARY KEY,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lookup_targets (
    target    TEXT PRIMARY KEY,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rdtype_usage (
    rdtype    TEXT PRIMARY KEY,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used REAL NOT NULL
);
"""


#: 历史表白名单：表名 -> 值列名（仅供内部拼接 SQL，防注入）
_HISTORY_TABLES = {
    "dns_servers": "server",
    "lookup_targets": "target",
}


def default_db_path() -> Path:
    """返回默认数据库路径（跟随操作系统数据目录约定）。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
    else:
        base = os.environ.get("XDG_DATA_HOME")
    if not base:
        base = str(Path.home() / ".local" / "share")
    return Path(base) / "dns-tools" / "data.db"


class Store:
    """SQLite 存储访问层（调用方均在主线程，内部以锁兜底）。"""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # 单值配置
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # ------------------------------------------------------------------
    # 历史记录（通用：去重 + 计数 + 最近使用置顶 + LRU 裁剪）
    # ------------------------------------------------------------------
    def _touch_history(self, table: str, value: str, limit: int) -> None:
        column = _HISTORY_TABLES[table]
        value = value.strip()
        if not value:
            return
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT INTO {table} ({column}, use_count, last_used) VALUES (?, 1, ?) "
                f"ON CONFLICT({column}) DO UPDATE SET "
                f"use_count = use_count + 1, last_used = excluded.last_used",
                (value, now),
            )
            self._conn.execute(
                f"DELETE FROM {table} WHERE {column} NOT IN ("
                f"  SELECT {column} FROM {table} "
                f"  ORDER BY last_used DESC LIMIT ?)",
                (limit,),
            )

    def _list_recent(self, table: str, limit: int) -> list[str]:
        column = _HISTORY_TABLES[table]
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {column} FROM {table} ORDER BY last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row[column] for row in rows]

    # ------------------------------------------------------------------
    # DNS 服务器历史
    # ------------------------------------------------------------------
    def list_servers(self, limit: int = SERVER_HISTORY_LIMIT) -> list[str]:
        return self._list_recent("dns_servers", limit)

    def add_server(self, server: str) -> None:
        """记录一次服务器使用（去重 + 计数 + 最近使用置顶），并裁剪历史上限。"""
        self._touch_history("dns_servers", server, SERVER_HISTORY_LIMIT)

    def clear_servers(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM dns_servers")

    # ------------------------------------------------------------------
    # 拨测目标历史（域名 / IP）
    # ------------------------------------------------------------------
    def list_targets(self, limit: int = TARGET_HISTORY_LIMIT) -> list[str]:
        return self._list_recent("lookup_targets", limit)

    def add_target(self, target: str) -> None:
        """记录一次拨测目标使用（去重 + 计数 + 最近使用置顶），并裁剪历史上限。"""
        self._touch_history("lookup_targets", target, TARGET_HISTORY_LIMIT)

    # ------------------------------------------------------------------
    # 记录类型使用计数
    # ------------------------------------------------------------------
    def touch_rdtype(self, rdtype: str) -> None:
        """单类型拨测时累计一次使用。"""
        rdtype = rdtype.strip().upper()
        if not rdtype:
            return
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO rdtype_usage (rdtype, use_count, last_used) VALUES (?, 1, ?) "
                "ON CONFLICT(rdtype) DO UPDATE SET "
                "use_count = use_count + 1, last_used = excluded.last_used",
                (rdtype, now),
            )

    def list_used_rdtypes(self, limit: int = RDTYPE_EXTRA_LIMIT) -> list[str]:
        """按使用次数降序（次数相同取最近）返回用过的记录类型。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT rdtype FROM rdtype_usage "
                "ORDER BY use_count DESC, last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row["rdtype"] for row in rows]


# ----------------------------------------------------------------------
# 模块级单例
# ----------------------------------------------------------------------
_store: Store | None = None
_db_path_override: Path | None = None


def configure_db_path(path: str | Path) -> None:
    """覆盖数据库路径。必须在首次调用 get_store() 之前使用（测试隔离用）。"""
    global _db_path_override, _store
    if _store is not None:
        raise RuntimeError("数据库已初始化，无法再修改路径")
    _db_path_override = Path(path)


def get_store() -> Store:
    """获取全局存储实例（惰性创建）。"""
    global _store
    if _store is None:
        _store = Store(_db_path_override or default_db_path())
    return _store


def close_store() -> None:
    """关闭全局存储实例（测试清理用）。"""
    global _store
    if _store is not None:
        _store.close()
        _store = None
