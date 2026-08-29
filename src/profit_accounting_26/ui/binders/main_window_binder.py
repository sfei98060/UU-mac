"""主窗口 Binder。

在 ``MainWindow`` 加载 ``main_window.ui`` 后，按 ``objectName`` 绑定：
- 顶部问候（btnRefreshGreeting / lblGreetingTitle / lblGreetingSubtitle）
- 左侧三导航（btnNav*）与 mainStack 页面切换（Stage 4：导航精简）
- 数据目录（lblDataDirectoryPath / btnChangeDataDirectory）
- 汇率（spinExchangeRate / btnRefreshExchangeRate / lblExchangeRateUpdated）
- 保存状态（lblSaveStatus）

页面挂载策略：
- pageCalculation：使用 .ui 自带的计算页布局（由 CalculationBinder 绑定）；
- pageSettingsHost：将 settings_page.ui 挂载进 pageSettingsHostLayout；
- pageHistory：清除 Designer 占位提示后挂载现有页面 QWidget。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.greeting_header import GreetingHeaderController
from profit_accounting_26.ui.ui_loader import load_settings_page


# 导航按钮 objectName、页面 objectName、显示文字、SVG 图标文件名（顺序固定）
_NAV_ICON_DIR = "src/profit_accounting_26/ui/assets"
_NAV_BINDINGS_ALL: list[tuple[str, str, str, str]] = [
    ("btnNavProductCollection", "pageProductCollection", "商品采集", "nav_data_import_export.svg"),
    ("btnNavCalculation", "pageCalculation", "新商品测算", "nav_model_calibration_feedback.svg"),
    ("btnNavHistory", "pageHistory", "历史记录管理", "nav_history_records.svg"),
    ("btnNavSettings", "pageSettingsHost", "设置", "nav_settings.svg"),
]
# 平台门控（与 main_window.COLLECTOR_ENABLED 保持一致）：非 Windows 无商品采集导航项，
# 保证 NAV_BINDINGS 与 main_window.NAV_ITEMS 平行、索引一致。
_COLLECTOR_ENABLED = sys.platform == "win32"
NAV_BINDINGS: list[tuple[str, str, str, str]] = [
    binding
    for binding in _NAV_BINDINGS_ALL
    if _COLLECTOR_ENABLED or binding[1] != "pageProductCollection"
]


class _PathElideFilter(QObject):
    """事件过滤器：让 QLabel 单行显示路径，超长时中间截断（ElideMiddle）。

    拦截 paintEvent 用 QFontMetrics.elidedText 绘制；不修改布局结构。
    """

    def eventFilter(self, obj, event):
        if event.type() == event.Type.Paint and isinstance(obj, QLabel):
            fm = QFontMetrics(obj.font())
            elided = fm.elidedText(obj.text(), Qt.TextElideMode.ElideMiddle, obj.width())
            if elided != obj.text():
                painter = QPainter(obj)
                painter.setPen(obj.palette().text().color())
                painter.drawText(0, (obj.height() + fm.ascent() - fm.descent()) // 2, elided)
                return True
        return False


class MainWindowBinder:
    """绑定已加载的 main_window.ui 上的所有控件。"""

    settingsSaved = Signal()
    forwardersSaved = Signal()

    def __init__(self, window: QMainWindow, context: AppContext) -> None:
        self.window = window
        self.context = context
        self.settings = context.settings_service.load()
        self.greeting_header: GreetingHeaderController | None = None
        self._nav_buttons: list[QPushButton] = []
        self._page_widgets: dict[str, QWidget] = {}
        # 外部设置：由 MainWindow 注入实际页面 widget
        self.calculation_page = None
        self.product_collection_page = None
        self.settings_page = None
        self.history_page = None

    # ------------------------------------------------------------------
    # 绑定入口
    # ------------------------------------------------------------------

    def bind(self) -> None:
        """执行所有绑定。在 MainWindow 完成页面注入后调用。"""
        self._bind_greeting()
        self._bind_navigation()
        self._bind_data_directory()
        self._bind_exchange_rate()
        self._mount_pages()
        # 必须在 _mount_pages 之后绑定保存状态：
        # _mount_pages 会删除 main_window.ui 的 pageCalculation 占位（含旧 lblSaveStatus），
        # 替换为 CalculationPage（从同一 .ui 重新加载，含新的 lblSaveStatus）。
        # 如果提前绑定，self.lbl_save_status 会指向已被 deleteLater 的旧控件。
        self._bind_save_status()
        # 默认切换到测算页（Stage 4：新导航顺序下为 index 0）
        self.switch_page(0)

    # ------------------------------------------------------------------
    # 顶部问候
    # ------------------------------------------------------------------

    def _bind_greeting(self) -> None:
        btn_refresh = self.window.findChild(QPushButton, "btnRefreshGreeting")
        lbl_title = self.window.findChild(QLabel, "lblGreetingTitle")
        lbl_subtitle = self.window.findChild(QLabel, "lblGreetingSubtitle")
        lbl_user_name = self.window.findChild(QLabel, "lblGreetingUserName")

        self.greeting_header = GreetingHeaderController(
            lambda: str(self.settings.get("display_name") or "用户"), self.window
        )
        if btn_refresh and lbl_title and lbl_subtitle:
            self.greeting_header.bind_existing_header(
                title_label=lbl_title,
                subtitle_label=lbl_subtitle,
                shuffle_button=btn_refresh,
                user_name_label=lbl_user_name,
            )

    # ------------------------------------------------------------------
    # 导航与页面
    # ------------------------------------------------------------------

    def _bind_navigation(self) -> None:
        self._nav_buttons = []
        # 导航按钮使用 QPushButton 原生 icon + text 布局，
        # 通过 CSS padding-left 实现图标列与文字列的固定对齐。
        _nav_base_style = (
            "QPushButton { background: transparent; border: none;"
            " text-align: left; padding: 10px 12px 10px 40px;"
            " font-size: 13px; color: #42526a;"
            " border-radius: 6px; }"
        )
        for btn_name, _page_name, label, icon_file in NAV_BINDINGS:
            btn = self.window.findChild(QPushButton, btn_name)
            if not btn:
                continue
            btn.setCheckable(True)
            btn.setText(label)
            # 设置 SVG 图标，固定 20×20 渲染尺寸
            icon_path = str(resource_path(f"{_NAV_ICON_DIR}/{icon_file}"))
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(20, 20))
            btn.setStyleSheet(_nav_base_style)
            # 索引与连接
            idx = len(self._nav_buttons)
            btn.clicked.connect(lambda _checked, i=idx: self.switch_page(i))
            self._nav_buttons.append(btn)
        # 采集模块未启用（非 Windows）时，隐藏 .ui 中仍存在的商品采集导航按钮
        if not _COLLECTOR_ENABLED:
            collector_btn = self.window.findChild(QPushButton, "btnNavProductCollection")
            if collector_btn:
                collector_btn.setVisible(False)
        # 初始化第一个按钮为选中态
        if self._nav_buttons:
            self._update_nav_styles(0)

    def _update_nav_styles(self, active_index: int) -> None:
        """更新导航按钮的选中/未选中样式。"""
        _inactive = (
            "QPushButton { background: transparent; border: none;"
            " text-align: left; padding: 10px 12px 10px 40px;"
            " font-size: 13px; color: #42526a;"
            " border-radius: 6px; }"
        )
        _active = (
            "QPushButton { background: #eaf2ff; border: none;"
            " text-align: left; padding: 10px 12px 10px 40px;"
            " font-size: 13px; color: #176ff2; font-weight: 600;"
            " border-radius: 6px; }"
        )
        for idx, btn in enumerate(self._nav_buttons):
            btn.setStyleSheet(_active if idx == active_index else _inactive)

    def switch_page(self, index: int) -> None:
        """切换到第 index 个导航页（索引按 NAV_BINDINGS 显示顺序）。

        mainStack 物理顺序与导航显示顺序可能不同（pageCalculation 占位在挂载时
        被替换为真实 CalculationPage），因此按导航项对应的页面实际索引切换。
        """
        stack = self.window.findChild(QStackedWidget, "mainStack")
        if not stack or not (0 <= index < len(NAV_BINDINGS)):
            return
        _btn_name, page_name, label, _icon_file = NAV_BINDINGS[index]
        real_index = self._page_stack_index(stack, page_name)
        if real_index < 0:
            real_index = index
        stack.setCurrentIndex(real_index)
        for idx, btn in enumerate(self._nav_buttons):
            btn.setChecked(idx == index)
        self._update_nav_styles(index)
        # 触发页面刷新
        if label == "历史记录管理" and self.history_page:
            self.history_page.refresh()
        elif label == "设置" and self.settings_page and not getattr(self.settings_page, "dirty", False):
            if hasattr(self.settings_page, "load_settings"):
                self.settings_page.load_settings()

    def _page_stack_index(self, stack: QStackedWidget, page_name: str) -> int:
        """导航项对应页面在 mainStack 中的实际索引。

        pageCalculation 占位在挂载时被替换为真实 CalculationPage；
        其余页面仍以占位 widget 形式挂在 stack 中。
        """
        if page_name == "pageCalculation" and self.calculation_page is not None:
            idx = stack.indexOf(self.calculation_page)
            if idx >= 0:
                return idx
        placeholder = self.window.findChild(QWidget, page_name)
        if placeholder is not None:
            return stack.indexOf(placeholder)
        return -1

    def _mount_pages(self) -> None:
        """将现有页面 widget 挂载到 .ui 的页面占位中。"""
        page_map = {
            "pageCalculation": self.calculation_page,
            "pageProductCollection": self.product_collection_page,
            "pageHistory": self.history_page,
            "pageSettingsHost": self.settings_page,
        }
        stack = self.window.findChild(QStackedWidget, "mainStack")
        for page_name, page_widget in page_map.items():
            if page_widget is None:
                continue
            placeholder = self.window.findChild(QWidget, page_name)
            if placeholder is None:
                continue
            if page_name == "pageCalculation" and stack is not None:
                # CalculationPage 自带从同一 .ui 加载的 pageCalculation 根节点；
                # 直接替换 stack 中的占位页，避免同名控件重复嵌套。
                index = stack.indexOf(placeholder)
                stack.removeWidget(placeholder)
                placeholder.setParent(None)
                placeholder.deleteLater()
                stack.insertWidget(index, page_widget)
                page_widget.setVisible(True)  # setParent 会清除可见标记，必须显式恢复
                continue
            self._replace_placeholder(placeholder, page_widget)

        # 设置页：加载 settings_page.ui 挂载进 pageSettingsHostLayout
        settings_host = self.window.findChild(QWidget, "pageSettingsHost")
        if settings_host and self.settings_page is None:
            # 如果没有外部注入的设置页，加载 .ui 版本
            self._mounted_settings_widget = load_settings_page(parent=settings_host)
            host_layout = settings_host.layout()
            if host_layout:
                host_layout.addWidget(self._mounted_settings_widget)

    @staticmethod
    def _replace_placeholder(placeholder: QWidget, real_widget: QWidget) -> None:
        """清除 Designer 占位内容，将 real_widget 挂载进 placeholder 的布局。"""
        layout = placeholder.layout()
        if layout is None:
            layout = QVBoxLayout(placeholder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        # 清除 Designer 占位子控件（ QLabel with uiPlaceholder property 等）
        from PySide6.QtWidgets import QLayout

        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None and child is not real_widget:
                child.setParent(None)
                child.deleteLater()
        real_widget.setParent(placeholder)
        real_widget.setVisible(True)  # setParent 会清除可见标记，必须显式恢复
        layout.addWidget(real_widget)

    # ------------------------------------------------------------------
    # 数据目录
    # ------------------------------------------------------------------

    def _bind_data_directory(self) -> None:
        self.lbl_data_dir = self.window.findChild(QLabel, "lblDataDirectoryPath")
        btn_change = self.window.findChild(QPushButton, "btnChangeDataDirectory")
        if self.lbl_data_dir:
            path_text = str(self.context.paths.data_dir)
            self.lbl_data_dir.setText(path_text)
            # 路径显示策略：单行 + 中间截断 + 悬停工具提示。
            # 侧边栏固定 220px，卡片内边距后约 188px 可用宽度，
            # 不使用 wordWrap（长路径换行会挤占按钮空间并导致文字重叠）。
            self.lbl_data_dir.setWordWrap(False)
            self.lbl_data_dir.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.lbl_data_dir.setToolTip(path_text)
            # 固定单行高度，防止路径撑高卡片
            fm = QFontMetrics(self.lbl_data_dir.font())
            self.lbl_data_dir.setMaximumHeight(fm.height() + 4)
            self.lbl_data_dir.setMinimumWidth(60)
            # 安装事件过滤器实现 ElideMiddle 绘制
            self._path_elide_filter = _PathElideFilter(self.lbl_data_dir)
            self.lbl_data_dir.installEventFilter(self._path_elide_filter)
        if btn_change:
            btn_change.clicked.connect(self.change_data_directory)

    def change_data_directory(self) -> None:
        """切换数据目录：只写 location.json，重启后生效，不复制/合并/覆盖任何数据。

        - 用户选择目标文件夹 → 写入 location.json；
        - 提示“重启后切换”，当前进程继续使用旧目录；
        - 不自动 copy settings / API / 数据库 / 图片，不合并历史与校准数据。
        """
        selected = QFileDialog.getExistingDirectory(
            self.window, "选择新的数据目录", str(self.context.paths.data_dir)
        )
        if not selected:
            return
        from profit_accounting_26.shared import ApplicationPaths

        target = Path(selected).expanduser().resolve()
        if target == self.context.paths.data_dir.resolve():
            QMessageBox.information(
                self.window, "数据目录未变化", "该目录就是当前数据目录。"
            )
            return
        ApplicationPaths.save_data_dir(target)
        QMessageBox.information(
            self.window,
            "数据目录已设置",
            f"新数据目录：{target}\n\n"
            "数据目录将在重启后切换。\n"
            "不会自动合并或覆盖两个目录中的已有数据。\n\n"
            f"当前会话继续使用：{self.context.paths.data_dir}",
        )
        # 目录标签保持显示当前真实运行目录，不把尚未生效的新目录伪装成当前目录。
        if getattr(self, "lbl_data_dir", None):
            path_text = str(self.context.paths.data_dir)
            self.lbl_data_dir.setText(path_text)
            self.lbl_data_dir.setToolTip(path_text)

    # ------------------------------------------------------------------
    # 汇率
    # ------------------------------------------------------------------

    def _bind_exchange_rate(self) -> None:
        from PySide6.QtWidgets import QDoubleSpinBox

        self.spin_rate = self.window.findChild(QDoubleSpinBox, "spinExchangeRate")
        btn_refresh = self.window.findChild(QPushButton, "btnRefreshExchangeRate")
        self.lbl_rate_updated = self.window.findChild(QLabel, "lblExchangeRateUpdated")
        if self.spin_rate:
            self.spin_rate.setValue(float(self.settings.get("exchange_rate_usd_to_rmb", 7.2)))
        if self.lbl_rate_updated:
            updated = str(self.settings.get("exchange_rate_updated_at") or "未记录")
            self.lbl_rate_updated.setText(f"最后修改：{updated}")
        if btn_refresh:
            btn_refresh.clicked.connect(self.save_exchange_rate)
        if self.spin_rate:
            self.spin_rate.valueChanged.connect(self._on_rate_live_changed)

    def _on_rate_live_changed(self, _value: float) -> None:
        """汇率实时变化时仅更新更新时间标签，不自动保存。"""
        # 实时保存由 refresh 按钮触发；这里只做 UI 反馈
        if self.lbl_rate_updated:
            self.lbl_rate_updated.setText("未保存修改")

    def save_exchange_rate(self) -> None:
        if not self.spin_rate:
            return
        value = self.spin_rate.value()
        if value <= 0:
            QMessageBox.warning(self.window, "汇率无效", "汇率必须大于0。")
            return
        self.settings = self.context.settings_service.load()
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.settings["exchange_rate_usd_to_rmb"] = value
        self.settings["exchange_rate_updated_at"] = updated_at
        # 尾程 RMB = USD × 汇率（USD 为主字段）
        self.settings["default_tail_fee_rmb"] = float(
            self.settings.get("default_tail_fee_usd", 5.56)
        ) * value
        self.context.settings_service.save(self.settings)
        self.spin_rate.setValue(value)
        if self.lbl_rate_updated:
            self.lbl_rate_updated.setText(f"最后修改：{updated_at}")
        # 通知计算页刷新利润区冻结换算值（含尾程 RMB）
        if self.calculation_page and hasattr(self.calculation_page, "refresh_settings"):
            self.calculation_page.refresh_settings()
        self.settingsSaved.emit()

    # ------------------------------------------------------------------
    # 保存状态
    # ------------------------------------------------------------------

    def _bind_save_status(self) -> None:
        self.lbl_save_status = self.window.findChild(QLabel, "lblSaveStatus")
        # 历史记录编辑模式状态：独立于 dirty 的第三种状态
        self._is_history_editing = False

    def set_dirty(self, dirty: bool) -> None:
        if not self.lbl_save_status:
            return
        # dirty=True 时优先显示"未保存"（无论是否历史编辑模式）
        if dirty:
            self.lbl_save_status.setText("未保存")
            self.lbl_save_status.setStyleSheet(
                "background:#FFF4E5;color:#C77600;padding:6px 11px;border-radius:14px;"
            )
        elif self._is_history_editing:
            # 非 dirty 且处于历史编辑模式 → "正在更新历史记录"
            self.lbl_save_status.setText("正在更新历史记录")
            self.lbl_save_status.setStyleSheet(
                "background:#EAF0FA;color:#4A6FA5;padding:6px 11px;border-radius:14px;"
            )
        else:
            self.lbl_save_status.setText("已保存")
            self.lbl_save_status.setStyleSheet(
                "background:#EAF9F2;color:#168A58;padding:6px 11px;border-radius:14px;"
            )

    def set_history_editing(self, editing: bool) -> None:
        """切换历史编辑模式。进入时显示"正在更新历史记录"；退出后由 set_dirty 接管。"""
        self._is_history_editing = editing
        if not editing:
            return
        # 进入历史编辑模式且当前非 dirty → 显示"正在更新历史记录"
        if not self.lbl_save_status:
            return
        # 如果已经是"未保存"状态则不覆盖（dirty 优先级高于 editing）
        if self.lbl_save_status.text() == "未保存":
            return
        self.lbl_save_status.setText("正在更新历史记录")
        self.lbl_save_status.setStyleSheet(
            "background:#EAF0FA;color:#4A6FA5;padding:6px 11px;border-radius:14px;"
        )

    # ------------------------------------------------------------------
    # 设置保存后刷新
    # ------------------------------------------------------------------

    def on_settings_saved(self) -> None:
        self.settings = self.context.settings_service.load()
        if self.greeting_header:
            self.greeting_header.refresh_display_name()
        if self.spin_rate:
            self.spin_rate.setValue(float(self.settings.get("exchange_rate_usd_to_rmb", 7.2)))
        if self.lbl_rate_updated:
            updated = str(self.settings.get("exchange_rate_updated_at") or "未记录")
            self.lbl_rate_updated.setText(f"最后修改：{updated}")
        if self.calculation_page and hasattr(self.calculation_page, "refresh_settings"):
            self.calculation_page.refresh_settings()
        self.set_dirty(False)
