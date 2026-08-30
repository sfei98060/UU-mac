"""验证 macOS 容器层整体等比缩放 + UU测算 入口（几何断言 + 交互 + 截图）。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QTransform
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QGraphicsView,
    QLabel,
    QPushButton,
    QScrollArea,
)

from profit_accounting_26.ui.app import build_window

tmp = Path(tempfile.mkdtemp(prefix="uu_macfit_"))
app, window = build_window(data_dir=tmp)
window.show()
app.processEvents()

page = window.calculation_page
results = {}


def probe(tag: str, w: int, h: int) -> None:
    window.resize(w, h)
    app.processEvents()
    view = page._scaling_view
    assert isinstance(view, QGraphicsView), f"{tag}: 缩放视图缺失"
    root = page._root
    scroll = root.findChild(QScrollArea, "calculationScrollArea")
    assert scroll is not None, f"{tag}: 页面内滚动区丢失"
    scale = view.transform().m11()
    row = dict(
        window=(w, h),
        frozen=(root.width(), root.height()),
        viewport=(view.viewport().width(), view.viewport().height()),
        scale=round(scale, 4),
        inner_hbar=scroll.horizontalScrollBar().maximum(),
        inner_vbar=scroll.verticalScrollBar().maximum(),
    )
    results[tag] = row
    assert row["inner_hbar"] == 0 and row["inner_vbar"] == 0, f"{tag}: 页面内出现滚动条 {row}"
    assert scale <= 1.0 + 1e-9, f"{tag}: 不允许放大 {row}"
    # 整页缩放后必须完整落在视图视口内
    assert root.width() * scale <= view.viewport().width() + 1, f"{tag}: 水平未完整显示 {row}"
    assert root.height() * scale <= view.viewport().height() + 1, f"{tag}: 垂直未完整显示 {row}"


# 本机最大化窗口实测尺寸
probe("maximized_1470x805", 1470, 805)
# 正常窗口
probe("normal_1200x760", 1200, 760)
# 1920×1080 设计尺寸：应 1:1 不放大
probe("design_1920x1080", 1920, 1080)

window.resize(1470, 805)
app.processEvents()
window.grab().save("/tmp/uu_macfit_maximized.png")
window.resize(1200, 760)
app.processEvents()
window.grab().save("/tmp/uu_macfit_normal.png")

# ---------------- 交互验证（经代理层的真实输入链路） ----------------
window.resize(1470, 805)
app.processEvents()
window.activateWindow()
window.raise_()
app.processEvents()

view = page._scaling_view
edit = page._root.findChild(QDoubleSpinBox, "txtListPriceProfitRate")
assert edit is not None, "标价利率输入框丢失"

# 真实使用中用户点击时窗口必然处于激活态；终端探针无法自行激活，显式设定
QApplication.setActiveWindow(window)
app.processEvents()

# 1) 经视图映射的点击必须让嵌入控件获得焦点（完整事件路径）
from PySide6.QtWidgets import QGraphicsProxyWidget

proxy = next(i for i in view.scene().items() if isinstance(i, QGraphicsProxyWidget))
root_point = edit.mapTo(page._root, edit.rect().center())
mapped = view.mapFromScene(proxy.mapToScene(QPointF(root_point)))
edit.clearFocus()
app.processEvents()
QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=mapped)
app.processEvents()
assert edit.hasFocus(), (
    f"经代理层点击未获焦点: focusWidget={QApplication.focusWidget()!r}"
    f" mapped={mapped} root_point={root_point} active={window.isActiveWindow()}"
)

# 2) 键入 + 回车提交必须生效（业务重算链路不受代理影响）
edit.selectAll()
QTest.keyClicks(edit, "33")
QTest.keyClick(edit, Qt.Key.Key_Return)
app.processEvents()
assert abs(edit.value() - 33.0) < 1e-9, f"键入未生效: {edit.value()}"

# 3) 空白点击提交：未回车直接点非编辑区，值必须已提交
edit.setFocus()
app.processEvents()
edit.selectAll()
QTest.keyClicks(edit, "36")
label = page._root.findChild(QLabel, "lblPackingStateTitle") or page._root.findChild(QLabel)
assert label is not None, "找不到可点击的非编辑控件"
QTest.mouseClick(label, Qt.MouseButton.LeftButton)
app.processEvents()
assert abs(edit.value() - 36.0) < 1e-9, f"空白点击未提交: {edit.value()}"
results["interaction"] = dict(proxy_click_focus=True, typing=True, blank_click_commit=True)

# ---------------- UU测算 入口 ----------------
btn = window.findChild(QPushButton, "btnOpenQuickCalculator")
assert btn is not None, "UU测算 入口按钮缺失"
assert btn.isVisible(), "UU测算 入口按钮不可见"
btn.click()
app.processEvents()
qw = getattr(window, "_quick_calculator_window", None)
assert qw is not None and qw.isVisible(), "UU测算 窗口未打开"
assert qw.windowTitle() == "UU测算", f"UU测算 标题错误: {qw.windowTitle()}"
# 尺寸契约：宽度恒 448；默认折叠 = 折叠锁定高度；展开/收起在两个
# 锁定高度间切换（高度为内容实测值，跨平台随字体不同，不硬编码 475）
assert qw.width() == 448, f"UU测算 宽度契约被破坏: {qw.width()}"
assert qw.height() == qw._collapsed_height > 0, (
    f"UU测算 默认折叠高度错误: {qw.height()} vs {qw._collapsed_height}"
)
qw.grab().save("/tmp/uu_quick_from_main.png")
from PySide6.QtWidgets import QToolButton

toggle = qw.findChild(QToolButton, "btnQuickToggleDetails")
toggle.click()
app.processEvents()
assert qw.height() == qw._expanded_height > qw._collapsed_height, (
    f"UU测算 展开高度错误: {qw.height()} vs {qw._expanded_height}"
)
toggle.click()
app.processEvents()
assert qw.height() == qw._collapsed_height, "UU测算 收起未回到折叠高度"
# 再次点击应复用同一窗口
btn.click()
app.processEvents()
assert getattr(window, "_quick_calculator_window", None) is qw, "UU测算 窗口未被复用"
results["quick"] = dict(
    title=qw.windowTitle(),
    collapsed=qw._collapsed_height,
    expanded=qw._expanded_height,
    reused=True,
)

for tag, row in results.items():
    print(tag, row)
print("MACFIT_OK")
