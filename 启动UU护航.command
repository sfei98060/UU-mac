#!/bin/bash
# UU护航 macOS 启动器 —— Finder 双击即可运行。
# - 自动定位本仓库根目录（不依赖当前工作目录）；
# - 自动使用项目本地 .venv（不存在时自动创建并安装运行依赖）；
# - 启动真实应用入口 profit_accounting_26.ui.app；
# - 路径含空格/中文安全。
set -euo pipefail

# 解析仓库根目录（本脚本所在目录），处理空格与中文
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$ROOT"

# ---------------------------------------------------------------------------
# 定位 Python 3.11（pyproject 约定 >=3.11,<3.12）
# ---------------------------------------------------------------------------
PY311=""
for cand in \
    "$(command -v python3.11 || true)" \
    "/opt/homebrew/bin/python3.11" \
    "/usr/local/bin/python3.11"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then
        PY311="$cand"
        break
    fi
done

if [ -z "$PY311" ]; then
    echo "=========================================="
    echo " 未找到 Python 3.11。"
    echo " 请先安装（例如：brew install python@3.11）,"
    echo " 然后重新双击本启动器。"
    echo "=========================================="
    echo
    echo "按回车键关闭本窗口..."
    read -r _
    exit 1
fi

VENV="$ROOT/.venv"
VPY="$VENV/bin/python"

# ---------------------------------------------------------------------------
# 首次运行：创建项目本地虚拟环境并安装 macOS 运行所需依赖
# 依赖以“保留的 macOS 运行时”为限；商品采集的 Playwright/Edge 在 macOS 不安装。
# ---------------------------------------------------------------------------
if [ ! -x "$VPY" ]; then
    echo "首次运行：正在创建项目本地虚拟环境 .venv ..."
    "$PY311" -m venv "$VENV"
fi

if ! "$VPY" -c "import PySide6, profit_accounting_26" >/dev/null 2>&1; then
    echo "首次运行：正在安装运行依赖（PySide6 / openpyxl / Pillow）..."
    "$VPY" -m pip install --upgrade pip >/dev/null
    "$VPY" -m pip install "PySide6>=6.7,<7" "openpyxl>=3.1,<4" "Pillow>=10.0,<12"
    # 以可编辑方式挂载本包（--no-deps：避免拉入仅 Windows 需要的 playwright）
    "$VPY" -m pip install -e . --no-deps
fi

# ---------------------------------------------------------------------------
# 启动真实应用入口
# ---------------------------------------------------------------------------
export QT_ENABLE_HIGHDPI_SCALING=1
exec "$VPY" -m profit_accounting_26.ui.app
