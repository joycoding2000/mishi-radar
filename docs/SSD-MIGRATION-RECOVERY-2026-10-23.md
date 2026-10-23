# 系统盘更换恢复说明（2026-10-23）

盘点时间：2026-10-23（Asia/Shanghai）。本文件记录迁移前的 Git、Owner 状态和本机数据依赖；它不改变既有验收或授权。

## 项目状态

### 已核实事实

- 项目：`mishi-radar`；GitHub：`git@github.com:joycoding2000/mishi-radar.git`。
- `main` 与 `origin/main` 均为 `447c0e22edd414abe9ef1efcdfb6ad266c0bcb32`。本次盘点开始时，独立查询 GitHub 远端 heads 仅返回 `main`，SHA 与本地一致。
- 盘点前主工作区及其余三个登记 worktree 均无 tracked 修改、无 untracked 文件；stash 为空。D 盘工作区仅有可重建的 Python `__pycache__` 被忽略文件。
- 四个 worktree 共用主仓库 `D:\Dev\Projects\mishi-radar\.git`：

| 工作区 | 分支 | HEAD |
|---|---|---|
| `D:\Dev\Projects\mishi-radar` | `main` | `447c0e22edd414abe9ef1efcdfb6ad266c0bcb32` |
| `C:\Users\Administrator\.codex\worktrees\od1-od2-final-integration\mishi-radar` | `codex/od1-od2-final-integration` | `b9a7fba6be9515fc3271eac7a7a97ab65f53e64d` |
| `D:\Dev\Projects\.worktrees\mishi-od1-a` | `feature/od1-strategy-core` | `a72c67901e1147f3e4c198207dea8dd56d59a542` |
| `D:\Dev\Projects\.worktrees\mishi-od2-b` | `feature/od2-cash-backtest` | `fc02eff5a68b0bc408bc3a60b5b4f0ad272c6758` |

- 三个非 `main` 分支的 tip 都已包含在 GitHub `main` 历史内（各分支相对 `origin/main` 的独有提交数为 0）；远端没有为这些名称单独保留分支引用。恢复需要时可按上表 SHA 重建分支。
- 本恢复文档单独保存在 `backup/ssd-migration-2026-10-23`；该备份分支不推进 `main`。其当前 SHA 以 GitHub 该分支 ref 为准。
- 最新提交依次包括 DR03 时间语义文档、WP-FX01B 固定 Fixture Web 切片、WP-FX01A 结果合同和 OD-1/OD-2 整合记录。迁移盘点没有运行测试。

### 已批准决定与验收状态（按现有记录）

- OD-1、OD-2：Owner Acceptance 均为 `PASS`；整合记录称既有整合验证通过（167 次执行、165 个不同测试 ID、零失败），`NEXT_PHASE_AUTHORIZED=NO`。依据：`docs/OD1_OD2_OWNER_ACCEPTANCE_2026-10-23.md`。这些是既有记录，本次迁移盘点没有重跑测试。
- WP-FX01A：`PASS_WITH_LIMITATION`；固定合同 8 个交付文件，既有独立测试 176 项通过。32 个暂停文件缺少可证明实施前身份的基线；现有 SHA256 清单只从生成时起提供追溯，不授权恢复或继续这些文件。依据：`docs/WP_FX01A_OWNER_ACCEPTANCE_2026-10-23.md`。
- 事实：WP-FX01B 合成 Fixture Web 演示代码及相关浏览器证据已在 `main`。它只使用固定合成输入，不接真实行情、不通过数据 Gate，也不代表发布批准。仓库内未找到独立的 WP-FX01B Owner Acceptance 记录；不得从代码提交推断已验收。
- 当前权威状态见 `docs/CURRENT_STATE.md`：`FULL_DESIGN_NOT_FROZEN`；OD-3 为 `PRINCIPLES_ACCEPTED / NUMERIC_TERMS_UNKNOWN`；DR01-CURRENT 仍 `BLOCKED`（深市 2026-10-16 完整、可追溯停复牌状态仍缺）；DR02/03/DR04-M/05/06 尚未通过完整数据资格。DR04-P 的接受不扩展为 M、PIT 或 S08 PASS。

### 尚未完成 / 待 Owner 决定

- 真实数据资格及上述 DR 缺口、OD-3 运行和权益数值仍未解决；买家付费意愿也没有本项目真实付款验证。
- 是否接受 WP-FX01B：本仓库没有独立 Owner Acceptance 记录。
- 是否授权下一阶段：现有记录明确为 `NO`。迁移恢复本身不构成新开发、实验、数据供给或研究授权。

## 本机资产与恢复依赖

GitHub 保存已跟踪源码、文档、研究结论和 `outputs/` 中已提交的证据。以下内容不在 GitHub；路径大小为本次只读盘点值。

| 路径 | 文件数 / 字节 | 位置与恢复依赖 |
|---|---:|---|
| `D:\Dev\Projects\mishi-radar\docs\joinquant-full-review\reading-inputs\` | 228 / 7,775,331 | `.gitignore` 排除的阅读切块；依赖 F 盘聚宽源库，精确副本不在 GitHub。建议迁移前另备份此目录。 |
| `D:\Dev\Projects\mishi-radar\docs\joinquant-full-review\middle-reading-inputs\` | 16 / 284,997 | 同上；另有图像与逐文件抽取文本。 |
| `D:\Dev\Projects\mishi-radar\docs\joinquant-full-review\tail-reading-inputs\` | 12 / 712,029 | 同上；包含尾部阅读副本及图像。 |
| `D:\Dev\Projects\mishi-radar\docs\joinquant-full-review\2026-tail-reading-inputs\` | 13 / 271,923 | 同上；包含末段阅读副本。 |
| `C:\Users\Administrator\Documents\竞品分析\` | 69 / 37,085,071 | C 盘竞品截图；`docs/research/competitor-scope-2026-10-15.json` 与相关研究文档引用。原记录写 68 张图片，本次枚举到 69 个文件；未分类额外文件。**需单独备份到 F 盘**，GitHub 只有索引和文字分析。 |
| `C:\Users\Administrator\Documents\Codex\2026-10-13\3-a-http-124-221-98\outputs\` | 186 / 3,432,534 | C 盘竞品 3 原始调查报告、逐步记录和原始页面材料；仓库文档将其作为来源链接。**需单独备份到 F 盘**，GitHub 未包含该目录。 |

项目记录的五个原始研究库本次在 F 盘均可枚举；它们已位于外置盘 `F:\BaiduNetdiskDownload\`，如果 F 盘保留则不需再次复制：

| 路径 | 文件数 / 字节 |
|---|---:|
| `F:\BaiduNetdiskDownload\量化交易入门\` | 176 / 287,228,171 |
| `F:\BaiduNetdiskDownload\2020-2026聚宽600条源码\` | 597 / 8,406,253 |
| `F:\BaiduNetdiskDownload\Qmt策略\` | 50 / 335,971 |
| `F:\BaiduNetdiskDownload\聚宽中转 qmt 自动交易\` | 16 / 394,245,014 |
| `F:\BaiduNetdiskDownload\量化交易课程类\` | 38 / 3,592,365,217 |

Owner 计划整体备份的 `C:\Users\Administrator\.codex\` 覆盖其中的 Codex 会话数据、`worktrees\od1-od2-final-integration\mishi-radar` 文件和既有 `visualizations` 验收/研究证据。此 worktree 并非独立仓库：若沿用它，主仓库 `.git` 元数据也必须保留；若新克隆主仓库，应从上表 SHA 重建 worktree，不要把复制的 worktree 目录当作独立 clone。两个 `D:\Dev\Projects\.worktrees\` 工作区无独有未提交成果，且其提交已在 GitHub `main` 中。

环境不是 GitHub 资产：仓库依赖见 `requirements.txt`（FastAPI、Uvicorn、Jinja2、python-multipart 固定版本）；浏览器证据环境另见 `requirements-dev.txt` 和 README。现有验收证据引用本机 Python 3.14 路径；新系统需安装兼容 Python 并重新安装依赖。被忽略的 `__pycache__` 可重建。不要把任何本机运行环境路径当作研究结果备份。

## 新系统最小恢复步骤

1. 更换系统盘前，把上表两个 C 盘目录和四个 D 盘忽略阅读副本另存到 F 盘；核实 Owner 计划备份的整个 `.codex` 已完成并可读取。
2. 若 `D:\Dev\Projects\mishi-radar` 及其 `.git` 仍完整，直接打开现有项目。否则从 `git@github.com:joycoding2000/mishi-radar.git` 克隆到一个空目录，确认 `main` 为 `447c0e22edd414abe9ef1efcdfb6ad266c0bcb32`；单独获取 `backup/ssd-migration-2026-10-23` 读取本恢复文档，不合并到 `main`。
3. 按需从表中恢复本地资料；原始 F 盘库已在位时，阅读切块可从源库重新生成。若需恢复旧 worktree 分支，在新 clone 中按本文件的分支名和 SHA 建立本地分支；worktree 仍须由同一个主仓库 `.git` 管理。
4. 安装项目 `requirements.txt` 中的依赖。需要启动合成演示时按 README 操作；该演示不是数据资格或发布验收。
5. 重新开始工作前阅读 `README.md`、`docs/CURRENT_STATE.md`、本文件，以及相关 Owner Acceptance / DR 报告；由 Owner 明确指定下一项任务。当前没有下一阶段授权。

## 建议接续

迁移后先核对上述本地资产副本和 `main` SHA；然后由 Owner 选择是否补做 WP-FX01B 验收记录或处理既有数据资格缺口。没有新的 Owner 指令前，不自动启动新开发、实验、数据供给或研究阶段。
