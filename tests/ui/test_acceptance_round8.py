"""第八轮人工验收修正回归测试（真实控件路径 + MainWindow 集成）。

覆盖三个阻塞问题：
1. 顶部欢迎区：Hi + 蓝色背景用户名 + 中英双行问候真实可见；
2. 尾程 USD → RMB 实时联动（通过真实 spinTailFreightUsd 控件触发）；
3. 标价利率正式写入 main_window.ui（可见性 / 几何位置 / 计算 / 不可编辑）。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QGridLayout,
    QMessageBox,
    QWidget,
)

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.ui.greeting_header import GREETINGS
from profit_accounting_26.ui.binders.calculation_binder import (
    ALL_ENABLED_RULES_ID,
    DRIVER_NO_ACTIVITY_PROFIT,
    DRIVER_NO_ACTIVITY_PRICE,
)


RATE = 7.2


# ── fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def main_window_fixture(qapp, temp_context):
    """构建真实 MainWindow（含 greeting header + 所有页面）。"""
    from profit_accounting_26.ui.main_window import MainWindow
    window = MainWindow(temp_context)
    window.resize(1920, 1080)
    window.show()
    qapp.processEvents()
    yield window
    window.close()
    qapp.processEvents()


# ── 问题 1：顶部欢迎区 ────────────────────────────────────────────

class TestGreetingHeaderLayout:
    """欢迎区：Hi + 蓝色用户名 + 中英双行 真实可见。"""

    def test_subtitle_visible_and_bilingual(self, main_window_fixture):
        window = main_window_fixture
        subtitle = window.findChild(QLabel, "lblGreetingSubtitle")
        title = window.findChild(QLabel, "lblGreetingTitle")
        assert subtitle is not None
        assert subtitle.isVisibleTo(window)
        assert len(subtitle.text().strip()) > 0, "英文副标题为空"
        assert len(title.text().strip()) > 0, "中文标题为空"
        # 两行均不重复显示 Hi 和用户名
        assert not title.text().startswith("Hi"), f"标题含 Hi 前缀: {title.text()}"
        assert not subtitle.text().startswith("Hi"), f"副标题含 Hi 前缀: {subtitle.text()}"

    def test_username_label_visible_and_blue_bg(self, main_window_fixture):
        window = main_window_fixture
        lbl = window.findChild(QLabel, "lblGreetingUserName")
        assert lbl is not None
        assert lbl.isVisibleTo(window)
        # 用户名背景 QSS 已应用（蓝色背景框）
        assert "background:#176ff2" in lbl.styleSheet(), f"用户名 QSS 未包含蓝色背景: {lbl.styleSheet()}"
        assert len(lbl.text()) > 0, "用户名为空"

    def test_eight_char_name_displays_normal(self, main_window_fixture, temp_context):
        window = main_window_fixture
        # 设置 8 字符显示名称
        settings = temp_context.settings_service.load()
        settings["display_name"] = "测长名测名字测"
        temp_context.settings_service.save(settings)
        window.binder.on_settings_saved()
        lbl = window.findChild(QLabel, "lblGreetingUserName")
        assert lbl.text() == "测长名测名字测"

    def test_over_eight_chars_cannot_save(self, qapp, temp_context, monkeypatch):
        """display_name > 8 个可见字符时保存被拒绝。"""
        from profit_accounting_26.ui.pages import SettingsPage
        # 拦截 QMessageBox.warning
        import profit_accounting_26.ui.pages.settings_page as spm
        captured: list = []
        monkeypatch.setattr(
            spm.QMessageBox, "warning",
            staticmethod(lambda *a, **k: captured.append(a)),
        )
        page = SettingsPage(temp_context)
        try:
            page.display_name.setText("超过八个字符的名称")  # 9 可见字符
            page.save_settings()
            assert len(captured) > 0, "应弹出警告框但未拦截到"
            # 设置中 display_name 未被修改
            saved = temp_context.settings_service.load()
            assert saved["display_name"] != "超过八个字符的名称"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_refresh_shows_same_greeting_zh_en(self, main_window_fixture):
        """刷新后中英文来自同一条 greeting。"""
        window = main_window_fixture
        btn = window.findChild(QPushButton, "btnRefreshGreeting")
        title = window.findChild(QLabel, "lblGreetingTitle")
        subtitle = window.findChild(QLabel, "lblGreetingSubtitle")
        # 强制触发一次刷新
        btn.click()
        window.update()
        zh_text = title.text()
        en_text = subtitle.text()
        # 在 GREETINGS 中找到 zh 匹配的条目，en 必须来自同一条目
        pair = next((g for g in GREETINGS if g.zh == zh_text), None)
        assert pair is not None, f"标题文本不在问候库中: {zh_text}"
        assert pair.en == en_text, f"中英文不匹配: zh='{zh_text}', en='{en_text}', expected en='{pair.en}'"

    def test_refresh_button_position_stable(self, main_window_fixture, temp_context, qapp):
        """右上角刷新按钮位置不随用户名变化。"""
        window = main_window_fixture
        btn = window.findChild(QPushButton, "btnRefreshGreeting")
        pos_before = btn.mapTo(window, btn.rect().topLeft())
        # 改为长用户名
        settings = temp_context.settings_service.load()
        settings["display_name"] = "长用户名测试"
        temp_context.settings_service.save(settings)
        window.binder.on_settings_saved()
        window.resize(1920, 1080)
        qapp.processEvents()
        pos_after = btn.mapTo(window, btn.rect().topLeft())
        assert pos_before == pos_after, "刷新按钮位置随用户名变化"


# ── 问题 2：尾程 USD → RMB 实时联动 ──────────────────────────────

class TestTailFeeUsdLiveLink:
    """尾程 USD 实时联动（通过真实 spinTailFreightUsd 控件触发）。"""

    @staticmethod
    def _arm_scenario(page):
        """填充完整计算场景（成本 + 包装 + 货代），使 recalculate 产生实际报价。"""
        page.product_cost.spin.setValue(50.0)
        page.domestic_shipping.spin.setValue(5.0)
        # 当前采用（右卡）是唯一正式包装计算输入
        for key in ("length", "width", "height"):
            page.conservative_fields[key].spin.setValue(20.0)
        page.conservative_fields["weight"].spin.setValue(500.0)

        # 添加两个启用的测试货代
        settings = page.context.settings_service.load()
        if not settings.get("forwarders"):
            shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
            yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
            from dataclasses import asdict
            settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
            settings["selected_forwarder_id"] = shenzhen.id
            page.context.settings_service.save(settings)
            page.refresh_settings()

    def test_usd_edit_updates_rmb_and_full_chain(self, qapp, temp_context):
        """真实控件 setValue(10.00) → RMB=72.00，货代/系统成本/利润全链路更新。"""
        from profit_accounting_26.ui.pages import CalculationPage
        page = CalculationPage(temp_context)
        try:
            self._arm_scenario(page)
            # 确保初始计算
            page.recalculate()
            usd_spin = page._root.findChild(QDoubleSpinBox, "spinTailFreightUsd")
            rmb_spin = page._root.findChild(QDoubleSpinBox, "spinTailFreightRmb")
            assert usd_spin is not None and rmb_spin is not None

            # 记录基准值
            cards_before = {fid: card.rows["total"].text() for fid, card in page.quote_cards.items()}
            total_before = page.system_total.text() if page.system_total else ""
            cost_before = page.profit_binder.txt_cost_rmb.value() if page.profit_binder.txt_cost_rmb else 0.0

            # 通过真实 UI 控件触发（真实 spinTailFreightUsd.setValue 发射 valueChanged）
            usd_spin.setValue(10.0)
            qapp.processEvents()

            # 冻结 RMB 立即变成 72.00
            assert rmb_spin.value() == pytest.approx(72.0, abs=0.01), f"RMB={rmb_spin.value()} != 72.00"

            # 两家货代“头程总费用”不随尾程变化（货代卡只显示头程口径）；尾程金额不显示
            for fid, card in page.quote_cards.items():
                assert card.rows["total"].text() == cards_before.get(fid, ""), \
                    f"货代 {fid} 头程总费用不应随尾程变化: {card.rows['total'].text()}"
                assert card.rows["tail"].text() == ""

            # 系统总成本改变
            assert page.system_total is not None
            assert page.system_total.text() != total_before

            # 利润区计算总成本改变
            assert page.profit_binder.txt_cost_rmb is not None
            assert page.profit_binder.txt_cost_rmb.value() != cost_before
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_usd_19_88_does_not_keep_stale_40(self, qapp, temp_context):
        """USD=19.88 → RMB 不能继续保持旧的 40.00。"""
        from profit_accounting_26.ui.pages import CalculationPage
        page = CalculationPage(temp_context)
        try:
            self._arm_scenario(page)
            page.recalculate()
            usd_spin = page._root.findChild(QDoubleSpinBox, "spinTailFreightUsd")
            rmb_spin = page._root.findChild(QDoubleSpinBox, "spinTailFreightRmb")

            usd_spin.setValue(19.88)
            qapp.processEvents()

            expected = 19.88 * 7.2
            assert rmb_spin.value() == pytest.approx(expected, abs=0.01)
            assert rmb_spin.value() != pytest.approx(40.0, abs=0.01), \
                f"RMB 错误地保持旧值 40.00: 实际 {rmb_spin.value()}"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_exchange_rate_save_resyncs_tail_rmb(self, qapp, temp_context):
        """汇率保存后 refresh_settings 重新同步尾程 RMB=USD×新汇率。"""
        from profit_accounting_26.ui.pages import CalculationPage
        page = CalculationPage(temp_context)
        try:
            self._arm_scenario(page)
            page.recalculate()
            rmb_spin = page._root.findChild(QDoubleSpinBox, "spinTailFreightRmb")

            # 基准：默认汇率 7.2
            base_rmb = page.tail_fee_usd.value() * 7.2
            assert rmb_spin.value() == pytest.approx(base_rmb, abs=0.01)

            # 修改并保存汇率
            settings = temp_context.settings_service.load()
            settings["exchange_rate_usd_to_rmb"] = 6.5
            temp_context.settings_service.save(settings)
            page.refresh_settings()

            expected = page.tail_fee_usd.value() * 6.5
            assert rmb_spin.value() == pytest.approx(expected, abs=0.01), \
                f"汇率变化后 RMB 未同步: {rmb_spin.value()} != {expected}"
        finally:
            page.deleteLater()
            qapp.processEvents()


# ── 问题 3：标价利率正式写入 main_window.ui ──────────────────────

class TestListPriceRateInUi:
    """标价利率 可见性 / 几何位置 / 计算 / 可编辑。"""

    def test_find_children_and_visible(self, main_window_fixture):
        window = main_window_fixture
        # 经测算页根节点查找（macOS 上 _root 被代理进 QGraphicsScene，
        # 不在窗口部件树中；_root 相对查找在所有平台一致有效）
        page_find = window.calculation_page._root.findChild
        title = page_find(QLabel, "lblListPriceProfitRateTitle")
        value = page_find(QDoubleSpinBox, "txtListPriceProfitRate")
        unit = page_find(QLabel, "unit_txtListPriceProfitRate")
        assert title is not None, "lblListPriceProfitRateTitle 未找到"
        assert value is not None, "txtListPriceProfitRate 未找到"
        assert unit is not None and unit.text() == "%", "标价利率 % 单位标签缺失"

        page = window.calculation_page._root
        assert title.isVisibleTo(page), "title 不可见"
        assert value.isVisibleTo(page), "value 不可见"
        assert title.width() > 0, "title width=0"
        assert title.height() > 0, "title height=0"
        assert value.width() > 0, "value width=0"
        assert value.height() > 0, "value height=0"

    def test_position_between_shein_price_and_profit(self, main_window_fixture):
        """标价利率与 SHEIN标价 / 标价利润同属标价区，水平顺序正确。"""
        window = main_window_fixture
        page_find = window.calculation_page._root.findChild
        na_price_w = page_find(QDoubleSpinBox, "txtNoActivityPriceRmb")
        lp_rate_w = page_find(QDoubleSpinBox, "txtListPriceProfitRate")
        na_profit_w = page_find(QDoubleSpinBox, "txtNoActivityProfitRmb")

        assert na_price_w is not None and lp_rate_w is not None and na_profit_w is not None
        # 三个控件均可见且水平顺序：SHEIN标价 < 标价利率 < 标价利润
        page = window.calculation_page._root
        assert na_price_w.isVisibleTo(page)
        assert lp_rate_w.isVisibleTo(page)
        assert na_profit_w.isVisibleTo(page)
        xs = [
            na_price_w.mapTo(page, na_price_w.rect().center()).x(),
            lp_rate_w.mapTo(page, lp_rate_w.rect().center()).x(),
            na_profit_w.mapTo(page, na_profit_w.rect().center()).x(),
        ]
        assert xs[0] < xs[1] < xs[2], f"标价区水平顺序错误: {xs}"

    def test_calculation_shows_correct_percent(self, main_window_fixture):
        """真实计算：cost=100, 标价利润=40.81 → '40.81%'。"""
        window = main_window_fixture
        binder = window.calculation_page.profit_binder
        rate_spin = window.calculation_page._root.findChild(QDoubleSpinBox, "txtListPriceProfitRate")

        binder.set_calculation_cost(100.0)
        # 直接设置无活动利润 = 40.81 触发 driver 反推
        binder._profit_driver = DRIVER_NO_ACTIVITY_PROFIT
        binder.txt_na_profit_rmb.setValue(40.81)
        assert rate_spin.value() == pytest.approx(40.81, abs=0.01), \
            f"标价利率应为 40.81%，实际 {rate_spin.value()}"

    def test_cost_zero_shows_zero(self, main_window_fixture):
        """成本为 0 时安全显示 0，不异常。"""
        window = main_window_fixture
        binder = window.calculation_page.profit_binder
        rate_spin = window.calculation_page._root.findChild(QDoubleSpinBox, "txtListPriceProfitRate")

        binder.set_calculation_cost(0.0)
        binder.txt_na_price_usd.setValue(20.0)
        assert rate_spin.value() == 0.0, f"成本=0 应显示 0，实际 {rate_spin.value()}"

    def test_user_can_edit(self, main_window_fixture):
        """标价利率是可编辑百分比输入框：无上下箭头、2 位小数、可输入负值。"""
        window = main_window_fixture
        value = window.calculation_page._root.findChild(QDoubleSpinBox, "txtListPriceProfitRate")
        assert isinstance(value, QDoubleSpinBox)
        assert not value.isReadOnly()
        assert value.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        assert value.decimals() == 2
        value.setValue(-5.0)
        assert value.value() == -5.0
