# WP-H1-FX01 固定 Fixture 静态观察仓实施记录

日期：2026-10-24，Asia/Shanghai。基线：`e7a081c3c4ccfd948c80a4956fe5aa7a0a0cd1ba`。状态：**IMPLEMENTED / OWNER REVIEW PENDING**。本记录不构成 Owner Acceptance，也不授权 F4/F8、真实数据联算或正式发布。

## 范围

完成 H1 固定 Fixture 纵向切片：创建观察、静态估值、旧价/无价状态、默认 S01 退出提示、更正版本、主动结束、只读历史、重启持久化与 F5 隔离。

- 固定演示用户 `fixture-user`，固定合成 Fixture，无网络调用。
- H1 独立 JSON 存储，默认 `var/fixture-demo/h1-observations.json`，可用 `MISHI_H1_STORE` 覆盖；F5 仍使用原有 `watchlist.json`。
- 复用 `mishi_radar.result_contract` 的固定原始收盘价、Fixture 身份和 `mishi_radar.strategy_core.evaluate_exit` 的 S01 退出判断；未修改 OD-1/OD-2 内核、冻结合同或 FX01A 结果合同。
- 创建/更正支持证券、数量、平均成本、成本基准日期、可选 S01 关联和备注；数量与成本必须为有限正数，允许零股，并拒绝超出可支持范围的极端数值；基准日期不得晚于本地当日。
- 估值使用 `q×P`、`q×c`、`q×(P-c)`、`P/c-1`；无价时市值/浮盈/浮盈率为 UNKNOWN；旧价保留最后价格日期并标记“基于旧价”。
- 更正创建新版本，旧版本保留；结束需独立确认页和必填原因，保存当时数量、成本、基准日期、参考价/日期或 UNKNOWN、规则状态、原因和结束时间；结束后只读，再次观察创建新记录。
- 持有交易日按固定 Fixture 日历从基准日（含）计至业务日；基准日非交易日从之后首个交易日起算；缺持有上下文或必要行情时 S01 状态为 UNKNOWN，不自动结束。
- 页面明示未计交易费用、分红、送转及其他公司行为调整；静态浮盈不替代 OD-2 未平仓经济损益止损口径；只复用 S01 策略退出条件与最长持有，不含 OD-2 通用止损。
- 未入机会榜、行情缺失或 UNKNOWN 均不等于退出。

## 文件

新增：

- `mishi_radar/demo/h1.py`：独立 H1 版本化存储。
- `mishi_radar/demo/h1_service.py`：校验、估值、原始价读取、持有日计数、S01 退出提示与页面视图。
- `mishi_radar/demo/templates/h1.html`、`h1_end.html`：观察仓与结束确认页。
- `tests/test_h1_fixture.py`：9 项 H1 测试。
- `docs/WP_H1_FX01_IMPLEMENTATION_2026-10-24.md`：本记录。
- `outputs/wp-h1-fx01-fixture-observer-2026-10-24/`：测试日志、浏览器证据与差异记录。

修改：

- `mishi_radar/demo/app.py`：H1 路由、独立存储注入、`/api/h1`。
- `mishi_radar/demo/__init__.py`：包说明。
- `mishi_radar/demo/service.py`：F7 状态页 H1 Gate 文案更新。
- `mishi_radar/demo/templates/base.html`：H1 导航与边界说明。
- `mishi_radar/demo/static/app.css`：H1 表单、卡片与移动端样式。

## 实施中发现并修复的缺陷

- `H1_ENDED_QUERY_COLLISION`：`/h1?ended=1` 的查询参数覆盖了模板中的 ENDED 列表，导致结束历史不显示。改为独立 `notice_ended` 键，并加入结束流程测试。
- `H1_EXTREME_DECIMAL_500`：极大/极小有限数值通过初版校验后在页面计算阶段触发 500。增加可表示范围校验并加入异常输入测试。

两项均在授权范围内最小修复，相关测试与浏览器流程已重新验证。

## 验证

- 定向测试：`python -m unittest tests.test_h1_fixture tests.test_demo_product -v`，17 项通过（H1 9、FX01B 产品 8），退出码 0。已接受的 184 项证据未重跑；本轮未修改 result contract、OD-1/OD-2 或既有 F5 记录语义。
- 浏览器：Chromium 148 headless 仿真，桌面 1440×1000、手机 390×844；完成创建、估值、更正、结束、只读历史、再次观察和旧价 UNKNOWN 路径；手机视口无页面级横向溢出。**真实 Android/iPhone 设备未测**，不得将仿真冒充真机。
- 测试日志：`outputs/wp-h1-fx01-fixture-observer-2026-10-24/unittest.log`。
- 浏览器日志与截图：同目录 `browser_check.log`、`desktop-*.png`、`mobile-*.png`。
- 差异与清单：同目录 `diff.patch`、`change-record.json`。

## 未覆盖 / 保留限制

- 完整 H1 验收、真实持仓、实时行情、账户权益、交易账本、费用/分红/送转自动调整均未实现或未通过 Gate。
- 只验证默认 S01；其它策略、F4、F8、OD-3 数值与正式发布未推进。
- 浏览器证据为仿真视口，不构成真实设备验收。
- 本切片不提升 FX01A 具名限制、真实数据资格或下一 Phase 授权。
