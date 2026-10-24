# mishi-radar 资产保留与清理审查方案

2026-10-24（Asia/Shanghai）。**CLEANUP_AUTHORIZED = NO。** 本轮只读取、归纳、统计、提交并推送本整理分支；未删除文件、分支、worktree或stash，未执行gc/prune/reset/clean，未清理Codex会话或工作区，未改变main及正式研究结论。

## 基线、范围与计量

- 正式main与GitHub main：`447c0e22edd414abe9ef1efcdfb6ad266c0bcb32`。
- SSD备份本地与远端：`34c8b4c7cf9236f316ebd661c175e12bdcbc26cb`；多于main的唯一提交是恢复说明，保持KEEP_ARCHIVE。
- 本轮分支：`codex/research-asset-review-2026-10-24`，基于SSD备份；开工前tracked/untracked状态为空。本轮新增文档和证据不算历史资产，也不进入清理候选。
- 只审查mishi-radar、3个登记历史worktree、已有研究索引明确引用的2个C盘原材料目录和4个验收证据目录。没有扫描其他项目或整个`.codex`；本项目不存在`.codegraph/`。

实测历史文件共 **2,080个 / 165,166,284字节（157.5MiB）**，包含主工作区、3份历史checkout及外部材料；不含共享`.git`、目录元数据、本轮新交付以及不可访问的F盘。主工作区711文件/56,849,649字节；三个历史worktree914文件/63,204,353字节；外部可读目录455文件/45,112,282字节。是有界范围总量，不是全机总量。

| 分类 | 文件数 | 逻辑字节 | 用途与限制 |
|---|---:|---:|---|
| KEEP | 455 | 71,778,514 | 有效代码/测试/合同、当前决策、聚宽最终知识、原始竞品图、未结数据资格与FX01B证据 |
| ARCHIVE | 382 | 5,893,593 | 已结束批次/旧提案/年度阅读过程/OD验收底稿；保留来源身份，退出日常入口 |
| DELETE_CANDIDATE | 959 | 67,287,613 | 3个无独有成果的历史checkout、44字节码、1个已证等价ZIP；均待下一轮Owner授权 |
| REVIEW | 284 | 20,206,564 | 269份阅读输入及15份暂停FX01证据；缺原件可用性或待Owner处置，不计入可回收量 |
| 合计 | 2,080 | 165,166,284 | 四类互斥、全集覆盖；CSV中每个文件仅归一类 |

文件数是目录项数量。通过Windows文件ID、链接计数核对，2,080个目录项对应2,080个独立文件ID，没有在本范围内重复计算硬链接；候选未发现范围外硬链接。用`GetFileInformationByHandleEx(FileStandardInfo)`查询候选的分配大小，结果 **68,974,056字节（65.8MiB）**，无查询错误。该数不包含目录/MFT开销或共享Git元数据；实际删除后的卷空闲变化仍受文件系统、运行时新增和存储层影响，不承诺严格相等。逻辑字节67,287,613作为跨环境可复核基准，分配字节68,974,056作为本机可回收估计。

`git count-objects -v`另外报告759个松散对象、`size=35470` KiB（约36,321,280字节）、pack=0；它不是上述工作区字节，也不是删除分支可立即回收的空间。**本方案Git对象回收计为0**，不运行gc。3个本地分支删除主要减少导航负担，GitHub远端引用不算本地容量收益。

F盘五个源库仅有2026-10-23记录：877文件/4,282,580,626字节（含聚宽597文件）。本轮提升权限只读确认仍无F盘，不能验证现存量；不把这个历史量加到当前总量，也不填成0文件。F盘所有权/迁移副本位置未知，状态REVIEW。外部未被既有索引列明的材料、更多旧会话/历史worktree和未登记clone属于范围外未知，不为凑总量扩大扫描。

## 文件集合保留决定

精确路径、修改时间、容量、文件ID、分类与组名见 [asset-files.csv](docs/asset-review-2026-10-24/asset-files.csv)；组级统计见 [retention-summary.json](docs/asset-review-2026-10-24/retention-summary.json)。下表路径均相对 `D:\Dev\Projects\mishi-radar`，除非写绝对路径。集合由CSV中`group`选取，不能把未列入的同名新文件自动纳入。

| 分类 / 集合 | 数量 / 字节 | 保留或清理依据、其他副本及最小条件 |
|---|---:|---|
| KEEP `active-code-contracts-decisions` | 75 / 1,011,137 | 有效源码、测试、最新Owner决定/合同/导航；main可达。旧设计中的撤回建议不覆盖最新决定 |
| KEEP `joinquant-final-knowledge` | 10 / 1,598,415 | 最终总结、594条索引、合并语义记录、源/覆盖/校验清单；均在main。保留机制与缺陷、canonical和编码映射；不再把原库数量当策略数量 |
| KEEP `dr01-current-*`（两批） | 127 / 8,557,045 | 原始响应与闭市码等反例仍支撑BLOCKED；后轮引用首轮。main内持久化，不能整组当缓存 |
| KEEP `dr02-dr06-consolidation-2026-10-19`、`dr04-m-decision-design` | 5 / 4,801,409 | 最新差距与待决M设计；main内持久化。供需文档快照不等于供应方实时资格 |
| KEEP `s08-fund-universe-investigation-2026-10-17` | 71 / 4,618,340 | 来源/分页/零/缺失/年度原文及旧本地输入哈希；main内持久化。既有VIPDOC调查输入位于供应项目，保留其索引，不跨项目清理或重测 |
| KEEP FX01A身份清单及合同样例 | 4 / 166,166 | 已接受合同与32暂停文件限制仍有效，main内持久化；不能用后补基线宣称实施前身份已证明 |
| KEEP `fx01b-current-evidence`、`fx01b-recovery-for-owner-review` | 47 / 14,123,683 | 当前27证据+20恢复文件均在main；恢复19份内容本轮全部匹配清单。支持未结束的Owner Review，不能当代码重复副本清理 |
| KEEP 竞品原图 | 68 / 34,022,804 | `C:\Users\Administrator\Documents\竞品分析\`内原图；GitHub只有索引/文字，未验证迁移盘第二副本。历史截图不可保证再次取得；保留来源时间与产品关联 |
| KEEP FX01B两轮外部独立证据 | 48 / 2,879,515 | 索引所列`wp-fx01b-independent-review/`36项、`wp-fx01b-reacceptance/`12项；首次失败与修复后证据身份不同，不互相当重复。尚无验证的仓库外第二副本 |
| ARCHIVE `joinquant-stage-records` | 23 / 589,427 | 年度/分段摘要、分段JSONL与progress；最终记录已整合，但过程身份可能不同，不判逐条等价删除。采用已有main/SSD备份可达的Git历史冷归档，最终10文件作日常入口 |
| ARCHIVE `superseded-product-proposals`、`historical-consumer-review` | 21 / 156,470 | CSV精确列出的7个旧提案和`outputs/v0.1-owner-review-2026-10-16/`14文件；由R3.2和新差距报告覆盖当前作用，仍有决策追溯价值。依托已有Git引用，不再复制一份归档目录 |
| ARCHIVE `competitor-3-source-batch` | 186 / 3,432,534 | 既有C盘竞品3`outputs/`批次；保留原位作冷资料，以R01进入，不重新采集。不声称已备份到GitHub或F盘，不从C盘释放量中计收益 |
| ARCHIVE OD整合/独立验收底稿 | 152 / 1,715,162 | 索引所列`final-integration-2026-10-23/`35项及`g01-g07-final-reacceptance/`117项；Owner PASS后日常只看Acceptance，但原外部证据与反例需可追溯。原位冷保留，不与worktree一并移除 |
| REVIEW `joinquant-reading-inputs` | 269 / 9,044,280 | 4个忽略目录：`reading-inputs/`228/7,775,331；`middle-reading-inputs/`16/284,997；`tail-reading-inputs/`12/712,029；`2026-tail-reading-inputs/`13/271,923。原始F盘目前不可访问，既有LF校验不等于今天仍可重建 |
| REVIEW `paused-fx01-evidence` | 15 / 11,162,284 | `outputs/wp-fx01-fixture-vertical-2026-10-23/`旧截图、脚本、演示状态。与FX01B部分内容可能重复，但32文件暂停身份限制及Owner收口尚未处理，不把“旧/暂停”直接变删除资格 |

ARCHIVE是退出日常工作入口的价值决定，不代表立刻删除工作副本。对Git内44项/745,897字节，下一轮若Owner确实希望精简默认checkout，可另批准窄范围导航/移除改动；历史原件仍由现有保留引用到达，不能由本轮授权推导可改main。对外部338项/5,147,696字节，优先利用原位存储及Owner已有SSD迁移备份；如需迁出C盘，先指定唯一归档根、按本CSV相对路径保留批次、导出局部哈希清单并校验后再单独申请释放旧副本。F盘未挂载时不新建假定可用的归档目标，不维护多份同样的日常镜像。

## 可申请一次性清理的精确集合

| 编号 / CSV组 | 精确目标 | 数量 / 逻辑字节 | 依据、恢复保障与执行条件 |
|---|---|---:|---|
| C01 `primary-python-bytecode` | 主工作区CSV列出的44个`.pyc`，位于源码/测试的`__pycache__` | 44 / 1,020,993 | 由Git内`.py`与Python生成；不含watchlist、页面响应、数据证据或`.codex`。执行前路径/类型/文件身份仍匹配；只移除清单文件，不递归删整个项目或任意缓存父目录 |
| C02 `competitor-4-duplicate-container` | `C:\Users\Administrator\Documents\竞品分析\竞品4量化交易选股系统源码58.65.zip` | 1 / 3,062,267 | 7/7非目录成员经解压到内存计算SHA，与保留的同目录7原图全部匹配；不是源码包，未执行内容。ZIP原始SHA与成员映射见[等价清单](docs/asset-review-2026-10-24/zip-equivalence.json)。保留原图与映射即可恢复内容；未来重打ZIP字节未必相同。执行前重验容器和保留图身份及引用，不移除7张图 |
| C03 `worktree-1` | `C:\Users\Administrator\.codex\worktrees\od1-od2-final-integration\mishi-radar` | 306 / 21,062,843 | 整合任务已PASS闭环；tracked/untracked干净、忽略0；tip全在main，外部验收证据不在此目录。仅下一轮明确授权后由Git/适用的应用worktree生命周期方式移除该登记checkout，保留其他`.codex`文件 |
| C04 `worktree-2` | `D:\Dev\Projects\.worktrees\mishi-od1-a` | 305 / 21,074,373 | A已正式接受并整合；289跟踪文件、16忽略字节码，无未提交成果，无独有提交。恢复用A精确SHA，不依赖现有checkout |
| C05 `worktree-3` | `D:\Dev\Projects\.worktrees\mishi-od2-b` | 303 / 21,067,137 | B已正式接受并整合；289跟踪文件、14忽略字节码，无未提交成果，无独有提交。恢复用B精确SHA |

机器清单为**集合边界**，不是可直接执行的脚本。本轮没有生成或运行删除脚本。3个checkout中的30份字节码已包含在C03–C05，不再加到C01；`.git`指针和共享管理元数据不计候选文件字节。没有因同一历史源被多个文档引用而重复计容量。

## 每个分支与worktree的判定

| 本地分支 | tip | 相对main独有提交 / 保留引用 | 判定 |
|---|---|---|---|
| `main` | `447c0e22edd414abe9ef1efcdfb6ad266c0bcb32` | 0；GitHub同SHA | KEEP_ACTIVE |
| `backup/ssd-migration-2026-10-23` | `34c8b4c7cf9236f316ebd661c175e12bdcbc26cb` | 1；同名GitHub引用已核对，本轮分支也以其为祖先 | KEEP_ARCHIVE；独有恢复说明及既有恢复链接有价值。只1个备份，无需归并或新增标签 |
| `codex/research-asset-review-2026-10-24` | 本交付提交，初始基线为`34c8b4c` | 新整理成果；推送后正常保留同名远端 | KEEP_ACTIVE，待Owner清理决策 |
| `codex/od1-od2-final-integration` | `b9a7fba6be9515fc3271eac7a7a97ab65f53e64d` | 0；main和SSD备份均可达全部历史 | DELETE_CANDIDATE，与C03结对；Acceptance/恢复文档引用此名，用本表tip及main恢复，不丢审查差异 |
| `feature/od1-strategy-core` | `a72c67901e1147f3e4c198207dea8dd56d59a542` | 0；main和SSD备份均可达全部历史 | DELETE_CANDIDATE，与C04结对；Owner已接受对应精确SHA |
| `feature/od2-cash-backtest` | `fc02eff5a68b0bc408bc3a60b5b4f0ad272c6758` | 0；main和SSD备份均可达全部历史 | DELETE_CANDIDATE，与C05结对；Owner已接受对应精确SHA |

GitHub本轮开始仅有main、SSD备份2个heads，均KEEP；没有远端历史分支删除候选。`origin/main`与`origin/backup/...`是对应远端的本地跟踪引用，不再当另外2条独立研究分支计数。本轮推送会新增整理分支，完成后为6个本地分支（KEEP3、候选3）、3个远端heads（全部KEEP）。无标签、stash为空，均不作清理。

4个登记worktree中，主工作区为KEEP_ACTIVE；3个历史worktree为DELETE_CANDIDATE。资格依据不仅是合并关系：三者状态干净、没有原始阅读副本/隐藏数据，只有A/B的30字节码；对应Owner Review已在OD Acceptance收口，未结FX01B证据在主工作区或单列外部路径；已有永久远端main保留全部提交。以`rev-list <tip> --not <main>`证明各为0，含原来修复/候选差异，见[Git清单](docs/asset-review-2026-10-24/git-inventory.json)。恢复记录按上述SHA重建分支和checkout即可，不需要原`.git`工作区指针。

限定的[进程检查](docs/asset-review-2026-10-24/process-check.json)未找到命令行引用项目/worktree的Python/Node进程。最近50个聊天的[相关快照](docs/asset-review-2026-10-24/task-snapshot.json)及既有整合闭环记录未显示三个旧checkout上的活跃任务；该清单不是全局所有历史聊天或所有外部依赖的证明。执行前须再次核实无活跃使用，不能仅凭文件旧、聊天idle或mtime认定废弃；Owner清理授权也不授权停止别人的任务。

## 下一轮顺序与恢复条件

1. **批准具体集合后，先执行C01–C02。** 重验44字节码身份与ZIP7成员等价；保留原图、JSON映射与清单。小收益约4.08MB逻辑数据，几乎不影响研究恢复。
2. **再执行C03–C05及对应3个本地分支。** 先查HEAD、tracked/untracked/ignored、任务/运行依赖和main远端可达性；保留本表和恢复说明。只移除精确登记checkout，再移除已解除checkout占用的候选分支；出现新成果则暂停该组，不强制或递归删除父目录。候选checkout逻辑回收63,204,353字节，是本项目主要收益。
3. **原库接回后再处理269阅读副本。** 以清单匹配594正文（历史仅约8MB），按记录编码和行区间示范重建一个多段chunk、一个带base64图的JQ0351/JQ0387及一个尾部抽取。明确LF文本哈希与原始字节哈希口径；规范化/脱敏转换无完整配方时，不能承诺精确重建，应保留不能证明等价的部分。原件+最终知识充分后，才将相应副本从REVIEW转为下一份精确候选，不默默纳入本轮959文件。
4. **FX01B Owner收口后再评估旧FX01证据15文件。** 先证明每项的历史身份和重要反例已被适当保留、恢复副本仍可靠；不把截图与复验的不同批次当字节等价，不改写FX01A具名限制。未满足前保持REVIEW。
5. **冷归档通过导航减负。** 保留本索引→最终结论→必要原件的路径；默认不再按年读progress或搜索三个旧checkout。Git内旧提案不移动、不合并main；外部单份证据原位冷留。若后续确需迁移外部证据，只验证该组目标后申请处置旧副本，不扫描整个Codex或全盘重复文件。

这些是清理执行前的恢复保障，不是新增产品研发Gate。D01的F盘限制不阻断C01–C05；未通过某组核实也不阻断无关集合。参考 [RESEARCH_DECISION_QUEUE](RESEARCH_DECISION_QUEUE.md) D01–D03。

## 验证、维护收益与剩余风险

本轮验证聚焦文档与清理资格：Git本地/远端SHA、3个tip可达性、4个工作区状态及忽略集合、2,080条互斥分类与容量对账、候选硬链接/分配大小、ZIP7成员等价、32暂停文件映射及19恢复副本身份、引用文档和关键外部结论可读。没有重新抓市场数据、运行投资策略或重跑已有产品功能测试。既有167/176/184测试结论均标明为历史证据。

本项目清理收益主要是减少 **914份重复checkout文件和3个无独有提交的分支入口**；加上缓存和重复ZIP共959文件，减少无效搜索与旧文档误读。日常阅读收敛为本索引、当前权威与聚宽最终10文件；382项冷资料不再冒充待办。仓库本身只有约56.8MB工作区文件，本轮不承诺GB级回收，不把离线F盘4.28GB资料当可释放空间。

剩余风险：F盘原件及迁移副本未验证；外部图/调查/独立证据多为仅验证一个存储位置；暂停FX01实施前身份不可证明；FX01B正式Owner Acceptance尚未发现；运行依赖检查是有限快照。上述风险分别保留REVIEW/KEEP或执行前核实条件，不把技术/来源资格不足判为投资机制或产品假设失败。

## 交付摘要

```text
PROJECT = mishi-radar
CURRENT_BASELINE = main 447c0e22edd414abe9ef1efcdfb6ad266c0bcb32; SSD backup 34c8b4c7cf9236f316ebd661c175e12bdcbc26cb
RESEARCH_TOPICS_INDEXED = 10
VALUABLE_UNINDEXED_FINDINGS = 6 groups reconnected to current decisions; no new experiment
OPEN_RESEARCH_DECISIONS = 8 consolidated decisions (including asset decisions)
KEEP_FILES_AND_SIZE = 455 / 71778514 bytes
ARCHIVE_FILES_AND_SIZE = 382 / 5893593 bytes
DELETE_CANDIDATE_FILES_AND_SIZE = 959 / 67287613 bytes
REVIEW_FILES_AND_SIZE = 284 / 20206564 bytes
LOCAL_RECLAIMABLE_BYTES = 68974056 estimated allocated bytes; 67287613 logical bytes; 0 executed
BRANCHES_KEEP = local 3; remote 3 after review push
BRANCHES_DELETE_CANDIDATE = local 3; remote 0
WORKTREES_DELETE_CANDIDATE = 3 of 4 registered
IRREPLACEABLE_DATA_RISKS = F drive unavailable; external original/evidence second copies unverified; paused pre-implementation identity unproven
CLEANUP_PLAN = ASSET_RETENTION_AND_CLEANUP_PLAN.md
RESEARCH_INDEX = RESEARCH_ASSET_INDEX.md
DECISION_QUEUE = RESEARCH_DECISION_QUEUE.md
CLEANUP_AUTHORIZED = NO
OWNER_REVIEW_READY = YES
```
