# DR01-CURRENT 来源资格结论

本轮结论为 **BLOCKED**。没有进入供应能力或 Mishi 产品实现，没有形成 PASS_CANDIDATE。
新增内容仅为本目录中的公开来源原始响应、资格调查脚本、审计结果及报告；未提交、推送或发布。

| 状态字段 | 结果 |
|---|---|
| `CURRENT_VERDICT` | `BLOCKED`：当前日终消费者资格尚未成立。 |
| `SOURCE_QUALIFICATION` | `PARTIAL / NOT_PASSED`：补齐深市独立数量及风险名单；剩余缺口是目标已完成交易日的证券资格状态有效性。 |
| `UNIVERSE_COVERAGE` | 已有官方全导出共 5,226 条：沪主板 1,702、沪科创板 618、深主板 1,495、深创业板 1,411。剔除已确认 CDR 1 条后观察到普通股票代码 5,225 个；**合格 CURRENT_SCAN 分母仍 UNKNOWN**。 |
| `SECURITY_TYPE_STATUS` | 官方公司概况明确 `SH:689009 / SEC_TYPE=科创CDR`，普通 A 股范围排除。`STOCK_TYPE=8` 是科创板枚举，不能直接解释为普通股票类型。风险名单中的沪 B 股 1 条、深 B 股 3 条单独排除。身份始终使用交易所＋代码。 |
| `LISTING_STATUS` | 观察到沪 A 风险警示 83 条、深 A 风险警示 115 条；深退市整理 `301139 / 元道退` 1 条。沪两类退市整理接口均正常返回空名单，但缺业务有效日，不能认证目标日为零。全市场停复牌状态尚未取得目标日完整证据。 |
| `DATE_SEMANTICS` | 深证券表、风险名单、退市整理表均明确标注 `2026-10-16`。沪统计表明确 `TRADE_DATE=20261016`，但沪证券名单及状态名单的 `queryDate` 为空、日期元数据未提供；统计表的日期不能移植给另一份名单。HTTP Date、获取时间及 XLSX 创建时间均不充当业务日。`601059`、`601198` 的 `DELIST_DATE=20261019` 仍保留，未提前当作退市。 |
| `IMPLEMENTATION_STATUS` | `NOT_STARTED_SOURCE_GATE_FAILED`：未新增 DR01 生产接口或空壳实现，未改旧名称解析、DR04-P、DR06、DR02、DR04-M 或 Mishi 产品代码。 |
| `TEST_RESULTS` | 离线原始证据审计 **89 项检查通过**，同一数据完整执行两次、输出逐字节一致。检查包括原始响应重解析、总数、代码身份/重复/冲突、必填身份字段、上市日期、风险名单集合、CDR、未来退市及来源哈希。它们是证据完整性检查，**不是 89 项 DR01 功能测试**。未实现适配器，故未运行其单市场失败、陈旧快照、UNKNOWN 等故障注入或产品回归验收。 |
| `LIVE_VALIDATION` | 复用上轮 3 份完整官方名单，新取 24 次公开 HTTP 响应，含独立数量/日期、完整深市风险导出、沪风险及退市整理全名单；全部保留原始响应和哈希。非单股验证，但也不是全市场消费者运行验证。另一次 Firecrawl 状态预检包含 2 次账户请求尝试，失败并计入预算；本轮保守 HTTP/TCP/TLS 预算 **78/100 单位**。来源探测没有重试、重定向或并发。 |
| `CONFIRMED_BLOCKERS` | ① 沪证券集合和关键状态尚无可核验的业务有效日，无法认证其对应目标 `2026-10-16` 日终；② 现有停复牌公共接口明确只支持请求当天，旧日期失败关闭，不能认证目标已完成交易日的全市场停复牌状态。不是“完全没有状态来源”，也不是源更新时间字段未知本身导致失败。 |
| `SCOPE_DEVIATION` | `NONE`：没有把全量 mootdx 双源对账作为新 Gate；未因本轮结论宣称历史 DR01、DR02 或整体 Mishi Gate 通过。供应 HEAD `9543d03310b25be9963227a2a226366de04276ec`，已核对冻结文档及相关供应源码哈希与上轮一致。 |
| `OWNER_ACCEPTANCE_READY` | `NO`：可提交来源调查阻断报告，尚无 DR01 当前能力候选可供功能验收。 |

必要事实是：**观察到的证券资格状态是否确实对目标已完成交易日有效，并覆盖该日全市场停复牌状态**。普通来源获取时间未知可以如实披露；这里缺失的是消费者计算所需的有效状态，不能用周末观察值代替。

最小解决方案：取得一份带明确业务日的沪深完整证券资格快照，或补足现有官方证券/风险来源的有效日说明及目标日完整停复牌证据；与已取得的官方代码集合对齐后，再进入获授权的最小适配。不需要历史证券库、新平台、全量 mootdx 对照或修改消费者合同。需要的是可靠证据，而非 Owner 口头认定日期。

1. **DR01 当前能力是否真正可供 Mishi 使用？** 否；目前可复用的是有边界的官方证券枚举及状态观察证据。
2. **哪个必要事实阻止完成？** 上述目标交易日资格状态的完整性和有效时点仍未证实，尤其沪市状态及全池停复牌。
3. **是否形成可提交 Owner 验收的能力候选？** 否；来源 Gate 失败，依授权停止编码。

## 直接证据

- [机器审计结果](evidence/qualification.json)、[双次执行验证](evidence/verification.json)、[请求账本](evidence/requests.json)、[离线复核脚本](evidence/audit.py)。
- 深市证券表：`003-szse-list-metadata.bin` 的 `metadata.subname=2026-10-16`、`recordcount=2906`，与复用的完整 XLSX 一致。[官方证券表入口](https://www.szse.cn/market/product/stock/list/index.html)
- 深市风险板：`014-szse-risk-metadata.bin`、`015-szse-risk-export.bin` 共 118 条，其中 115 A＋3 B；`018-szse-delisting-period-metadata.bin` 选中 tab2 后返回 1 条。**未选标签的零条只是占位，不能用于资格判断**。[官方风险警示板及定义](https://www.szse.cn/disclosure/listed/warn/index.html)
- 沪市风险板：`021-sse-main-risk.bin` 为 71 条（70 A＋1 B），`023-sse-star-risk.bin` 为 13 条；`022`、`024` 为正常空响应。四份响应均无业务日；数量逐一匹配各自 `pageHelp.total`。[官方主板风险警示板](https://www.sse.com.cn/disclosure/listedinfo/riskplate/)、[科创板风险提示](https://www.sse.com.cn/disclosure/listedinfo/starriskplate/)
- 证券类型：`011-sse-689009-overview.bin` 的 `SEC_TYPE=科创CDR`；官网脚本 `007-sse-stock-list-script.bin` 区分 A/B/CDR 类型，并明确 `STOCK_TYPE` 的板块选项。[官方公司概况](https://www.sse.com.cn/assortment/stock/list/info/company/index.shtml?COMPANY_CODE=689009)
- 日期边界：`020-sse-dated-statistic.bin` 的 `TRADE_DATE` 仅属于统计表。[官方统计入口](https://www.sse.com.cn/market/stockdata/statistic/)
- 现有公共接口：`D:/Dev/Projects/chstockdata/src/chstockdata/suspension.py:281` 明确历史/未来请求失败关闭；`tests/test_suspension_source_semantics.py` 现有测试检查最新事件不能证明历史停牌或未停牌。`delisting.py:422` 明确未命中终止上市名单不证明当前在市或可交易。本轮仅静态核对，未把已有 mock 测试当作市场验证。
- 复用原始证据保存在 `evidence/reused/`，与前轮哈希清单核对通过。前轮 mootdx 样本存在 `SH:000001=上证指数 / SZ:000001=平安银行` 等裸代码碰撞；已复用该结论，没有重复全量采集。

预算说明：公开来源每次 HTTPS 尝试预留 3 单位（HTTP、TCP、TLS），24 次计 72 单位。离线检查已安装的 Firecrawl CLI 1.18.5 `dist/commands/status.js` 后确认一次状态预检内部并行尝试了队列状态、余额两个账户请求，各无重试，另预留 6 单位；这些不是交易所来源采集。合计 26 次 HTTP 尝试、78 个保守预算单位。一次自动审批服务用量错误发生在执行前，重试审批后才执行，未重复来源请求。前轮 12 个保守预算单位只复用证据；即便并列计入也为 90，未超 100。未耗尽预算；停止原因是上述来源语义缺口。
