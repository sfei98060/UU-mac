# MACOS_CODEX_RESULT

macOS 原生运行版（macos-native-runtime）执行结果报告。

## 环境

| 项目 | 值 |
| --- | --- |
| Mac 型号 / 芯片 / 架构 | MacBook Air / Apple M2 / arm64 |
| macOS 版本 | 26.5.1（Build 25F80） |
| 显示器 | 内建 Liquid Retina，物理 2560×1664，逻辑 1470×956，DPR 2.0 |
| Qt availableGeometry | 1470×837（最大化后窗口实测 1470×805） |
| Python 版本 | 3.11.16（Homebrew `/opt/homebrew/bin/python3.11`，符合 `>=3.11,<3.12` 契约） |
| PySide6 版本 | 6.11.2 |
| 源仓库（只读） | aidenkael/2.6.1（remote `upstream`，未做任何修改） |
| 基线 SHA | `6aab42a964e1a83b0bffeb34c6abffbdfd7a119d`（分支 fix/3.0.1-runtime-bugfixes） |
| 工作仓库 | aidenkael/UU-mac（remote `origin`，未向其推送） |
| 推送目标 | `https://github.com/sfei98060/UU-mac`（remote `sfei98060`，用户指定） |
| 目标分支 | `macos-native-runtime` |

## 修改文件清单

| 文件 | 改动性质 |
| --- | --- |
| `src/profit_accounting_26/ui/main_window.py` | 平台门控商品采集导入/初始化/导航项；darwin 下应用 `_apply_macos_fit()` 尺寸调整 |
| `src/profit_accounting_26/ui/binders/main_window_binder.py` | 导航绑定表平台门控；非 Windows 隐藏商品采集导航按钮 |
| `src/profit_accounting_26/ui/app.py` | darwin 下 `showMaximized()` 后 `raise_() + activateWindow()` |
| `tests/ui/test_ui_shell.py` | 导航项断言改为平台感知（非 Windows 为 3 项） |
| `.gitignore` | 追加 macOS 系统文件条目（.DS_Store 等） |
| `启动UU护航.command` | 新增：Finder 双击启动器（自动建 .venv、装依赖、启动应用） |

未改动：计算页、货代规则、汇率、SHEIN 补贴、历史/图片、AI 识别、数值输入、单实例守卫、数据目录生命周期等全部既有模块；未创建安装包；未为实验提升版本号。

## 实际发现的 macOS 不兼容及根因修复

1. **启动即崩：`ModuleNotFoundError: No module named 'playwright'`**
   根因：`main_window.py` 模块级导入 `product_collector` → `business_source.py` 模块级 `from playwright.async_api import ...`，且采集核心依赖 `channel="msedge"` 的 Microsoft Edge（仅 Windows 分发）。
   修复：按文档要求做平台门控（`sys.platform == "win32"` 才导入/初始化采集模块）；采集依赖缺失不阻塞启动。未改写采集模块内部逻辑。

2. **商品采集导航在 macOS 无意义且必然失败**
   根因：同上，采集功能链完全依赖 Windows + Edge。
   修复：`NAV_ITEMS` 与导航绑定表在非 Windows 过滤掉商品采集项/按钮；页面不创建。保留代码不删除（文档要求"禁用但不删除"）。

3. **最大化窗口不前置/不激活（darwin 行为差异）**
   修复：`app.py` 在 darwin 下 `showMaximized()` 后追加 `raise_()` 与 `activateWindow()`。

4. **13 英寸屏（1470×837）上测算页溢出（页面按 1920×1080 设计）**
   修复：仅做文档许可的结构性尺寸调整——侧栏 220→184、计算主体最小宽度清零并收紧边距/间距、各分区最小宽度下调（成本包装 600、货代 320、尾部设置/系统成本 200、三张产品卡 186）。未缩小任何控件字号/精度，未改任何业务逻辑。完整适配结果见下文"最大化页面结果"。

## 商品采集在 macOS 的行为

不导入、不初始化、不出现在导航；不尝试安装/调用 Playwright，不探测 Edge；应用启动路径完全不依赖采集模块。Windows 上 `COLLECTOR_ENABLED = True`，行为与基线一致（未改写采集代码）。

## 既有功能保留状态

| 功能 | 状态 |
| --- | --- |
| 新商品测算（裸品/常规/保守三档） | 保留，冒烟通过 |
| 正反算、利润率、货代规则切换 | 保留；冒烟实测 `select_forwarder('forwarder_yiwu_default')`/`'forwarder_shenzhen_default'` 切换生效 |
| 汇率设置与持久化 | 保留；重启后 7.42 正确回读（注：见"遗留问题"中的既有 emit bug） |
| SHEIN 补贴规则 | 保留（未触碰相关模块） |
| 保存/历史/图片 | 保留；契约测试覆盖通过；未用 UI 直接驱动保存弹窗（改用 126 项契约测试作证据） |
| AI 识别/重估 | 保留，见下节 |
| 数值输入契约（焦点全选/小数点导航/Enter 提交/Esc 恢复/空白回退） | 保留，未触碰 `input_editing.py` |
| 单实例守卫（QLocalServer） | 跨平台，未触碰 |

## AI 识别 / 重估状态

- AI 按钮、配置存储（`api_profile_store`）、服务初始化路径在 macOS 上均可达，无平台不兼容。
- 按文档要求未发起任何付费调用；本机无有效 API 凭据，**在线识别/重估的实际请求未验证**（列为未验证项）。

## 用户数据目录行为

- `~/.profit_accounting_26/location.json` 为唯一权威；首次启动引导用户选择目录（本会话选择桌面下的独立数据目录）。
- 重启后正确复用已选目录，汇率 7.42 持久化回读通过；`StaleDataDirectoryError` 生命周期守卫未被触碰。

## 启动器

- 路径：`/Users/hana/Desktop/UU护航-mac/启动UU护航.command`（已 `chmod +x`）。
- 冷启动结果：Finder 双击 → 自动定位/创建项目内 `.venv`、按需安装 PySide6/openpyxl/Pillow 并 `pip install -e . --no-deps`（不装 playwright）→ 应用成功启动并最大化。**双击启动：可用。**

## 最大化"新商品测算"页面结果

结论：**未能在本机屏幕上完全免滚动呈现**，现按文档许可条款停下并记录精确阻塞数据：

- availableGeometry：1470×837；最大化窗口：1470×805；测算页视口：1269×708；内容 sizeHint：1386×857。
- 溢出：水平 117px、垂直 149px（调整后；调整前为 127/177）。
- 阻塞尺寸来源：`imageInputSection` 高 207（图片槽预览固定高 102+按钮）、`aiSummary` 62、中段分区合计 314、`profitSection` 187、底部操作区 58；水平方向被成本区内部控件最小宽度（约 849 hint）钉住。
- 页面按 1920×1080 设计（约需 1690×1030 有效区）；本机为 13″ 1470×837。在不缩小任何控件/不重排结构的前提下无法消除此溢出；进一步压缩属于文档禁止的结构性重设计，故按条款记录后止步。现有滚动区域可完整访问全部内容，功能不受损。

## 定向自动化测试结果

- 运行范围：按文档仅跑定向测试，不运行采集/浏览器/Windows 打包测试。
- 结果：**126 通过**；3 个采集测试（`test_commit_c_targeted.py::TestCollectorDeleteKey`）因缺 playwright 被排除，符合文档预期。

## 实机冒烟结果

- 冷启动（启动器）：通过。
- 最大化 + availableGeometry 测量：通过（数值见上节）。
- 核心冒烟（导航切换、货代切换、汇率输入、页面驱动）：通过。
- AI 状态：未做付费调用，见上节。
- 重启持久化：通过（汇率 7.42 + 数据目录复用）。

## 遗留阻塞 / 未验证项

1. **既有跨平台 bug（非本次引入，未修）**：`MainWindowBinder` 非 QObject 却声明 `Signal()`，`save_exchange_rate()` 末尾 `self.settingsSaved.emit()` 抛 `AttributeError`。汇率落盘发生在 emit 之前，持久化仍生效；影响为保存后的一次通知信号。按文档"只修真实 macOS 不兼容"的范围约束未修，如实记录。
2. 最大化免滚动适配在本机不可达（精确阻塞数据见上节）。
3. AI 在线识别/重估因无凭据未做实际请求验证。
4. `QBoxLayout::insert` 占位替换告警为基线既有噪音，改动前后一致，未处理。

## 最终提交

- 分支：`macos-native-runtime`
- 实现提交 SHA：`d11d51d0dd2e2ca2a87705bc2221cd72f60fc788`（本报告随其后一条提交入库，两笔均已推送）
- 推送：仅推送至 `https://github.com/sfei98060/UU-mac`；未向 `origin`（aidenkael/UU-mac）或 `upstream`（aidenkael/2.6.1）推送；未合并；未修改源仓库。
