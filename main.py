"""应用入口：PyInstaller 打包目标 & 本地启动脚本。

用法：
    uv run python main.py      # 本地启动
    打包见 .github/workflows/build.yml（仅手动触发）
"""

from dns_tools import main

if __name__ == "__main__":
    main()
