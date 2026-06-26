# Project KB 发布就绪评审

日期：2026-06-24
范围：`docs/project-kb-cross-agent-prd-cn.md` 当前实现、`docs/project-kb/completion-audit.md` 当前证据、仓库内 CLI/MCP/transport 代码与测试

## 结论

现在的项目状态，已经不是“要不要重写一遍 PRD”。

更准确的判断是：

1. 当前 PRD 作为方向文档仍然成立，不需要推翻重写。
2. 但如果目标是“真正可发布的项目”，当前还缺一份明确面向发布的计划。
3. 这份新计划不应该替代 PRD，而应该补在 PRD 之后，承担以下职责：
   - 发布范围冻结
   - 证据门槛定义
   - 环境前置条件
   - live 验证步骤
   - 试点任务计划
   - 发布阻塞项和退出标准

一句话：不需要重做 PRD，但需要新增一份 release plan。

## 当前优势

- 仓库内实现已经形成系统：
  - Project KB core
  - `kb` CLI
  - `kb_mcp.py` facade
  - repo-local Codex / Claude / OpenCode adapters
  - BM25 retrieval
  - safe writes
  - host config drafts
  - views export
- transport 分层已经从“概念”推进到“执行层”：
  - `cli`
  - `mcp_obsidian`
  - `filesystem`
- 安全边界相对清楚：
  - destructive surface 默认拒绝
  - secret scan
  - per-file lock
  - audit log
- 自动化回归已经有较高密度，当前全量测试数 74，属于一个可继续收敛发布面的基础。

## 当前发布短板

这些问题不是“代码没写”，而是“还不足以声明发布就绪”。

### 1. Live 环境证据不足

当前仓库内大量能力已有代码和测试，但缺少真实环境成功证据：

- Obsidian CLI binary 存在，但仍是 `disabled`
- Obsidian Local REST 端口仍拒绝连接
- Claude Code live 接通未验证
- OpenClaw live 接通未验证
- Canvas/Base 在真实 Obsidian 中的渲染未验证

这意味着：当前更像“候选发布构建”，还不是“可正式发布版本”。

### 2. 发布范围还没冻结

目前实现已经进入 P1 一部分，但没有一个清晰的发布范围标签，例如：

- `v0.1`: filesystem + Codex CLI live + repo-local adapters + tests
- `v0.2`: 加入 Obsidian CLI live transport
- `v0.3`: 加入 Local REST live transport

如果没有这个范围冻结，项目会继续无限延展，难以宣布任何版本完成。

### 3. PRD 与 release gate 不是一回事

当前 PRD 同时承担了：

- 愿景
- 架构
- 里程碑
- 验收

但它没有把“发布前必须满足的最小证据”单独抽出来。结果就是：

- 代码不断前进
- 但何时能叫 ready 不够清晰

### 4. 10 个真实任务试点尚未开始

这不是边角项，而是发布质量的核心外部证据。没有它，以下条款都不能闭环：

- retrieval hit rate
- stale misguidance
- average injected notes
- write-back acceptance

### 5. 环境依赖没有被发布化

当前最强阻塞都集中在宿主环境：

- Obsidian CLI 开关
- Local REST plugin / endpoint
- host config registration

这些现在散落在 audit 和聊天里，应该被整理成显式的发布前置条件。

## 是否需要重新规划

需要重新规划，但不是重做原 PRD。

建议的做法是：

1. 保留当前 PRD，作为产品/架构文档。
2. 新增一份 release-oriented 计划文档。
3. 新计划只做一件事：把“现在距离可发布还差什么”钉死。

## 建议新增的计划

建议新建：

- `docs/project-kb/release-plan-cn.md`

建议结构：

## 1. Release 目标

例如：

- `v0.1-preview`
  - Codex CLI live
  - filesystem fully verified
  - CLI/MCP/tests ready
  - Obsidian CLI / Local REST optional but not required

- `v0.2-beta`
  - Obsidian CLI live enabled
  - CLI transport verified in real Obsidian

- `v0.3-pilot`
  - Local REST live
  - 10 real tasks pilot done

## 2. 发布前置条件

- Obsidian version
- CLI enabled
- Local REST plugin installed/configured
- target vault path chosen
- host config destination agreed

## 3. Release Gate

明确哪些是“没有就不能发”的：

- 全量回归通过
- destructive surface absent
- Codex live transport evidence
- docs/audit up to date

## 4. Environment Gate

单独列：

- Obsidian CLI enabled
- Local REST reachable
- optional app render proof

## 5. Pilot Plan

- task selection rules
- evidence recording format
- success/failure review

## 6. Exit Criteria

把“什么时候可以说这个版本完成”写成 checklist。

## 建议的发布分层

这是我建议你采用的版本观，而不是继续追求“一次性全完成”。

### 发布层 1：工程可交付

定义：

- 仓库内实现完整
- 测试充分
- 文档一致
- live 外部依赖可以暂时缺失

当前项目已经非常接近这个层级。

### 发布层 2：环境可运行

定义：

- 宿主环境功能已启用
- Obsidian CLI / Local REST 可真实调用
- 至少 1-2 条 live 路径跑通

当前项目还没到。

### 发布层 3：产品可验证

定义：

- 10 个真实任务试点
- 指标回收
- 误导/stale 风险有真实数据

当前项目明显还没到。

## 我对“要不要重做计划”的结论

结论很直接：

- 不需要推翻当前 PRD
- 需要新增一份 release plan
- 需要把当前目标拆成“工程完成 / 环境完成 / 试点完成”三层

## 下一步建议

按优先级排序：

1. 新建 `docs/project-kb/release-plan-cn.md`
2. 定义一个你愿意接受的首发版本范围
3. 把当前 audit 中的 live blockers 迁移到 release plan 的 environment gate
4. 把 10-task pilot 设计成独立阶段，不混在当前工程收口里

## 最后的判断

如果你现在问：

“这个项目要不要重新做 plan 设计？”

我的答案是：

- 要，但不是从零重做
- 是从“产品 PRD”补一层“发布计划”
- 这是当前最正确的下一步
