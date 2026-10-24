# mishi-radar 历史研究成果索引

审查日：2026-10-24（Asia/Shanghai）。范围经 Owner 确认为 **仅 mishi-radar**；不审查 systematic-investing-os、chstockdata 的分支、代码或研究资产。本轮整理现有结论，不执行新实验，不改变 Owner Acceptance、数据资格或下一阶段授权。

**同日盘符更正**：Owner确认WD My Passport已由F:改为E:。现用`E:\BaiduNetdiskDownload`，五个原库均可访问；聚宽594份正文原始字节SHA-256全部匹配既有清单。已复现一个chunk的4段正文、3张内嵌图及JQ0594的379行编号文本，见[局部核实](docs/asset-review-2026-10-24/e-drive-source-check.json)。此前“F盘不可访问”只描述旧路径，原件可用性限制已解除；不改写历史源路径身份。269份阅读副本未发现必须长期保留的独立价值，但仍原位暂留REVIEW，待C01–C05后单独核定精确处置范围与授权，不把代表性复现说成全集精确重建通过。

## 权威状态与恢复入口

| 引用 | 本轮核实身份 | 用途 |
|---|---|---|
| `main` / GitHub `main` | `447c0e22edd414abe9ef1efcdfb6ad266c0bcb32` | 正式源码、合同、产品范围及已提交研究证据 |
| `backup/ssd-migration-2026-10-23` / 同名远端 | `34c8b4c7cf9236f316ebd661c175e12bdcbc26cb` | 比 main 多 1 个恢复说明提交；只增加 `docs/SSD-MIGRATION-RECOVERY-2026-10-23.md`，不是大量未跟踪研究文件的备份包 |
| 本轮整理分支 | `codex/research-asset-review-2026-10-24`，从上述备份 SHA 建立 | 本索引、决策队列、清理计划及机器清单；不合并 main |

远端 heads 已独立查询，见 [remote-baseline.json](docs/asset-review-2026-10-24/remote-baseline.json)。本项目只有 **1 个 SSD 备份分支**，附件中的 7 个、3 个分别属于其他项目。当前权威阅读顺序仍为 Owner 最新指令 → [CURRENT_STATE](docs/CURRENT_STATE.md) → R3.2 范围与消费者合同 → 专项 Acceptance → 最新资格事实；较早提案仅用于溯源。

## 按研究任务归纳

`TESTED` 只指列明的既有测试/离线审计或本轮局部身份检查；不代表投资效果、需求或真实供数已通过。研究状态与证据状态分别记录。本轮不重跑产品测试。

| ID / 主题 | 原问题与实际工作 | 已形成结论、原始证据和 Git 引用 | 研究状态 / 证据状态 | 后续价值与取代关系 |
|---|---|---|---|---|
| R01 竞品与买家需求 | 哪些发现、解释和回测路径值得交付？静态研究 8 组截图；复用竞品3现场操作、手册、留言及返回结果 | [三款竞品对照](docs/2026-10-15-COMPETITOR_STRATEGY_BACKTEST.md)、[闲鱼证据](docs/2026-10-14-XIANYU_EVIDENCE.md)、[当轮截图索引](docs/research/competitor-scope-2026-10-15.json)。C 盘原图 68 张；另有 1 个 ZIP。竞品3原批次 186 文件。文档在 main；原材料不在 GitHub | ACTIONABLE / INSUFFICIENT_EVIDENCE（本产品付费需求） | 功能路径存在与卖家宣传分开；没有本产品真实付款验证。资料仍适用于需求追溯，不需重做全面竞品研究。下一步由 Owner 选择具体结果/报价/使用验证 |
| R02 聚宽全文阅读 | “600条源码”有什么实际规则与缺陷？已静态阅读594份正文、557份不同内容，37份精确重复 | [FULL_REVIEW](docs/joinquant-full-review/FULL_REVIEW.md)、[594份索引](docs/joinquant-full-review/file-index.csv)、[合并语义记录](docs/joinquant-full-review/all-reviews.jsonl)、[原始身份清单](docs/joinquant-full-review/source-manifest.json)，均在 main。原始库现位于E盘，594正文哈希全部匹配，另3张独立PNG本次未重新核验 | CLOSED_WITH_EVIDENCE / NOT_TESTED（投资效果）；TESTED（原文身份） | 阅读已结束。保留最终知识与原件；年度记录冷归档。269份副本无已证明的长期独立保留必要，处置后置于C01–C05，暂留REVIEW。未验证收益不等于策略被实验否定 |
| R03 其他四个量化资料库 | 入门、QMT、中转、课程能提供什么？已结构盘点、有限静态抽样，未运行安装包或交易程序 | [本机资料基线](docs/LOCAL_RESEARCH_ASSETS.md)记录历史路径、编码和样本。五库历史合计877文件/4,282,580,626字节，含R02；现E盘五个根均可访问，未重数或核验其他四库内容 | PARKED / NOT_TESTED | 按具体需求取材即可；无必要为清理补读全部课程、展开二进制或运行源码。历史跨库三组精确重复已有记录，不扩展全盘去重 |
| R04 产品方向与范围演进 | 全天机会发现、策略、诊断、回测与交付形态怎样收敛？初始讨论→R2/R3→R3.2、Owner 决策及修订 | [R3.2范围](docs/MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md)、[运行规格候选](docs/MISHI_RADAR_R3_2_PRODUCT_OPERATING_SPEC_CANDIDATE_2026-10-19.md)、[Owner Decisions](docs/MISHI_RADAR_R3_2_OWNER_DECISIONS_2026-10-19.md)、[修订](docs/MISHI_RADAR_R3_2_OWNER_DECISION_ADDENDUM_2026-10-21.md)，main | DECIDED（已批准部分） / NOT_TESTED（需求与运行经济性） | 八策略、六维、H1、Web、当前扫描和真实现金回测的批准范围继续有效；旧“三种/七种/盘后优先”等建议已被取代。`FULL_DESIGN_NOT_FROZEN`，OD-3 数值仍 UNKNOWN，不重开已批准事项 |
| R05 DR01 当前池与停复牌资格 | 是否有目标日完整、可追溯证券状态？两轮来源调查保留官方导出、分页、闭市码反例、准上市页面及账本 | [首轮](outputs/dr01-current-2026-10-18/DR01-CURRENT-report.md)、[最终报告](outputs/dr01-current-unblock-2026-10-18/DR01-CURRENT-report.md)、同目录 `evidence/` / `sha256-manifest.json`；main。最终报告既有离线审计176断言，不是消费者功能测试 | INVESTIGATE / INSUFFICIENT_EVIDENCE（深市全量资格）；TESTED（离线一致性） | 沪市缺口已解决；深市 D=2026-10-16 完整停复牌的血缘及采集完成依据仍缺，结论 BLOCKED。零成交与闭市码不能代替状态。首轮被补充而非完全取代，后轮直接引用其原件，整组 KEEP |
| R06 S08资金来源与成本 | 日资金数值能否使用、覆盖多少、成本如何？固定20股五日样本、4股年度分页、旧 VIPDOC 包络调查 | [资金资格](outputs/s08-fund-universe-investigation-2026-10-17/s08-fund-source-qualification.md)、[全池与成本](outputs/s08-fund-universe-investigation-2026-10-17/s08-universe-and-scan-cost.md)、`evidence/local-input-hashes.json` / 原始响应，main | ACTIONABLE / INSUFFICIENT_EVIDENCE（全池与 PIT）；TESTED（既有定向样本） | DR04-P 后续已接受，旧“无公共无损接口”被取代；M、原始零经济语义与历史可知性未解决。保留原始两股完整年度响应及缺失/过期反例。41.08% 是旧单日包络减幅，不能套给全年并集5552股或当前 SLA |
| R07 DR02–DR06供需差距 | 现有供应能力离消费者合同还差什么？复用签名、历史审计和局部身份核对，整理当前/历史资格及最小请求 | [综合报告](outputs/dr02-dr06-consolidation-2026-10-19/DR02-DR06-consolidated-gap-report.md)、`evidence/baseline-and-reuse.json`；[DR04-M设计](outputs/dr04-minimum-consumer-contract-2026-10-17/dr04-minimum-consumer-contract-owner-review.md)；消费者合同均在 main，DR03 时间语义更新在 `447c0e2` | ACTIONABLE / INSUFFICIENT_EVIDENCE | DR04-P PASS/CLOSED 不扩展为 M、PIT、S08。DR03当前矩阵/历史成员、DR05逐日估值与旧版财报、DR06历史执行均有缺口。报告是日期快照，不重新审查另一仓库来宣告其现在状态 |
| R08 OD-1/OD-2规则及内核 | 八策略、信号时刻和现金模型是否按批准语义实现？A/B独立实施、修复、合成验证后受控整合 | [正式Acceptance](docs/OD1_OD2_OWNER_ACCEPTANCE_2026-10-23.md)。A=`a72c67901e1147f3e4c198207dea8dd56d59a542`，B=`fc02eff5a68b0bc408bc3a60b5b4f0ad272c6758`，整合=`b9a7fba6be9515fc3271eac7a7a97ab65f53e64d`，均可从 main 到达；外部独立/整合证据见下表 | DECIDED / TESTED（既有合成验收） | Owner PASS；167次执行/165个不同测试ID为既有记录。源码/测试/Acceptance长期保留；干净历史工作区可列清理候选，提交与审查差异仍可由 main 恢复。无下一阶段自动授权 |
| R09 暂停 WP-FX01 与 FX01A | 暂停界面文件身份不完整时，是否能独立接受只读结果合同？已接受8个合同交付文件，保留32暂停文件身份基线 | [FX01A Acceptance](docs/WP_FX01A_OWNER_ACCEPTANCE_2026-10-23.md)、`outputs/wp-fx01a-owner-acceptance-2026-10-23/paused-fx01-sha256.json`、`outputs/wp-fx01a-result-contract-2026-10-23/`；main中的合同提交 `87b653e6867286c277c60cc23c4174266fc04091` | DECIDED / TESTED（合同）；INSUFFICIENT_EVIDENCE（暂停文件实施前身份） | `PASS_WITH_LIMITATION` 不重写。不能用后补清单证明更早身份。旧15文件界面证据先 REVIEW；32文件不按“暂停”整体删除，当前12项有意改变、20项未变，恢复副本19/19身份匹配见本轮检查 |
| R10 WP-FX01B固定Fixture切片 | 合同如何经真实Web路径展示、关注和合成现金检验？现代码、浏览器/HTTP证据及两项修复已提交 | `9f83a2e`在 main；[当前证据](outputs/wp-fx01b-fixture-vertical-2026-10-23/)、[恢复清单](outputs/wp-fx01b-recovery-2026-10-23/pre-change-sha256.json)。聊天“独立验收 WP-FX01B”及外部复验结果记录 `PASS_FOR_OWNER_ACCEPTANCE`，184次执行零失败 | ACTIONABLE / TESTED（既有固定Fixture复验） | 原“没有独立验收记录”需区分：仓库没有正式Owner Acceptance，但外部独立复验确实存在。不能从询问“可以验收了吗”推定Owner已经接受。保留首次失败证据、修复后复验与恢复副本，等Owner决定 |

## 外部原件与结论的关联

下列路径仅是本轮可访问或历史记载的存储位置，不声称存在第二份持久副本。目录级身份及具体文件见 [asset-files.csv](docs/asset-review-2026-10-24/asset-files.csv)。本轮未复制、上传原始页面/图片、改动原库或清理任何 `.codex` 内容。

| 位置 | 关联研究 / 实测数与字节 | 保留方式 |
|---|---|---|
| `C:\Users\Administrator\Documents\竞品分析\` | R01；69 / 37,085,071，其中68原图34,022,804字节，另1个ZIP3,062,267字节 | 原图 KEEP。额外第69项已识别为竞品4 ZIP，包内7张图与保留目录逐字节等价；仅容器 DELETE_CANDIDATE，见 [等价证据](docs/asset-review-2026-10-24/zip-equivalence.json) |
| `C:\Users\Administrator\Documents\Codex\2026-10-13\3-a-http-124-221-98\outputs\` | R01；186 / 3,432,534 | 已结束批次 ARCHIVE 原位保留；报告与阶段观察是来源身份，不因材料名称/时效而丢弃 |
| `E:\BaiduNetdiskDownload\2020-2026聚宽600条源码\`及另外四库 | R02/R03；历史记录877 / 4,282,580,626，本次不重数 | Owner确认同一WD盘由F:改为E:；五根可访问，聚宽594正文哈希匹配。旧清单F路径保留历史身份，以相对路径映射到E；原件第二持久副本未验证，无需重读全库 |
| `C:\Users\Administrator\.codex\visualizations\2026\10\22\01a16446-92f1-7fb1-b25f-112797c67cc7\final-integration-2026-10-23\` | R08；35 / 275,952；`final_state.json`记录整合闭环 | ARCHIVE；Acceptance中的原链接继续保留，不能随worktree一起删除 |
| `C:\Users\Administrator\.codex\visualizations\2026\10\22\01a163dd-e5fd-7ad0-919e-edf98f203aca\g01-g07-final-reacceptance\` | R08；117 / 1,439,210 | ARCHIVE独立正反例和审查证据；不清理会话或父目录 |
| `C:\Users\Administrator\.codex\visualizations\2026\10\23\01a16819-10cb-7d40-8978-4957695ac0be\wp-fx01b-independent-review\` | R10；36 / 2,062,908 | KEEP首次审查、失败CSV/小N反例、F5/F6独立证据 |
| 上一行同一聊天目录下 `wp-fx01b-reacceptance\` | R10；12 / 816,607 | KEEP；`evidence/review-result.json`、`verification.json`、`unittest.log`是Owner可用的复验证据；不复制整套证据到本分支 |

## 有价值但尚未充分利用的发现

以下6组均已被旧记录发现；本轮价值在于把它们接回当前决策，**不是新增经验证的投资发现**。

1. **机制去重优于源码数。** 聚宽594份正文不等于594个机制；37份精确重复已有canonical关系。保留最终语义记录即可发现行业广度（JQ0149/JQ0436）、板块强股（JQ0260/JQ0408/JQ0592）、业绩预告（JQ0362）等具体参考，不再逐年重读。
2. **源标题与执行路径冲突是可复用反证。** JQ0358“一进二”实际条件、JQ0361查询布尔表达式、JQ0364占位模板及缺模型权重的AI脚本，说明不能把宣传或定义函数当成已启用能力；对应原文身份与语义记录应长期保留。
3. **资金请求预算不能只看一次筛选减幅。** S08旧单日41.08%减幅与年度5552股并集同时存在；任意股诊断、自选、持仓等需求还扩大并集。成本线索可供以后OD-3预算选择，不能冒充生产SLA或新策略失败。
4. **缺失与失败本身有信息。** 五日样本90个非零/10个缺日、41个原始零、深市闭市码反例分别说明过期、缺失、原始零、失败须保持区别；这些证据不应当缓存删除。
5. **截图“69对68”有精确解释。** 多出的文件是已展开7图的ZIP，而非漏读的一张独特图片；无需把全部图重新语义审阅即可确认一个容器清理候选。
6. **FX01B已有独立复验、尚缺正式Owner收口。** 现有184次执行及小N/EMPTY下载证据可以直接支持Owner决定，无需再组织一次完整功能审查；它不覆盖真实数据、R3.2完整产品或发布。

## 使用和停止边界

后续先按本表定位主题及最终结论，再按JQ ID、报告相对路径或提交SHA进入原件。待决事项集中在 [决策队列](RESEARCH_DECISION_QUEUE.md)，精确清理集合及恢复条件见 [清理计划](ASSET_RETENTION_AND_CLEANUP_PLAN.md)。本轮没有发现需要重开已批准OD-1/OD-2或重做594份阅读的理由，也不授权继续研发、市场数据请求、供应验证或发布。
