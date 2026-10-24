# 2026-10-24 有界资产审查证据

入口为仓库根目录的`RESEARCH_ASSET_INDEX.md`、`RESEARCH_DECISION_QUEUE.md`、`ASSET_RETENTION_AND_CLEANUP_PLAN.md`。

- `asset-files.csv`：本轮新增文件以外的2,080个历史文件，UTF-8；每行scope/root/path/字节/时间/文件ID/链接数/分类/组。只枚举既有索引及Git登记路径，不是全机清单。
- `collection-summary.json`：初次盘点的计数与旧F路径不可访问快照；同日盘符更正及当前原库资格见`e-drive-source-check.json`，不重写历史枚举结果。
- `git-inventory.json`：盘点时Git/worktree状态、refs可达性、基线树、备份差异及stash/对象计量。主工作区出现的untracked仅为本轮证据文件，开工前为空；历史worktree均干净。
- `remote-baseline.json`：推送前独立远端heads查询。
- `retention-summary.json`：互斥分类、组级计数及Windows分配空间估计；不含共享Git或F盘历史量。
- `zip-equivalence.json`：唯一重复容器的7成员→保留原图映射及哈希。
- `joinquant-source-check.json`：初次按F路径核实的历史快照；后续Owner确认盘符改为E:，其旧路径限制已由新记录解除。
- `e-drive-source-check.json`：只核实受盘符变更影响的五个库根、聚宽594正文哈希及代表性重建；不重复全面审计。
- `reading-derivative-closeout.json`：269份阅读派生副本的逐项删除记录及恢复性批量核验。
- `cleanup-closeout.json`：C01–C05、异盘原件备份、最终排除项及总回收量。
- `fx01-identity-check.json`：32暂停文件的当前映射与19恢复副本校验，不能证明更早实施前身份。
- `process-check.json`、`task-snapshot.json`：执行前的有限运行/近期聊天快照；最终C01–C05逐项状态复核与当前线程检查见`cleanup-closeout.json`。
- `cleanup-targets.json`：从分类导出的精确集合边界与分支/worktree资格，不可直接作为删除脚本。
- `verification.json`、`sha256-manifest.json`：本轮交付核验及清单身份（manifest不包含自身）。本证据目录用局部`.gitattributes`保留原始字节；仓库根三份Markdown按UTF-8/LF规范化文本计算，方法在每项`method`字段明确记录，避免Windows换行变化造成误报。

`collect_inventory.py`只读源资产并在本证据目录写清单，`qualify_assets.py`从本次清单生成分类、做ZIP等价及Windows分配计量。采集与分类顺序执行；本轮快照不可因以后复跑而覆盖后再冒称原始审查时点。脚本需要可运行Python和Git；非Windows环境不运行Windows容量资格部分。未建立venv或安装依赖，未生成删除程序。

本次仅在C盘本地保留聚宽原始材料的独立副本；未将原始正文、图片或第三方资料上传GitHub。E盘源库未修改，C03仅移除了已批准的历史worktree checkout；未删除Codex聊天或visualizations。
