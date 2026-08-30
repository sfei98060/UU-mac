#!/bin/bash
# UU护航 macOS 构建脚本 —— 生成原生 GUI .app（Finder 双击直接启动，不弹 Terminal）。
# 流程对齐 build_windows.bat：定位/创建虚拟环境 → 安装构建依赖 → PyInstaller。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$ROOT"

VPY="$ROOT/.venv/bin/python"

# ---------------------------------------------------------------------------
# 定位 Python 3.11（pyproject 约定 >=3.11,<3.12）；优先复用项目本地 .venv
# ---------------------------------------------------------------------------
if [ ! -x "$VPY" ]; then
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
        echo "未找到 Python 3.11（brew install python@3.11 后重试）" >&2
        exit 1
    fi
    echo "首次构建：创建项目本地虚拟环境 .venv ..."
    "$PY311" -m venv "$ROOT/.venv"
fi

if ! "$VPY" -c "import PySide6, profit_accounting_26" >/dev/null 2>&1; then
    echo "安装运行依赖（PySide6 / openpyxl / Pillow）..."
    "$VPY" -m pip install --upgrade pip >/dev/null
    "$VPY" -m pip install "PySide6>=6.7,<7" "openpyxl>=3.1,<4" "Pillow>=10.0,<12"
    "$VPY" -m pip install -e . --no-deps
fi

if ! "$VPY" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "安装构建依赖（PyInstaller）..."
    "$VPY" -m pip install -r requirements-build.txt
fi

# ---------------------------------------------------------------------------
# PyInstaller 打包：原生 .app（console=False 的 BUNDLE，无 Terminal）
# ---------------------------------------------------------------------------
"$ROOT/.venv/bin/pyinstaller" --noconfirm --clean ProfitAccounting26_macOS.spec

echo "构建完成：$ROOT/dist/UU护航.app"
