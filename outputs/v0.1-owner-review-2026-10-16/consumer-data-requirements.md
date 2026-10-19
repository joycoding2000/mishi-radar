# Mishi Radar V0.1：chstockdata 消费者数据需求

日期：2026-10-16（北京时间）。状态：**CONSUMER_REQUIREMENTS_REVIEW / OWNER_REVIEW**。本报告请求数据能力，不规定供应项目如何实现，不构成修改接口、测试、Issue或发布计划的授权。

## 版本和验证边界

| 对象 | 核查基线 |
|---|---|
| Mishi `CURRENT_SHA` | `678872568c7425b773a0059ae551adc55b3040a3`；R2及资金附录另以[散列](evidence/mishi-source-hashes.json)固定 |
| chstockdata v0.4.2 | 本地 annotated tag 解析到提交 `17af23fe8183f740150dc01dd877473afe3911b7` |
| 读取工作区 | `D:\Dev\Projects\chstockdata`，HEAD `0dc85e3e43588c5781771486a3c6f80c4be7714f`；`src/`、`tests/`、`pyproject.toml`、`MIGRATION.md`相对tag无差异；HEAD后续差异为README/发布说明 |
| 冻结副本 | `chstockdata-frozen-v042`是更早的`42bd44ef…`工作现场且有未提交内容；只用来识别版本，不作为已发布接口基线 |
| 检索方式 | 两个供应工作区CodeGraph均报“unable to open database file”；随后仅定向读取公开导出、相关实现、测试和合同，未修复索引、未重做长期审计 |
| 离线验证 | 6个既有测试文件，**72 passed in 6.57s**；[日志](evidence/supplier-offline-tests.txt)。禁用pytest缓存/字节码，临时文件全部在本输出目录；未新增或修改供应测试 |
| 固定样本 | [4只本地日线](evidence/local-consumer-samples.json)：600519、300401、002208、000002，经已导出`load_vipdoc_daily(root=...)`读取；均截至**2026-09-22**。另有[资金文本fixture](evidence/fund-flow-formatting-example.json)，明确不是市场实测 |
| 未做的资格声明 | 网络请求0、全市场采集0；未刷新历史包。当前行情/资金供应在线可用性、全市场覆盖/时延、商业展示许可与费用均**未知**，离线通过不替代这些证据 |

支持状态含义：**真实支持**＝公开合同/已读实现明确，且指出验证层级；**部分支持**＝只满足部分字段、时间或范围；**不支持**＝现有公开合同明确无该能力或缺少必需返回；**未知**＝没有足够证据。功能整链状态不由某个字段可取直接升级为支持。

## 公共接口与字段合同

以下以包顶层导出为稳定消费者入口；内部/桥模块可调用不等于已承诺的顶层数据合同。来源均为本机v0.4.2对应源码，不依赖宣传推断。

| 数据组 / 入口 | 原始数值、单位、来源和时间 | 缺失/状态与限制 | 支持判断 |
|---|---|---|---|
| 原始日线：`load_vipdoc_daily(code,start,end,root=...,market=...)` | DataFrame含Date/OHLC/pre_close/Volume/**Amount**；已限定股票价格元、量股、额元。来源本地TDX官方盘后包；Date是业务日，pre_close是文件前一根原始Close，非除息参考价 | 文件无→None，窗内无→空帧；无统一FetchResult/逐行采集时间；新鲜度与完整性需另检查。4样本真实读到Amount且有多年历史，但末日旧 | **真实支持：本地数值读取**；当前新鲜度/全池覆盖未知 [A1] |
| 路由日线：`fetch_daily_bars(code,start,end)` | FetchResult，必需Date/OHLC/Volume，pre_close按源可选。默认VIPDOC→mootdx→Sina；`metadata.data_as_of`来自返回日线；获取时刻≠业务日 | **默认VIPDOC适配器主动去掉Amount**，故不能由OHLCV假定有成交额。VIPDOC/Sina量=股，mootdx=`provider_native_unknown`，混源=`mixed_provider_native`；成功仍可stale/partial；源端observed_at为空 [A2] | **部分支持**；需成交额时现有本地公开reader是可复用路径，不必先要求新接口 |
| 缓存日线：`get_ohlcv_frame_cached(symbol,curr_date)`；文本`get_stock_data` | 前者数值帧，最近最多800根；后者文本/CSV及指标说明。后者不是README示例暗示的通用DataFrame合同 | 缓存有写入副作用，本次未调用该缓存入口。800根/在线回落不保证3年+预热；文本非首选计算输入 [A3] | **部分支持** |
| 复权：`get_adjusted_bars(...,adjust,period,daily_bars=...)` | AdjustedBars含数值frame、raw/qfq/hfq、日/周/月、日线源/因子源/锚/事件范围；新浪事件因子；量额不跟价格缩放 | QFQ锚可随新事件改变；不能用复权绝对价成交，或跨锚对账；因子缺失抛错，不把raw伪装复权；不提供完整历史数据版本库 [A4] | **部分支持：分析序列**；完整组合现金/分红会计仍属消费者模型 |
| 当前报价：`get_realtime_snapshot(ticker)`；`fetch_realtime_quotes(codes,quote_fetchers,quote_number=...)` | 字典含price/OHLC/last_close（元）、amount_wan（万元）、turnover_pct（百分数）、PE/PB、市值（亿元）、涨跌停价；腾讯→mootdx→新浪。facade的observed_at是本次获取时刻 | 该快照**未输出累计Volume及交易所行情时间**；不得用observed_at当成交时间。腾讯空槽部分转0；回落源部分估值为None。结构化批量接口需注入fetchers，不等于开箱即用全市场股票清单 [A5] | **部分支持**；最新价不能替代S02盘中量或盘中资金 |
| 个股资金：`get_fund_flow(ticker,curr_date,include_history=True)` | **str**；TDX L1重构当前主力/小单、5日分档、最近最多20日日频历史；失败可降级新浪总净流/r0。展示是元÷10000后**整数“万”**，来源/方法有文本标签 | `curr_date`只裁历史段；TDX“当前”段仍是抓取时点。TDX和新浪主力定义不同，混用不能视为同源。部分missing经过`or 0`，返回缺失文案与正常数据也不同于统一FetchResult；无逐行原始值/缺失码/实际可知时间 [A6] | **部分支持：解释性文本**；**不支持现成的无损同源长期S08数值合同** |
| 板块资金：`get_board_fund_flow(board_type,period,top_n)` | 字典rows含code/name/main_net_yuan（元）/main_net_yi（亿）、source、带时区observed_at、limitations；东财bkzj；today/5d/10d，行业/概念/地域 | 无任意历史as-of；无四档、占比、领涨股和分钟曲线；没有单独源交易日期/发布时间。total_count与有效返回数应分开，不能视top_n为全池覆盖 [A7] | **真实支持：有限板块快照合同**（本轮离线测试，在线未知）；其余不支持 |
| 行业/成分：`get_concept_blocks`、`get_industry_comparison` | 前者F10所属行业/地域/风格/概念混合文本，附TDX板块快照；后者TDX或新浪最新排名文本，明确“请求日仅归档” | **不是单一分类全股票成员表，不是历史生效区间**；TDX/东财/新浪分类不能直接拼接。README明确未包含申万行业历史 [A8] | **部分支持：当前背景**；**不支持S06所需历史成员合同** |
| 财务：`get_balance_sheet/get_income_statement/get_cashflow`；`get_free_financial_indicators`；`get_fundamentals` | 三表是带CSV的str；报告期/公告日可带入过滤；原始项目值/同比，结构化指标仍是格式化str，ROE百分数、现金流/利润为倍数。金额源值没有完整逐字段币种/单位schema；F10为最新快照，报告期是参考期 [A9] | 日期过滤会排除未来/缺公告日；**无法凭过滤函数证明供应商保留旧修订版**。新浪每次请求最近20期、过滤后最多8期，不是完整历史档案。ROE年报与TTM定义需与S07约定一致 | **部分支持当前价值/质量**；历史可知版本和全池质量未知 |
| 估值：`get_valuation_history(ticker)`；当前PE/PB见报价 | **JSON字符串**，可结构化解析；有status/source/observed_at/latest_date、latest metrics、3y/5y/all分位和history覆盖摘要 | 实现内部读取日估值，但**返回没有逐日原始估值序列，也没有as-of参数**；不能据函数名当作历史PE DataFrame。亏损/样本不足明确标不适用；分页/截断披露 [A10] | **真实支持：最新值及分位摘要合同**；**不支持据此直接重建S07历次行业排名** |
| 日历/停牌/退市：`fetch_trading_calendar`、`fetch_suspension_info`、`fetch_delisting_status`、`fetch_tradability` | FetchResult提供日期/状态、来源、获取时间及限制。日历可复用；退市有部分官方事实；当前停牌是最新事件快照 | 历史/未来停牌请求fail closed；`tradable=None`不等于可交易。`tradable=True`也不承诺完整IPO/上市生命周期/ST/涨跌停等资格；无公开完整历史证券主表 [A11] | **部分支持**；**不支持F6全市场完整PIT资格** |
| 历史开盘：`fetch_historical_opening_evidence` | R2.1、[09:30,09:31)正交易活动+官方停牌证据，含UNKNOWN/冲突 | 明确认证仅8证券（6 ETF及688432/000002两个股票控制），不是全市场A股通用能力；不证明严格09:30成交或排队；不补齐历史ST/全天停牌/PIT资格 [A12] | **部分支持限定样本**；不得用另一消费者的验收替代Mishi资格 |
| 全市场证券范围/刷新合同 | `resolve_ticker`可解析名字，已有报价接口可对传入代码取值 | 包公开导出未给完整当前/历史证券主表合同（市场/板块/上市退市/ST生效）；名称缓存或本地.day存在不证明资格。受控全池刷新覆盖/预算/时点未测 | **不支持现成完整主表合同；运行能力未知** |

### 所有数值组的最小消费者约束

同一字段应能获得：证券ID及市场、业务日期/统计窗口、原始数值、单位/币种、源/方法版本、源时间（若不可得须明确未知）、获取时间、缺失原因、覆盖/缓存/修订状态。原始值可保留来源单位，Mishi转换时记录比例；百分数与比例、元/万/亿、股/手不能凭字段名猜。

结构化接口按`metadata.request_status`判定，再检查stale/partial/limitations及逐股字段。cache-only可能`attempts=[]/final_status=skipped`但请求可成功；不能只看`succeeded`或HTTP 200。资金/财务等legacy字符串**没有同等统一合同**，正常无记录、缺字段、请求失败必须分别处理。对缺失分母、未知时点或换源数据不合成完整评分/排名。

## S01–S08 与 F3–F6 逐项需求

共同股票范围是现有策略提案的**沪深A股：主板/创业板/科创板**；北交所/ETF不作为本策略包默认范围。共同过滤需当时ST/退市整理/停牌、上市历史≥120交易日、近20日平均成交额≥3000万元；这些阈值仍是提案。回测股票范围必须包含历史曾合格而今天已退市的股票，不能只抓今天名单。

共同更新：盘后确认日线/日终快照；盘中只用有明确时点的当前暂态，自动频率未知、不得先承诺秒数。共同历史目标：近1年/3年/自定义是**目标**，实际区间必须等各字段覆盖；还需指标预热，不能悄悄截短。下表窗口为现有公式的输入需求，不新增策略公式。

| ID | 必需字段、范围、更新/跨度 | 已有公共接口与状态 | 缺口影响 / 最小数据能力请求 |
|---|---|---|---|
| S01趋势强势 | 价、MA20/60、20/60日收益、同日基准收益、共同过滤；全合格池横截面排名。60日收益至少61个收盘；盘后每日、盘中暂态；回测1/3年+预热 | A1/A2/A4价量与A5当前价；指数可用本地reader显式market区分同码。**部分支持** | 缺全池证券资格/基准覆盖/一致复权会影响超额与百分位；请求当前及历史池、证券化基准ID、覆盖与数据版本。Mishi自行计算均线/收益/百分位 |
| S02平台放量突破 | 前20完整日高低/量、前5均量、当时价格和累计量、前平台上沿；共同过滤。盘中量与历史量须同单位；1/3年+预热 | A1/A2历史OHLCV；A5报价无累计Volume、无源行情时间。**部分支持** | 盘后可由合格历史量算条件，盘中是否放量缺标准输入；请求明确累计Volume、源业务日/时点、单位、确认/暂态状态。不能用成交额或时间比例推算全天量 |
| S03强势回调再启动 | MA20/60、距MA20、前20日高、昨日高、60日超额与共同过滤；观察/确认分开。日更/盘中暂态；1/3年+预热 | A1/A2/A4/A5，**部分支持** | 共用S01数据；请求同一历史版本/当前时间，防止观察条件被算成确认信号。不需新供应商策略评分 |
| S04超跌修复 | 截至昨日5日收益、MA5/20、昨高、当前修复幅度、共同过滤；日更/盘中暂态；1/3年+预热 | A1/A2/A4/A5，**部分支持** | 复权、除权与极端交易状态影响假超跌及成交；请求交易状态和价格基准，Mishi算修复条件 |
| S05低波稳健 | MA60及5日前MA60、60日收益波动、日成交额/收益计算Amihud、共同过滤；全池百分位。斜率约需65日价格，波动还需前收盘；日更；1/3年+预热 | A1已有数值Amount；A2常用路由无Amount且量单位可未知；A4复权。**部分支持** | 默认路由无法直接计算日均额/Amihud。请求稳定可消费的同日原始Amount（元）及缺失/零成交区别；可确认沿用现有A1合同，无须指定新增API。不得用Close×Volume替代真实成交额 |
| S06板块强股 | 单一分类ID/版本、每股行业、有效起止日；成员全池MA20广度、20日平均超额、行业/个股排序、每行业上限；当前每日、历史分类变更时；1/3年+S01预热 | A8仅当前背景，A1/A2价格可复用。**部分支持背景；不支持完整策略数据合同** | 当前成员矩阵不足则连当前60%广度分母也未确认；历史成员缺失阻断同口径历史筛选/退出。请求完整当前成员表与生效区间历史、分类变更/无行业原因。S06首发方向不降级 |
| S07价值质量 | 非金融股，正PE/盈利/经营现金流、ROE阈值；同日行业内低PE/高ROE百分位，20交易日调仓。报价/估值日更，财报按公告更新；历史1/3年须含TTM/平均权益基期及旧版本 | A5/A9/A10当前字段基础存在，A8行业不足；**部分支持当前输入；历史未知/缺公开序列** | 请求数值PE类型、利润/OCF/权益及ROE定义、单位、报告期/公告可知时间/修订版本、金融分类与行业历史、逐日估值as-of。日期过滤不等于保存历史旧值。可行性供Owner决定，不把S07当成已取消 |
| S08日度资金持续流入 | 同一供应商/方法每日main_net、date、同日Amount、MA20；近5日≥3正且总正、sum(net)/sum(amount)排序；退出需近3日净流出。全合格池，每日确认；当前至少5日，历史回测1/3年+预热 | A6最多20日文本、舍入/缺值转零、当期段非历史、降级换定义；A7板块流不是个股序列。**部分支持展示，不满足完整数值/历史合同** | 请求不舍入带缺失码的逐股逐日净额、供应商/方法/单位、实际可用时间、5日连续覆盖与长期区间、同源降级语义。S08首发不降级；不从最多20日推导3年历史 |
| F3完整诊断 | 任意支持股票（不只榜内）复用S01–S06/S08实际指标、风险/失效、行业/日度资金、K线；若采用竞品4式六因子，再加S07价值/质量；当前时点+预热+关注/历史信号区间 | A1–A11按字段部分支持；**完整输入部分支持** | 请求字段级时点/缺失/来源，确保多页使用同一批数据；诊断分、策略分由Mishi定义。若价值/质量缺失，应未知，不能造50分；Owner完整诊断方向保持 |
| F4市场/行业/资金 | 基准指数、全池/行业汇总及覆盖分母、单股/板块日度资金、5日对照；每日确认。若纳入I层需个股/板块分钟窗口、大单定义与增量；若展示120日则需真实120日历史 | A1/A2/A7/A8当前部分；A6仅最多20日文本。**日度部分支持；分钟/逐笔/身份不支持** | 请求行业一致性和资金源时间；盘中另需买卖方向、大小单阈值/单位/窗口、修订与缺测。120日不是接口现成承诺，不为匹配截图擅加首发硬范围 |
| F5自选/跟踪 | 当前自选与关注时池、快照、之后价格/排名/条件、首次关注时间；自首次真实发布积累、不可伪补。日报需当时池每股当日/前日/5日资金、覆盖/生成时间；手工仓另需价/成本日期语义 | A1/A5可供估值，A6资金受限；**数据部分支持**。用户自选/排名/持仓记录由Mishi保存，不是供应商缺少业务API | 请求稳定证券ID、价格/资金批次时间与历史更正。报告快照、用户权益、持仓数量/成本、提醒均不向chstockdata索要；精确历史排名由Mishi从真实全池结果保存 |
| F6单股/组合回测 | 原始交易价与分析复权序列、基准、交易日历、历史股票池/ST/停牌/上市退市、历史行业/资金/财报（随规则）、分红送转、涨跌停参考/交易制度生效、缺失/版本；日频1/3年+预热，组合逐日 | A1/A2/A4/A11及公司行为API可复用，A12仅限定样本；**部分支持，不足以资格确认完整R2回测** | 请求可追溯的历史资格/限制/公司行为、支持证券与区间声明；制度/费用表由Mishi明确来源及版本。日OHLC不证明队列成交，不拿开盘样本接口覆盖全池；失败成交/现金/持仓/绩效属于Mishi实现 |

## 向供应项目提出的最小能力需求（仅清单）

| 请求ID | 最小数据能力 / 可回答方式 | 具体受影响功能 | 当前结论 |
|---|---|---|---|
| DR01 证券范围与资格 | 提供/确认完整当前证券表及历史上市、退市、ST/退市整理、停复牌有效区间，市场/板块和缺失范围；不能提供也需明确范围 | 所有共同过滤、历史排名、F6组合 | 当前历史完整合同**不支持**；当前池覆盖未知 |
| DR02 价量额与基准 | 确认已有`load_vipdoc_daily`可稳定提供股票/基准原始价、股、元及更新/覆盖说明；说明路由换源的单位。盘中另给累计量和源时间 | S01–S06/S08、F3–F6 | 本地原始价量额**真实支持**，最新/全池/盘中字段**部分或未知**；不强制改现有接口 |
| DR03 行业成员 | 一个固定分类的当前完整成员与历史生效区间、分类版本和未知项 | S06、F3/F4行业、S07、F6行业约束 | 完整合同**不支持**，不能用最新排行替代 |
| DR04 日度资金 | 按股票/日期无损数值净额、单位、缺失原因、方法/源标识、可知/确认时间；当前5日覆盖及可回测的明确连续区间 | S08、F3/F4、F5日报、F6资金规则 | 顶层文本接口**部分支持**；长期同源数值合同不支持。桥模块有字典方法，但是否作为受支持消费者合同需供应Owner确认，不自行转向私有抓取 |
| DR05 财务估值（若Owner选择S07/六因子价值质量） | 数值财务/估值、报告期、公告时间、修订可知版本、ROE/PE定义、金融股/行业、历史区间 | S07及对应F3/F6 | 当前数据基础**部分支持**；历史修订覆盖未知，公开逐日估值返回不足 |
| DR06 历史交易输入 | 历史资格/限制价格/公司行为覆盖和版本；明确能证明的可交易性，未知不当可成交 | 所有宣称可回测策略、手工仓公司行为（若纳入） | **部分支持**，R2.1认证不能外推 |
| DR07 盘中资金（仅候选） | 如可提供已加工指标，说明逐股/板块覆盖、时间窗、大小单/方向定义、买卖额/净额、单位、延迟/频率、缺失/回填及历史；另确认使用许可/费用 | I层资金雷达/自选短窗/分钟图 | 当前公开能力**不支持对应分钟/逐笔合同**；许可/费用未知。不开新渠道、不自建L2 |

以上不是要求供应项目必须扩建；可以答复“已由现有API满足”“限定区间支持”“不可提供”或“需另行立项”。本次未发Issue、未联系他人、未安排其发布。Mishi的业务计算/快照不转嫁给独立供应项目。

## 缺口的产品处理边界

S06/S08/F3是已确认首发方向。若DR03/DR04/DR06仍不满足，Owner可对历史区间、明确有限支持或数据路径/发布时间作决定；本报告**不选择方案**，也不把数据不足写成策略不值得做。当前静态/样本证据不足以宣称“chstockdata v0.4.2单独满足全部首发合同”。

盘中资金与日度资金分别出状态。日度降级为另一供应商时须分段/拒算同源策略，不能把不同定义接成连续序列；本金/成交额零与missing分开；机构身份不在现有数据证明范围。

### 只读代码与测试追溯

- A1：[本地reader与单位](D:/Dev/Projects/chstockdata/src/chstockdata/vipdoc_history.py:98)、[公开入口](D:/Dev/Projects/chstockdata/src/chstockdata/__init__.py)；4样本见上方JSON。
- A2：[schema/Amount/单位合同](D:/Dev/Projects/chstockdata/src/chstockdata/daily_bars.py:23)、[默认适配器去掉Amount](D:/Dev/Projects/chstockdata/src/chstockdata/daily_bars.py:294)、[既有合同测试](D:/Dev/Projects/chstockdata/tests/test_daily_bars_contract.py)。注：自定义注入适配器可能保留额外列，不代表默认路由提供Amount。
- A3：[公共缓存帧的800根边界](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:2670)、[get_stock_data签名](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:2785)。
- A4：[复权合同](D:/Dev/Projects/chstockdata/src/chstockdata/adjusted_bars.py:1)、[入口和元数据](D:/Dev/Projects/chstockdata/src/chstockdata/adjusted_bars.py:513)。
- A5：[腾讯字段](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:1290)、[快照字段](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:1574)、[结构化批量入口](D:/Dev/Projects/chstockdata/src/chstockdata/quote_chain.py:144)。
- A6：[资金入口/舍入/降级](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:7339)、[20日桥参数](D:/Dev/Projects/chstockdata/src/chstockdata/tdx_bridge.py:184)、[原测试](D:/Dev/Projects/chstockdata/tests/test_astock_tdx_fallback.py:51)。本轮fixture：真实输入49元和missing都可显示0万；未改代码。
- A7：[板块资金合同](D:/Dev/Projects/chstockdata/src/chstockdata/board_flow.py:1)、[离线测试](D:/Dev/Projects/chstockdata/tests/test_board_flow.py)。
- A8：[当前归属](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:7113)、[当前行业排名](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:8030)、[README历史边界](D:/Dev/Projects/chstockdata/README.md)。
- A9：[财报20期/公告过滤/8期返回](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:3344)、[财务指标文本与口径](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:3568)、[PIT过滤](D:/Dev/Projects/chstockdata/src/chstockdata/point_in_time.py:83)、[财务口径测试](D:/Dev/Projects/chstockdata/tests/test_astock_financial_yoy_alignment.py)。
- A10：[估值入口](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:5214)、[实际返回摘要](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:5419)、[估值测试](D:/Dev/Projects/chstockdata/tests/test_astock_margin_valuation.py:245)（本轮静态阅读，未列入72项运行）。
- A11：[历史停牌失败测试](D:/Dev/Projects/chstockdata/tests/test_suspension_source_semantics.py:30)、[派生可交易性](D:/Dev/Projects/chstockdata/src/chstockdata/tradability.py:115)、[FetchResult语义](D:/Dev/Projects/chstockdata/src/chstockdata/fetch_result.py:145)。
- A12：[8证券认证范围](D:/Dev/Projects/chstockdata/src/chstockdata/opening_evidence.py:42)、[开盘约束接口](D:/Dev/Projects/chstockdata/src/chstockdata/opening_evidence.py:425)、[限定开盘测试](D:/Dev/Projects/chstockdata/tests/test_historical_opening_evidence.py)（静态阅读）。

`DATA_CONTRACT_GAPS=DR01–DR07_RECORDED; V042_PARTIAL_INPUT_SUPPORT; FULL_LAUNCH_DATA_QUALIFICATION_NOT_ESTABLISHED`

`FINAL_VERDICT=OWNER_REVIEW; NO_SUPPLIER_CHANGES; NO_IMPLEMENTATION_AUTHORIZATION`
