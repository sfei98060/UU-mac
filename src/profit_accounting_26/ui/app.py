from __future__ import annotations

from profit_accounting_26._version import __version__
from profit_accounting_26.ui.main_window import NAV_ITEMS, MainWindow


def build_window(data_dir=None):
    """构造主窗口。

    ``data_dir`` 显式传入（测试/工具）时直接使用，跳过 location.json 与首次
    目录选择；未传入时走正式启动逻辑（共享 bootstrap_application）：
    location.json 已存在 → 以其为唯一数据目录（忽略 PROFIT_ACCOUNTING_DATA_DIR）；
    不存在 → 弹窗要求选择数据目录，取消则返回 ``(app, None)``。
    """
    from profit_accounting_26.application import AppContext
    from profit_accounting_26.ui.bootstrap import bootstrap_application

    app, paths = bootstrap_application(
        data_dir=data_dir,
        app_name=f"UU护航 {__version__}",
        icon_relative="src/profit_accounting_26/ui/assets/app_icon_desktop_taskbar.svg",
    )
    if paths is None:
        return app, None
    context = AppContext.create_default(paths=paths)
    window = MainWindow(context)
    return app, window


def main() -> int:
    import sys

    from profit_accounting_26.ui.single_instance import (
        UU_ESCORT_INSTANCE_KEY,
        SingleInstanceGuard,
    )

    app, window = build_window()
    if window is None:
        return 0
    # UU护航 单实例：已有实例时请求激活并正常退出，不创建第二个窗口/AppContext
    guard = SingleInstanceGuard(UU_ESCORT_INSTANCE_KEY, parent=app)
    if guard.already_running:
        return 0

    def _activate() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    guard.activateRequested.connect(_activate)
    window.showMaximized()
    if sys.platform == "darwin":
        # 从 Finder 双击 .app（或经 open/终端）启动时显式请求置前并激活，
        # 保证启动后窗口立即处于可用状态。
        window.raise_()
        window.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
