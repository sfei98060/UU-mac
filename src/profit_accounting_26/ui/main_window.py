from __future__ import annotations

import sys

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QMainWindow, QWidget

from profit_accounting_26._version import __version__
from profit_accounting_26.application import AppContext
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.binders.main_window_binder import MainWindowBinder
from profit_accounting_26.ui.pages import (
    CalculationPage,
    HistoryPage,
    SettingsPage,
)
from profit_accounting_26.ui.theme import APP_STYLE

# 商品采集依赖 Playwright + Microsoft Edge（channel="msedge"），仅 Windows 提供；
# 其他平台不导入、不初始化采集模块，其依赖缺失不得阻塞应用启动。
COLLECTOR_ENABLED = sys.platform == "win32"
if COLLECTOR_ENABLED:
    from profit_accounting_26.product_collector import ProductCollectionPage

# 保留 NAV_ITEMS 供 app.py 和测试导入（平台门控：非 Windows 无商品采集导航项）
NAV_ITEMS = [
    "商品采集",
    "新商品测算",
    "历史记录管理",
    "设置",
]
if not COLLECTOR_ENABLED:
    NAV_ITEMS = [item for item in NAV_ITEMS if item != "商品采集"]
SUBTITLES = {
    "新商品测算": "图片识别、物流估算与利润测算在同一页面完成",
    "商品采集": "AliExpress Business 商品搜索与候选管理",
    "历史记录管理": "打开记录、查看快照并补充实际反馈",
    "设置": "货代、利润规则、AI识图与物流校准配置",
}


class MainWindow(QMainWindow):
    """主窗口 —— 从 main_window.ui 加载布局，通过 MainWindowBinder 绑定控件。

    架构变更（2.6.1-dual-profit）：
    - .ui 决定布局（侧边栏、导航、顶部问候、汇率、数据目录）；
    - MainWindowBinder 按 objectName 绑定信号与状态同步；
    - 三个页面挂载到 .ui 的 mainStack 页面占位中（Stage 4：导航精简）；
    - 利润双场景由 CalculationBinder 负责（在 CalculationPage 重写后启用）。
    """

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.settings = context.settings_service.load()
        # 启动尺寸与最小尺寸适配当前屏幕：期望启动尺寸 = min(1920×1080 设计尺寸,
        # 当前屏幕可用尺寸)；保持合理 minimumSize 但绝不大于屏幕可用区域，
        # 避免低分辨率下窗口首次启动时按钮/标题栏跑到屏幕之外。不默认强制最大化。
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        avail_w = available.width() if available is not None and available.width() > 0 else 1920
        avail_h = available.height() if available is not None and available.height() > 0 else 1080
        self.setMinimumSize(min(1100, avail_w), min(700, avail_h))
        self.setStyleSheet(APP_STYLE)

        # 从 .ui 加载主窗口布局
        from profit_accounting_26.ui.ui_loader import load_main_window

        loaded_ui = load_main_window()
        # 将 .ui 的 central widget 移植到 self
        loaded_central = loaded_ui.centralWidget()
        loaded_central.setParent(self)
        self.setCentralWidget(loaded_central)
        # 窗口标题使用 .ui 的 windowTitle 作为基础，版本号从 _version 动态注入
        from PySide6.QtWidgets import QLabel as _QLabel
        
        self.setWindowTitle(f"UU护航 {__version__}")
        # 同步更新侧边栏“当前版本”标签（.ui 中为静态占位文字）
        _lbl_ver = self.findChild(_QLabel, "lblCurrentVersion")
        if _lbl_ver is not None:
            _lbl_ver.setText(f"当前版本：{__version__}")
        # 不直接采用 .ui 的 1920×1080 设计尺寸，也不采用其 minimumSize：
        # 两者都可能超过当前屏幕可用区域。启动尺寸按屏幕可用区域裁剪，
        # 页面内部的 QScrollArea 负责窄窗口下的横向/纵向滚动。
        self.resize(min(1920, avail_w), min(1080, avail_h))

        # 设置窗口图标
        self.setWindowIcon(
            QIcon(
                str(
                    resource_path(
                        "src/profit_accounting_26/ui/assets/app_icon_desktop_taskbar.svg"
                    )
                )
            )
        )

        # 创建三个页面（Stage 4：以图搜图/数据导入导出/模型校准反馈已删除）
        self.calculation_page = CalculationPage(context)
        self.history_page = HistoryPage(context)
        self.settings_page = SettingsPage(context)

        # 创建商品采集页（独立模块，不依赖 AppContext）；仅 Windows 启用
        if COLLECTOR_ENABLED:
            self.product_collection_page = ProductCollectionPage()
            # 注入日志目录：<data_dir>/product_collector/
            collector_log_dir = str(context.paths.data_dir / "product_collector")
            self.product_collection_page.set_log_dir(collector_log_dir)
            # 注入 API Profile Store（用于风险检测）
            self.product_collection_page.set_api_profile_store(context.api_profile_store)
        else:
            self.product_collection_page = None

        # 使用 Binder 绑定 .ui 控件
        self.binder = MainWindowBinder(self, context)
        self.binder.calculation_page = self.calculation_page
        self.binder.product_collection_page = self.product_collection_page
        self.binder.settings_page = self.settings_page
        self.binder.history_page = self.history_page
        self.binder.bind()

        # macOS 专属尺寸适配（平台门控）：仅收紧结构性尺寸（侧边栏宽度、内容
        # 边距/间距、中部列最小宽度），不缩放任何控件文字，不改变 Windows 行为。
        if sys.platform == "darwin":
            self._apply_macos_fit()

        # 跨页面信号（保留现有行为）
        self.calculation_page.dirtyChanged.connect(self.binder.set_dirty)
        self.calculation_page.historyEditingChanged.connect(self.binder.set_history_editing)
        self.settings_page.dirtyChanged.connect(self.binder.set_dirty)
        self.settings_page.settingsSaved.connect(self.binder.on_settings_saved)
        self.settings_page.forwardersSaved.connect(self.calculation_page.refresh_settings)
        self.calculation_page.saved.connect(lambda _record_id: self.history_page.refresh())
        self.history_page.recordRequested.connect(self.open_record)

    def switch_page(self, index: int) -> None:
        """委托给 binder。"""
        self.binder.switch_page(index)

    def set_dirty(self, dirty: bool) -> None:
        self.binder.set_dirty(dirty)

    def open_record(self, record_id: str) -> None:
        self.calculation_page.load_record_payload(record_id)
        self.switch_page(NAV_ITEMS.index("新商品测算"))

    def _apply_macos_fit(self) -> None:
        """macOS 尺寸适配（仅结构层，不缩放控件文字）。

        MacBook 屏幕可用区（如 13″ 1470×837）显著小于本页面 1920×1080 的设计验收
        尺寸；在不改变信息层级、不做结构性重排、不缩小文字的前提下，收紧以下结构尺寸
        以降低最大化时的滚动溢出：
        - 侧边栏固定宽度 220 → 184；
        - 计算内容区外边距 16/14 → 10/8，段落间距 10 → 6；
        - 中部三列最小宽度（成本 690→600、物流 350→320、右列 220→200），
          及三张包装卡最小宽度 205 → 186。
        这些只是“最小宽度”收紧，窗口拉宽时各列仍按原 stretch 自动放大。
        """
        from PySide6.QtWidgets import QFrame, QWidget

        sidebar = self.findChild(QFrame, "sidebarFrame")
        if sidebar is not None:
            sidebar.setMinimumWidth(184)
            sidebar.setMaximumWidth(184)

        body = self.findChild(QWidget, "calculationBody")
        if body is not None:
            body.setMinimumWidth(0)
            layout = body.layout()
            if layout is not None:
                layout.setContentsMargins(10, 8, 10, 8)
                layout.setSpacing(6)

        for name, width in (
            ("costPackingSection", 600),
            ("freightSection", 320),
            ("tailSettingsCard", 200),
            ("systemCostSection", 200),
        ):
            widget = self.findChild(QWidget, name)
            if widget is not None:
                widget.setMinimumWidth(width)
        for name in ("bareProductCard", "normalPackageCard", "conservativePackageCard"):
            card = self.findChild(QWidget, name)
            if card is not None:
                card.setMinimumWidth(186)
