# -*- mode: python ; coding: utf-8 -*-
"""UU护航 macOS PyInstaller spec —— 原生 GUI .app。

生成结构：
    dist/UU护航.app    （Finder 双击直接启动图形界面，不弹出 Terminal）

与 Windows 版（ProfitAccounting26.spec）同一入口、同一资源清单；差异仅：
- 商品采集依赖 Playwright + Edge，仅 Windows 提供 → macOS 排除；
- UU测算 轻量计算器不设独立入口，由主程序侧边栏入口复用
  （quick_calculator_window 模块仍须打包，列在 hiddenimports）。
"""
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "src" / "profit_accounting_26" / "ui" / "app.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        # 配置
        (str(root / "config"), "config"),
        # 校准资源
        (str(root / "calibration" / "logistics_v2"), "calibration/logistics_v2"),
        (str(root / "calibration" / "runtime_safety_baseline"), "calibration/runtime_safety_baseline"),
        # UI forms（主程序 + UU测算共用）
        (str(root / "src" / "profit_accounting_26" / "ui" / "forms"), "profit_accounting_26/ui/forms"),
        # UI assets（图标、SVG、PNG）
        (str(root / "src" / "profit_accounting_26" / "ui" / "assets"), "src/profit_accounting_26/ui/assets"),
    ],
    hiddenimports=["PIL", "profit_accounting_26.ui.quick_calculator_window"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 商品采集（仅 Windows）：macOS 主窗口对其平台门控，运行期不会导入
    excludes=["playwright", "profit_accounting_26.product_collector"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UU护航",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

app = BUNDLE(
    exe,
    a.binaries,
    a.datas,
    name="UU护航.app",
    icon=str(root / "src" / "profit_accounting_26" / "ui" / "assets" / "uu_main_black.icns"),
    bundle_identifier="com.uuescort.profit-accounting",
    info_plist={
        "CFBundleDisplayName": "UU护航",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    },
)
