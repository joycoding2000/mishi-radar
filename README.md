# mishi-radar · A股机会雷达

面向有投资经验、不会编程的A股个人投资者，帮助用户随时发现候选股票、理解入选依据、持续跟踪并检验历史表现。首发渠道为闲鱼，聚宽社区其次。

**当前阶段：R3.2 已批准范围与规则基线已记录，完整设计和数据资格尚未冻结。** Owner 已批准八策略、六维诊断、H1、PC/手机响应式 Web 和当前扫描/历史回测两项底线；OD-1/OD-2 已批准，OD-3 仅原则接受，运行和权益数值仍为 UNKNOWN。WP-FX01A 固定 Fixture F1/F3/F7 结果合同已由 Owner `PASS_WITH_LIMITATION` 接受；本仓库新增的 WP-FX01B Web 切片只消费该合同和固定合成输入，不接真实行情、不通过数据 Gate，也不构成发布批准。工程与本地目录名为`mishi-radar`；中文交付名称仍为提案，见[命名记录](docs/2026-10-15-PRODUCT_NAMING.md)。

本地工作区：`D:\Dev\Projects\mishi-radar`。GitHub仓库：[joycoding2000/mishi-radar](https://github.com/joycoding2000/mishi-radar)，SSH远端为`git@github.com:joycoding2000/mishi-radar.git`，`main`跟踪`origin/main`。

## WP-FX01B 固定 Fixture Web 演示

这是一条可在本机直接运行、可交互、响应式的 Fixture 演示路径：

**机会榜 F1 → 个股诊断 F3 → 关注 F5 → 合成现金回测 F6**，并在数据状态 F7 持续展示合同身份、覆盖、质量与 Gate。

- F1/F3/F7：消费 `mishi_radar.result_contract`（`FX01A-RESULT-CONTRACT-v1`）的已验收合同输出；Web 层不重算排名、条件或六维。
- F5：固定演示用户 `fixture-user` 的最小关注/取消与首次关注快照；数据隔离存储在本地 JSON，不引入正式账户系统。
- F6：调用 `mishi_radar.cash_backtest.run_backtest`；所有现金、NAV、成交、费用、股息税和失败原因来自内核。默认 `u3` 场景与已验收合成算例一致。
- F2：只提供策略切换和透明三风格显示；不实施完整参数编辑能力。
- F4/H1/F8 及其它未批准能力保持 Gate，不提供空壳页面。

### 启动

```powershell
python -m pip install -r requirements.txt
python -m mishi_radar.demo
```

打开 <http://127.0.0.1:8000>。可配置环境变量：

- `MISHI_DEMO_HOST`（默认 `127.0.0.1`）
- `MISHI_DEMO_PORT`（默认 `8000`）
- `MISHI_FIXTURE_STORE`（关注状态 JSON 路径；默认本地 `var/fixture-demo/watchlist.json`，已加入 `.gitignore`）

### 演示状态

F1/F3/F7 提供五个可复现场景：正常候选 `CANDIDATES`、完整空结果 `EMPTY`、部分输入 `PREVIEW`、全部不可判定 `UNKNOWN`、输入请求失败 `FAILED`。F1 显示 N 支持 `1/2/3/5/10/20/30`，小 N 用于查看合同的 `beyond_top_n` 榜外精确名次。零候选的 F1 CSV 仍保留 `STATUS` 身份行（标记、批次与 `EMPTY`），不会虚构候选。F6 提供 `u3`（完整现金场景）、`failures`（停牌/跌停失败与重试）、`empty`（无信号现金曲线）和 `blocked`（信号可用时刻未知）。

页面、JSON API 和 CSV 导出均带 `SYNTHETIC / FIXTURE / 非真实行情` 标记；所有页面均无真实行情接口、真实扫描、真实历史收益或预测胜率。

### 测试

```powershell
python -m unittest discover -s tests -t .
```

浏览器证据脚本使用 Chromium 仿真（桌面 1440×1000、手机 390×844），不是真实 Android/iPhone 设备验收：

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m mishi_radar.demo --port 8766
python outputs/wp-fx01b-fixture-vertical-2026-10-23/browser_check.py
```

## 恢复上下文的阅读顺序

1. [当前状态与决策](docs/CURRENT_STATE.md)：当前权威顺序、数据阻断与本轮授权边界。
2. [WP-FX01A Owner Acceptance](docs/WP_FX01A_OWNER_ACCEPTANCE_2026-10-23.md) 与 `mishi_radar/result_contract/`：已接受的 F1/F3/F7 结果合同与具名限制。
3. [R3.2 已批准范围](docs/MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md)及[DR01–DR06 消费者合同](docs/MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md)：正式范围与当前/历史双资格。
4. [最新运行规格候选](docs/MISHI_RADAR_R3_2_PRODUCT_OPERATING_SPEC_CANDIDATE_2026-10-19.md)及[Owner 决策记录](docs/MISHI_RADAR_R3_2_OWNER_DECISIONS_2026-10-19.md)：OD-1/OD-2 规则基线、OD-3 未冻结数值与限定验收。
5. [DR01 最终来源报告](outputs/dr01-current-unblock-2026-10-18/DR01-CURRENT-report.md)及[DR02–DR06 综合差距报告](outputs/dr02-dr06-consolidation-2026-10-19/DR02-DR06-consolidated-gap-report.md)：已完成调查与剩余数据资格缺口。
6. 较早的[范围讨论](docs/2026-10-15-V0_1_SCOPE_DISCUSSION.md)、[策略提案](docs/2026-10-15-LAUNCH_STRATEGIES.md)、[回测提案](docs/2026-10-15-BACKTEST_CAPABILITIES.md)及[竞品对照](docs/2026-10-15-COMPETITOR_STRATEGY_BACKTEST.md)保留来源身份；冲突以最新范围和 Owner 决策为准。

## 文档与研究资料导航

| 文档 | 用途与时效 |
| --- | --- |
| [初始交接](docs/PRODUCT_HANDOFF.md) | ChatGPT讨论形成的初始背景，含后来修正的旧判断；当前状态优先 |
| [WP-FX01A Owner Acceptance](docs/WP_FX01A_OWNER_ACCEPTANCE_2026-10-23.md) | F1/F3/F7 结果合同验收、具名限制与暂停文件 SHA256 基线 |
| [讨论时间线](docs/2026-10-14-PRODUCT_DISCUSSION.md) | 保留讨论、补充和纠偏顺序；不是所有段落同时有效 |
| [首款方向比较](docs/2026-10-15-PRODUCT_DIRECTION.md) | A/B/C方向比较及Owner对使用时段的修正 |
| [闲鱼截图记录](docs/2026-10-14-XIANYU_EVIDENCE.md) | 商品截图、价格与交付声明；不代表实际成交 |
| [综合竞品截图索引](docs/research/competitor-scope-2026-10-15.json) | 当轮25张图片路径；后续增补另见三款竞品对照，不是全部已读图片总表 |
| [本机资料利用基线](docs/LOCAL_RESEARCH_ASSETS.md) | 五个资料库实际检查范围、用途和限制 |
| [聚宽全文阅读入口](docs/joinquant-full-review/README.md) | 完成状态、逐文件记录、机制、缺陷及原始路径索引 |
| [软件命名与目录记录](docs/2026-10-15-PRODUCT_NAMING.md) | 工程/目录名已确认mishi-radar；中文名觅势仍为提案 |

## 文档使用规则

- 以Owner最新明确决定为准；“助手建议”“待确认”“有条件首发”不等于批准范围。
- 区分已有操作记录、页面截图、卖家声明、用户留言、助手设计与未知；策略阈值不是验证结果。
- 竞品丰富程度、源码文件数、买家关注数不能直接换算需求、策略有效性或收入。
- 当前不讨论合规，不把复杂研究Gate、统一平台或等完长期调查作为立项前提。
- 不修改其他项目或原始资料；产品编码、策略运行、部署、购买及外部发消息均需各自明确授权。

## Git收录范围

提交产品文档、研究结论、逐文件语义记录、索引、覆盖校验，以及`outputs/`中报告引用的原始响应、请求账本、调查脚本和身份清单。`.gitattributes`保留哈希所标识合同及证据的原始字节。源码阅读切块、抽取副本和图片保留在本机，由既有`.gitignore`排除；不删除、不当作产品代码导入。外部截图与资料库仍位于各文档列明的本机路径，新环境不能假定其可访问。

当前已有 WP-FX01B 固定 Fixture Web 演示与产品集成测试；F1/F3/F7 只读结果合同、F5 演示关注和 F6 合成现金检验可在本机启动。该演示不代表真实行情、真实历史收益、数据资格或发布验收，F4/F8/H1 等未批准能力仍保持 Gate。
