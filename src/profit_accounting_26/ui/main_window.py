from __future__ import annotations

import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QMainWindow, QPushButton, QWidget

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

        # macOS 专属适配（平台门控，不改变 Windows/Linux 行为）：
        # 侧边栏补一个 UU测算 轻量计算器入口（测算页整体等比缩放由
        # CalculationPage 自行完成，见其 _apply_macos_uniform_scaling）。
        if sys.platform == "darwin":
            self._install_quick_calculator_entry()

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

    def _install_quick_calculator_entry(self) -> None:
        """macOS 侧边栏补充“UU测算”入口。

        Windows 上 UU测算 有独立 exe 入口；macOS 只发布主程序 .app，
        故在主程序既有导航区（设置按钮之后）补一个入口按钮，
        直接复用现有轻量计算器窗口，不复制任何业务逻辑。
        """
        settings_btn = self.findChild(QPushButton, "btnNavSettings")
        if settings_btn is None or settings_btn.parentWidget() is None:
            return
        layout = settings_btn.parentWidget().layout()
        if layout is None:
            return
        btn = QPushButton("UU测算")
        btn.setObjectName("btnOpenQuickCalculator")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("打开 UU测算 轻量计算器")
        btn.setIcon(
            QIcon(str(resource_path("src/profit_accounting_26/ui/assets/uu_logo_blue.png")))
        )
        btn.setIconSize(QSize(20, 20))
        # 与导航按钮同一视觉样式（见 MainWindowBinder._bind_navigation），不另做设计
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " text-align: left; padding: 10px 12px 10px 40px;"
            " font-size: 13px; color: #42526a;"
            " border-radius: 6px; }"
        )
        layout.insertWidget(layout.indexOf(settings_btn) + 1, btn)
        btn.clicked.connect(self._open_quick_calculator)
        self._quick_calculator_window = None

    def _open_quick_calculator(self) -> None:
        """打开（或复用已打开的）UU测算 轻量计算器窗口。

        与主程序同进程、同 AppContext/数据目录（QuickCalculatorWindow 的
        设计契约即“与主软件共用同一数据目录/SettingsService/AppContext”）。
        """
        window = getattr(self, "_quick_calculator_window", None)
        if window is None:
            from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow

            window = QuickCalculatorWindow(self.context)
            self._quick_calculator_window = window
        window.show()
        window.raise_()
        window.activateWindow()
