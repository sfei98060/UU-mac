from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QDoubleSpinBox, QWidget


class NumericFocusSelectAllFilter(QObject):
    """可编辑 QDoubleSpinBox 获得焦点时自动全选（UU护航 / UU测算 共享交互）。

    背景：Qt 6 的 QDoubleSpinBox 获得焦点不会自动全选，用户想输入新数值时
    必须先手动删除 ``0.00`` / ``18.00`` 旧文本。

    关键事实（决定了实现方式）：
    - FocusIn 事件投递给 spinbox 本身，而不是内部 lineEdit（已实测验证）；
    - 鼠标首击的 press 处理会在焦点事件之后定位光标并清掉选区。
    因此不能在 FocusIn 里直接 selectAll，也不能只监听 lineEdit：
    统一用 QTimer.singleShot(0) 把 selectAll 排队到焦点/鼠标默认处理完成之后。

    行为边界：
    - 获得焦点自动全选；已聚焦后的再次点击不产生 FocusIn，
      光标编辑保持 Qt 原生行为；
    - 小数点键 = 小数位编辑导航：只选中小数位，键入即替换，
      无需 Delete/Backspace（详见 ``_handle_decimal_key``）；
    - 只读（冻结）字段不处理；
    - Enter 提交 / Esc 恢复 / 空白草稿回退等既有契约不变；
    - 不改任何小数精度，也不把金额/重量字段变成整数输入。
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        etype = event.type()
        if etype == QEvent.Type.FocusIn:
            spin = self._owner_spinbox(watched)
            if spin is None or spin.isReadOnly():
                return False
            line = spin.lineEdit()
            if line is not None:
                QTimer.singleShot(0, line.selectAll)
            return False
        if etype == QEvent.Type.KeyPress:
            return self._handle_decimal_key(watched, event)
        return False

    def _handle_decimal_key(self, watched: QObject, event: QKeyEvent) -> bool:
        """小数点键 = 小数位编辑导航：只选中小数位，键入即替换。

        - 仅处理可编辑且 ``decimals() > 0`` 的 QDoubleSpinBox（含其内部
          lineEdit——键事件可能到达其中任一目标，统一经 _owner_spinbox 解析）；
        - 按“控件区域设置的小数点”识别按键（Windows/中文环境的键盘 ``.``
          即命中；逗号小数布局自动跟随）；
        - 草稿已含小数点 → 只选中其后的 ``decimals()`` 位小数，
          不碰前后缀/单位文本；
        - 草稿尚无小数点（如已键入 "18"）→ 把草稿补全为 "18.00" 并只
          选中 "00"，用户键入即替换；
        - 按下小数点本身不改变数值（仅编辑草稿）；
        - 返回 True 吞掉该键，避免 Qt 再插入一个多余的小数点。
        """
        spin = self._owner_spinbox(watched)
        if spin is None or spin.isReadOnly() or spin.decimals() <= 0:
            return False
        decimal_point = spin.locale().decimalPoint()
        if not event.text() or event.text() != decimal_point:
            return False
        line = spin.lineEdit()
        if line is None:
            return False
        text = line.text()
        sep = text.rfind(decimal_point)
        if sep < 0:
            integer_part = text.strip() or "0"
            text = f"{integer_part}{decimal_point}{'0' * spin.decimals()}"
            line.setText(text)
            sep = text.rfind(decimal_point)
        start = sep + len(decimal_point)
        line.setSelection(start, min(spin.decimals(), max(0, len(text) - start)))
        return True

    @staticmethod
    def _owner_spinbox(watched: QObject) -> QDoubleSpinBox | None:
        """FocusIn 可能投递给 spinbox 或其内部 lineEdit，统一解析出所属 spinbox。"""
        if isinstance(watched, QDoubleSpinBox):
            return watched
        if isinstance(watched, QLineEdit):
            parent = watched.parentWidget()
            if isinstance(parent, QDoubleSpinBox):
                return parent
        return None


def install_natural_numeric_input(target: QObject) -> NumericFocusSelectAllFilter:
    """给 ``target`` 安装焦点全选/小数点导航过滤器。

    生产入口在 bootstrap_application 里对 QApplication 安装一次，
    两个软件的全部可编辑数值输入统一生效；测试可对单个 spinbox 安装。
    传入 QDoubleSpinBox 时同时挂到其内部 lineEdit——键事件可能到达
    spinbox 或 lineEdit 任一目标，逐 widget 安装也必须两处都覆盖。
    """
    guard = NumericFocusSelectAllFilter(target)
    target.installEventFilter(guard)
    if isinstance(target, QDoubleSpinBox):
        line = target.lineEdit()
        if line is not None:
            line.installEventFilter(guard)
    return guard


class DraftAwareDoubleSpinBox(QDoubleSpinBox):
    """Commit only valid completed edits; restore the prior value on blank drafts."""

    committed = Signal(float)
    unknownRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._committed_value = float(self.value())
        self._programmatic = False
        self.setKeyboardTracking(False)
        self.editingFinished.connect(self._commit_or_restore)

    def setValue(self, value: float) -> None:  # noqa: N802
        self._programmatic = True
        try:
            super().setValue(float(value))
            self._committed_value = float(value)
        finally:
            self._programmatic = False

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._committed_value = float(self.value())
        super().focusInEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            super().setValue(self._committed_value)
            self.lineEdit().selectAll()
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def _commit_or_restore(self) -> None:
        if self._programmatic:
            return
        text = self.lineEdit().text().strip()
        if not text:
            super().setValue(self._committed_value)
            return
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            super().setValue(self._committed_value)
            return
        super().setValue(value)
        if value != self._committed_value:
            self._committed_value = value
            self.committed.emit(value)

    def request_unknown(self) -> None:
        self.unknownRequested.emit()


class BlankClickFocusFilter(QObject):
    """Clicking a non-editor area inside the calculation page commits/restores the active editor."""

    EDITOR_TYPES = (QLineEdit, QAbstractSpinBox, QComboBox)

    def __init__(self, root: QWidget) -> None:
        super().__init__(root)
        self.root = root

    def _inside_root(self, target: QWidget) -> bool:
        cursor: QWidget | None = target
        while cursor is not None:
            if cursor is self.root:
                return True
            cursor = cursor.parentWidget()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.MouseButtonPress or not isinstance(watched, QWidget):
            return False
        target = watched
        if not self._inside_root(target):
            return False
        cursor: QWidget | None = target
        while cursor is not None and cursor is not self.root:
            if isinstance(cursor, self.EDITOR_TYPES):
                return False
            cursor = cursor.parentWidget()
        focused = QApplication.focusWidget()
        if focused is None:
            # 页面被代理嵌入时（macOS 容器层缩放），编辑焦点位于代理容器
            # 窗口，应用级 focusWidget() 返回 None，需回退到根节点所在窗口。
            root_window = self.root.window()
            if root_window is not None:
                focused = root_window.focusWidget()
        if focused is not None and focused is not target:
            focused.clearFocus()
        return False


def install_blank_click_focus_filter(root: QWidget) -> BlankClickFocusFilter:
    guard = BlankClickFocusFilter(root)
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication尚未创建")
    app.installEventFilter(guard)
    return guard
