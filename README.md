# dns-tools

面向 DNS 运维场景的桌面拨测工具（Python 3.14 · PySide6 + dnspython）。

## 功能

- **域名拨测**：单域名 / IP 拨测，覆盖全部公共可查询记录类型（A、AAAA、CNAME、MX、TXT、NS、SOA、SRV、CAA、SVCB、HTTPS、DNSKEY、DS、TLSA 等 70+ 种），「全部记录」模式一键并发查询；记录类型下拉默认展示常用类型，输入类型名可模糊查找全部类型
- **反向解析**：输入 IP 地址自动执行 PTR 反查
- **历史记录（搜索引擎式）**：目标与 DNS 服务器输入框点击即弹使用历史，输入时模糊过滤，键盘上下选择回车确认；LRU 上限 10 条自动淘汰
- **自定义 DNS 服务器**：支持 Do53 / DoT / DoH 多协议，可一次填多台对比
- **配置存储**：SQLite 单文件（`%APPDATA%\dns-tools\data.db`）集中保存服务器历史、记录类型使用计数、拨测参数与窗口状态；常用记录列表随使用自动学习
- **结果展示**：按类型分组展示记录值与 TTL，标注 CNAME 链与单类型耗时；双击记录值一键复制
- **其他**：输入防呆校验、界面跟随系统明暗主题

## 快速开始

```bash
uv sync
uv run dns-tools
```

后续计划通过 GitHub Actions + PyInstaller 自动打包 exe。

## 打包（Windows exe）

打包通过 GitHub Actions 完成，**仅手动触发**（push / PR 不触发）：

1. 仓库页面 → **Actions** → **Build Windows EXE**；
2. 点击 **Run workflow** → 选择分支 → **Run workflow**；
3. 运行完成后在该次运行的页面下载 artifact `dns-tools-windows-exe`。

本地等效命令（与 Actions 中完全一致）：

```bash
uv sync
uv run pyinstaller --noconfirm --clean --onefile --windowed --name dns-tools main.py
```

说明：已排除 QtWebEngine / QtPdf / QtQuick / QtQml 等本工具用不到的模块以控制体积；`build/`、`dist/`、`*.spec` 均已在 .gitignore 中忽略。

### 应用图标

将你的 `.ico` 文件复制到 `assets/` 目录并命名为 `icon.ico`（建议包含 16/32/48/256 多尺寸帧），代码、本地打包与 Actions 会自动识别：

- 窗口图标与软件介绍页 logo 优先使用该文件；
- 打包时自动设为 exe 文件图标，并打进包内供运行时加载；
- 文件不存在时回退内置动态绘制图标，程序照常运行，CI 打包也不会失败。

## DNS 服务器格式

| 输入 | 说明 |
| --- | --- |
| `223.5.5.5` | 普通 DNS（UDP+TCP，53 端口） |
| `223.5.5.5:5353` | 指定端口 |
| `[2001:db8::1]:53` | IPv6（带端口必须用方括号；纯 IPv6 地址可直接输入） |
| `tls://223.5.5.5:853` | DoT（TLS） |
| `https://223.5.5.5/dns-query` | DoH（HTTPS） |

留空使用系统默认 DNS；多台服务器用空格 / 逗号分隔。

## 目录结构

```
main.py                     # 启动入口（PyInstaller 打包目标）
assets/icon.ico             # 自选应用图标（可选，缺失时回退动态绘制）
.github/workflows/build.yml # 手动触发的打包 workflow
src/dns_tools/
├── __init__.py      # 入口 main() 与版本号
├── app.py           # QApplication 装配（主题 / 图标）
├── main_window.py   # 主窗口：QTabWidget 按注册表装配页面
├── core.py          # 拨测核心（纯逻辑，无 Qt 依赖，可独立测试）
├── store.py         # SQLite 配置存储（目标 / 服务器历史、类型使用计数、单值配置）
├── theme.py        # 明暗主题检测 + QSS + 应用 logo
└── pages/           # 功能页面
    ├── __init__.py  # 页面注册表 PAGE_CLASSES
    ├── lookup.py    # 域名拨测页
    └── about.py     # 软件介绍页
```

## 新增功能页面

1. 在 `pages/` 下新建页面类（`QWidget` 子类，定义类属性 `TITLE` 作为标签页标题）；
2. 在 `pages/__init__.py` 的 `PAGE_CLASSES` 列表中注册，主窗口自动装配，无需改动其他代码。

## License

MIT

> AI生成