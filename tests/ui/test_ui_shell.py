import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.ui.app import NAV_ITEMS, build_window


def test_three_navigation_items_are_visible_in_fixed_order(qapp, tmp_path, monkeypatch):
    # qapp 来自 tests/conftest.py 会话级 fixture；build_window() 复用
    # QApplication.instance()，整个测试会话只存在一个 QApplication。
    # 隔离数据目录：显式注入临时目录，避免走 location.json（正式 UI 启动路径）。
    # Product Collector 集成后 Windows 导航为 4 项；非 Windows 平台商品采集
    # 按平台门控移除（依赖 Playwright + Microsoft Edge，仅 Windows 提供）。
    if sys.platform == "win32":
        expected = [
            "商品采集",
            "新商品测算",
            "历史记录管理",
            "设置",
        ]
    else:
        expected = [
            "新商品测算",
            "历史记录管理",
            "设置",
        ]
    assert NAV_ITEMS == expected
    app, window = build_window(data_dir=tmp_path)
    # 标题来自冻结 main_window.ui 的 windowTitle（运行时为 UU护航 3.0.1），不硬编码旧版本
    assert window.windowTitle() == "UU护航 3.0.1"
    window.close()
    app.processEvents()


def test_new_product_calculation_inputs_default_to_zero():
    """新品测算页演示型默认数字已清零（长宽高/重量），持久设置不受影响。

    直接解析冻结的 main_window.ui：normal/conservative 两档尺寸输入
    默认 value 必须为 0；汇率等持久设置控件不得被清零。
    """
    import re
    from pathlib import Path

    ui_path = (
        Path(__file__).resolve().parents[2]
        / "src" / "profit_accounting_26" / "ui" / "forms" / "main_window.ui"
    )
    lines = ui_path.read_text(encoding="utf-8").splitlines()

    def default_value(name: str) -> str | None:
        """返回指定 QDoubleSpinBox 的 <property name=value> 默认值。"""
        cur = None
        for ln in lines:
            m = re.search(r'<widget class="QDoubleSpinBox" name="([^"]+)"', ln)
            if m:
                cur = m.group(1)
                continue
            if cur == name and '<property name="value">' in ln:
                i = lines.index(ln)
                for j in range(i + 1, min(i + 4, len(lines))):
                    dm = re.search(r"<double>([^<]+)</double>", lines[j])
                    if dm:
                        return dm.group(1)
                return None
        return None

    for name in (
        "spinNormalLengthCm", "spinNormalWidthCm", "spinNormalHeightCm", "spinNormalWeightG",
        "spinConservativeLengthCm", "spinConservativeWidthCm",
        "spinConservativeHeightCm", "spinConservativeWeightG",
    ):
        val = default_value(name)
        assert val is not None, f"{name} 未找到 value 属性"
        assert float(val) == 0.0, f"{name} 默认应为 0，实际 {val}"

    # 持久设置控件不得被清零
    assert float(default_value("spinExchangeRate")) > 0
    assert float(default_value("spinTailFreightRmb")) > 0
    assert float(default_value("spinTailFreightUsd")) > 0
