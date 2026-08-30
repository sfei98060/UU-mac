"""真实主窗口 / 设置页集成测试。

覆盖验收要求：
- 实际 MainWindow 不嵌套旧 CalculationPage（关键 objectName 全窗口唯一）；
- 实际设置页不嵌套旧 SettingsPage；
- 动态 API Profile 数量不受 UI 三行限制；
- 动态货代卡片按启用货代数量生成，Designer 预览卡已清除。
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QTableWidget,
    QWidget,
)

from profit_accounting_26.application import ApiProfile, AppContext, SettingsService

# qapp 由 tests/conftest.py 的会话级 fixture 提供（整个测试会话共用一个
# QApplication）。禁止在本文件内创建 QApplication——反复创建/销毁
# QApplication 会在 Linux offscreen 平台下导致段错误。


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


class TestNoNestedPages:
    """实际 MainWindow / 设置页不得嵌套旧版重复页面。"""

    def _build(self, context):
        from profit_accounting_26.ui.main_window import MainWindow

        return MainWindow(context)

    def test_actual_main_window_does_not_nest_old_calculation_page(self, qapp, temp_context):
        window = self._build(temp_context)
        try:
            def count(cls, name):
                n = len(window.findChildren(cls, name))
                if sys.platform == "darwin":
                    # macOS 容器层等比缩放：测算页根节点被代理进
                    # QGraphicsScene，不在窗口部件树中；其内部控件经
                    # _root 计数，全窗口唯一性不变式保持不变。
                    root = window.calculation_page._root
                    n += len(root.findChildren(cls, name))
                    # findChildren 不含自身，而 _root 本身就是 pageCalculation
                    if isinstance(root, cls) and root.objectName() == name:
                        n += 1
                return n

            # 主窗口结构唯一
            assert count(QStackedWidget, "mainStack") == 1
            assert count(QWidget, "pageCalculation") == 1
            # 加载的 .ui 外壳 QMainWindow 不得作为重复窗口嵌入
            assert count(QMainWindow, "MainWindow") == 0
            # 关键利润区/顶部控件全窗口只出现一次（若嵌套旧页面会重复）
            for cls, name in (
                (QDoubleSpinBox, "txtSheinPriceUsd"),
                (QDoubleSpinBox, "txtNoActivityPriceUsd"),
                (QDoubleSpinBox, "txtActivityProfitRmb"),
                (QDoubleSpinBox, "spinExchangeRate"),
                (QLabel, "lblGreetingTitle"),
            ):
                assert count(cls, name) == 1, f"{name} 出现 {count(cls, name)} 次，应为 1 次"
            # 测算页根节点就是 .ui 的 pageCalculation，而非旧程序化重复布局
            assert window.calculation_page._root.objectName() == "pageCalculation"
        finally:
            window.close()
            qapp.processEvents()

    def test_actual_settings_page_does_not_nest_old_settings_page(self, qapp, temp_context):
        window = self._build(temp_context)
        try:
            def count(cls, name):
                return len(window.findChildren(cls, name))

            assert count(QWidget, "SettingsPage") == 1
            assert count(QLineEdit, "txtDisplayName") == 1
            assert count(QComboBox, "cmbApiProfileSelect") == 1
            assert count(QTableWidget, "tableForwarders") == 1
            assert count(QListWidget, "listProfitRules") == 1
            assert window.settings_page._root.objectName() == "SettingsPage"
        finally:
            window.close()
            qapp.processEvents()


class TestDynamicRegions:
    """动态 API Profile 与动态货代。"""

    def test_dynamic_api_profiles_are_not_limited_to_three_rows(self, qapp, temp_context):
        from profit_accounting_26.ui.pages import SettingsPage

        store = temp_context.api_profile_store
        profile_ids = []
        for index in range(4):
            profile = ApiProfile.create(
                display_name=f"测试配置{index + 1}",
                provider="OpenAI",
                api_url=f"https://api{index}.test/v1/chat/completions",
                model_name=f"model-{index}",
            )
            store.save_profile(profile, f"key-{index}")
            profile_ids.append(profile.profile_id)

        page = SettingsPage(temp_context)
        try:
            combo = page.api_profile_select
            listed = {combo.itemData(i) for i in range(combo.count()) if combo.itemData(i)}
            assert set(profile_ids) <= listed
            assert combo.count() == len(profile_ids) + 1  # 含“选择已有配置”
            # 视觉/局部重估绑定下拉同样列出全部 Profile
            assert page.visual_binding.count() == len(profile_ids) + 1
            assert page.local_binding.count() == len(profile_ids) + 1
            # Designer 预览测试按钮运行时隐藏；删除按钮可见
            widget = page._root.findChild(QWidget, "btnTestApi1")
            assert widget is not None
            assert not widget.isVisibleTo(page._root)
            del_widget = page._root.findChild(QWidget, "btnDeleteApi1")
            assert del_widget is not None
            assert del_widget.isVisibleTo(page._root)  # 现为删除配置按钮
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_dynamic_forwarder_cards_follow_enabled_forwarders(self, qapp, temp_context):
        from profit_accounting_26.ui.pages import CalculationPage

        settings = temp_context.settings_service.load()
        third = SettingsService.new_forwarder("第三家货代", 73.0, 8.0, 7000.0)
        settings["forwarders"].append(asdict(third))
        temp_context.settings_service.save(settings)

        page = CalculationPage(temp_context)
        try:
            # 三家启用货代 → 三张动态报价卡（不写死两家）
            assert len(page.quote_cards) == 3
            assert third.id in page.quote_cards
            # Designer 预览卡已清除
            assert page._root.findChild(QWidget, "forwarderCardShenzhen") is None
            assert page._root.findChild(QWidget, "forwarderCardYiwu") is None
            # 归档第三家 → 刷新后仅剩两张卡
            settings = temp_context.settings_service.load()
            for item in settings["forwarders"]:
                if item["id"] == third.id:
                    item["archived"] = True
                    item["enabled"] = False
            temp_context.settings_service.save(settings)
            page.refresh_settings()
            assert len(page.quote_cards) == 2
        finally:
            page.deleteLater()
            qapp.processEvents()
