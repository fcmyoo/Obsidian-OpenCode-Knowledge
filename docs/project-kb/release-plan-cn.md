# Project KB Release Plan

日期：2026-06-24
依据：`docs/project-kb-cross-agent-prd-cn.md`、`docs/project-kb/release-readiness-review-cn.md`、`docs/project-kb/completion-audit.md`

## 1. 发布原则

本计划不替代 PRD。PRD 继续作为产品和架构方向，本文只定义“什么时候可以发布”和“发布前必须拿到什么证据”。

本计划当前的直接发布对象是 `Project KB` 子系统，不等于整个仓库对非技术用户承诺的“一键部署、开箱即用”产品发布。仓库整体发布必须额外通过本文第 6 节的 repo-wide gates。

Release target 必须显式二选一：

- `project-kb-preview`：只发布 Project KB 技术预览。允许 README 中的部分端到端用户承诺继续标注为未验证或不在本 release。
- `repo-wide-end-user-release`：发布整个 Obsidian + OpenCode 知识库产品。必须通过 clean install、用户旅程、公开承诺对齐和支持矩阵 gates。

发布判断分三层机器 gate：

- `engineering`：仓库内工程可交付。
- `environment`：当前宿主环境可运行。
- `pilot`：真实任务试点可验证。

三层可以独立检查，不能混成一个模糊的“完成”。例如：`engineering` 可以在 Obsidian CLI 未启用时通过；`environment` 必须有 Obsidian CLI 和 Local REST 的 live 证据；`pilot` 只评价 10 个真实任务和指标，不隐式代表环境已经可运行。

版本号按累计发布理解：

- `v0.1-preview` = `engineering` gate ready。
- `v0.2-beta` = `v0.1-preview` + `environment` gate ready。
- `v0.3-pilot` = `v0.2-beta` + `pilot` gate ready。
- `project-kb-full` gate = `engineering` + `environment` + `pilot` 全部 ready。

如果只运行某一个 gate，它只证明该 gate 本身，不证明更高版本已经完成。

`release check --level full` 当前表示 `project-kb-full`，不是仓库整体产品 fully publishable。

## 2. 版本范围

### v0.1-preview: engineering

范围：

- filesystem-backed Project KB core。
- `kb` CLI P0/P1 维护命令。
- stdio MCP Facade。
- repo-local Codex / Claude / OpenCode adapter entrypoints。
- OpenClaw / generic adapter guidance。
- safe writes、per-file locks、audit log、secret scan。
- BM25 bounded retrieval。
- release gate CLI/MCP surface。

必须证据：

- `python -m unittest tests.test_project_kb -v` 通过。
- `python scripts/kb.py --vault <vault> doctor --project <project>` 返回 `status: "ready"`。
- `python scripts/kb.py --vault <vault> release check --project <project> --level engineering` 返回 `status: "ready"`。
- 严格发版检查使用 `python scripts/kb.py --vault <vault> release check --project <project> --level engineering --commit <current-commit> --require-artifacts`，以同时卡住 stale notes 和发布工件缺失。
- MCP `tools/list` 不暴露 delete、overwrite、bulk rewrite 类工具。
- `docs/project-kb/completion-audit.md` 更新到当前证据。

不要求：

- Obsidian CLI 已启用。
- Local REST API 可访问。
- Claude Code / OpenClaw live 接通。
- 10 个真实任务 pilot 完成。

### v0.2-beta: environment

范围：

- v0.1 全部内容。
- Obsidian CLI 在当前机器上真实可用。
- Obsidian Local REST API endpoint 可访问。
- 至少一次通过 Obsidian transport 的 read/search/write smoke。

必须证据：

- `D:\soft\Obsidian\Obsidian.com --help` 或 PATH 中 `obsidian --help` 不再返回 CLI disabled。
- 官方插件默认的 `https://127.0.0.1:27124/` 或配置的 `PROJECT_KB_OBSIDIAN_REST_URL` 可访问。loopback 自签名证书受支持，实际读写仍要求 API key。
- `python scripts/kb.py --vault <vault> release check --project <project> --level environment` 返回 `status: "ready"`。
- `python scripts/kb.py --vault <vault> release smoke --project <project> --level environment` 成功写入 `environment-smoke.json`。
- `environment-smoke.json` 证明 Obsidian CLI read、Obsidian CLI search、Local REST append、probe nonce 文件回读四步都通过。
- `transport detect` 的 `available.cli.state` 为 `ready`。
- `transport detect` 的 `available.mcp_obsidian.available` 为 `true`。

当前状态：

- 当前 Windows 机器上的 Obsidian CLI 已启用，CLI read/search 已通过。
- `tmp-live-vault` 已安装并启用官方 `obsidian-local-rest-api` 4.1.3，安全默认端点 `https://127.0.0.1:27124/` 已通过认证写入与文件回读。
- `release smoke --level environment` 和 `release check --level environment` 均为 ready，因此 v0.2-beta 已通过。

### v0.3-pilot: pilot

范围：

- v0.2 全部内容。
- 10 个真实项目任务试点完成。
- 每个任务记录检索、读取、写回、stale、误导和上下文注入指标。

必须证据：

- `python scripts/kb.py --vault <vault> metrics --project <project>` 显示 `tasks >= 10`。
- effective retrieval hit rate >= 60%。
- stale misguidance <= 1。
- average injected notes <= 5。
- write-back provenance/acceptance = 100% when writes exist。
- validation failures = 0。
- destructive write incidents = 0。
- `python scripts/kb.py --vault <vault> release check --project <project> --level pilot` 返回 `status: "ready"`。

注意：

- `pilot` gate 不等于 `environment` gate。pilot 证明产品效果；environment 证明当前 Obsidian 宿主可运行。
- `v0.3-pilot` 是累计版本，必须同时满足 `engineering`、`environment`、`pilot` 三层。
- 单独的 `release check --level pilot` 只用于复算试点指标，不代表环境 gate 已通过。

## 3. Release Gate 命令

工程门槛：

```powershell
python scripts/kb.py --vault <vault> release check --project <project> --level engineering
```

严格工程发版门槛：

```powershell
python scripts/kb.py --vault <vault> release check --project <project> --level engineering --commit <current-commit> --require-artifacts
```

环境门槛：

```powershell
python scripts/kb.py --vault <vault> release diagnose --project <project> --level environment
python scripts/kb.py --vault <vault> release smoke --project <project> --level environment
python scripts/kb.py --vault <vault> release check --project <project> --level environment
```

试点门槛：

```powershell
python scripts/kb.py --vault <vault> release check --project <project> --level pilot
```

Project KB 完整发布门槛：

```powershell
python scripts/kb.py --vault <vault> release check --project <project> --level full
```

累计发布报告：

```powershell
python scripts/kb.py --vault <vault> release report --project <project>
```

返回约定：

- `status: "ready"` 时退出码为 `0`。
- `status: "blocked"` 时退出码为非 `0`。
- MCP Facade 同步暴露只读工具 `kb.release_check`，用于 Codex、Claude、OpenClaw、OpenCode 共享同一套发布判断。
- `release smoke` 是显式写证据的 CLI 维护命令，不作为普通 MCP 工具暴露。
- `release diagnose` 是只读诊断命令，blocked 时仍返回退出码 `0`，用于输出 v0.2 修复步骤和可复制验证命令。
- `release report` 汇总 `engineering`、`environment`、`pilot`、`full` 和 `repo-wide`，输出 `highest_ready_version`、`project_kb_status`、`blocked_gates`、`blockers`、`next_actions` 和复验命令；repo-wide 证据缺失时，`next_actions` 会先列出 `public-claims-smoke`、`clean-install-smoke`、`user-journey-smoke`、`support-matrix-smoke` 四条具体 smoke 命令，再列最终 `release check --level repo-wide`；顶层 `status` 和退出码要求 `project-kb-full` 与 `repo-wide` 同时 ready。
- 在文档措辞中，`full` 必须写成 `project-kb-full` 或明确限定为 Project KB，避免误读为整个仓库对外可发布。

参数：

- `--commit <current-commit>`：要求 tracked notes 的 `verified_commit` 或 `last_verified_commit` 与当前 commit 匹配。未传时不执行 stale gate，适合日常 smoke。
- `--require-artifacts`：要求 repo-local `.project-kb/project.json`、repo-local host config drafts、vault-local `.vault-meta/host-configs/mcp-server.json` 存在且关键路径一致。

## 4. Pilot 记录格式

真实任务选样规则：

- 至少覆盖 3 类任务：架构/模块理解、代码实现或修复、验证/文档回写。
- 至少覆盖 2 个 agent 入口；如果 Claude Code 或 OpenClaw 尚未 live，必须在任务记录里标注为 `environment_blocked`，不能把 Codex-only 结果外推成跨 agent 结论。
- 每个任务都必须先记录检索输入，再记录实际读取 note 数量。
- 任务完成前不能写回成功日志；写回必须引用 commit、命令、文件、source path、URL 或 repo 中至少一个来源。
- 任何一次 Obsidian note 误导当前代码判断，都必须记录为 `stale_misguidance: true`，即使任务最终修正成功。

每个真实任务完成后写入一个事件：

```json
{
  "task_id": "task-001",
  "title": "Use KB on a real implementation task",
  "searches": 2,
  "notes_read": 3,
  "write_backs": 1,
  "stale_notes": 0,
  "effective_hit": true,
  "false_positive": false,
  "stale_misguidance": false,
  "injected_notes": 3,
  "context_tokens": 1200,
  "write_back_accepted": true,
  "destructive_write_incident": false,
  "lock_contention_count": 0,
  "validation_failures": 0
}
```

写入命令：

```powershell
python scripts/kb.py --vault <vault> pilot plan --project <project>
python scripts/kb.py --vault <vault> pilot record --project <project> --from-file pilot-event.json
```

`pilot plan` 会写入 `Projects/<Project>/.vault-meta/pilot/plan.json`，包含 10 条试点任务、覆盖类别、建议 host、事件文件路径和记录命令模板。它只证明试点计划已经冻结，不替代真实任务事件。

同时它会生成 `Projects/<Project>/.vault-meta/pilot/events/task-*.json` 空事件模板。每个真实任务完成后，先填写对应模板，再通过 `pilot record --from-file` 追加到 `events.jsonl`。

`pilot record` 会拒绝未冻结计划的 task 事件、未出现在 `plan.json` 中的 `task_id`、缺少模板必填字段的事件，以及负数或非整数的计数字段。这样 `pilot` gate 只能由真实、完整、可复算的试点事件推进，空模板或半截 JSON 不计入完成任务。

复算指标：

```powershell
python scripts/kb.py --vault <vault> pilot status --project <project>
python scripts/kb.py --vault <vault> metrics --project <project>
```

`pilot status` 只汇总计划与已记录事件的差距，不把空模板算作完成任务。

## 5. 当前阻塞项

- v0.3 blocked：10 个真实任务 pilot 未开始。
- project-kb-full blocked：pilot 中的 Claude Code、OpenCode、OpenClaw 真实任务尚未执行。
- project-kb-full blocked：Canvas/Base 已生成，但 live Obsidian 渲染未验证。

## 6. Repo-Wide End-User Release Gates

如果 release target 是 `repo-wide-end-user-release`，还必须通过以下 gates。它们不替代 `Project KB` 的三层机器 gate，而是覆盖 README 和部署文档面向非技术用户的公开承诺。

机器检查入口：

```powershell
python scripts/kb.py --vault <vault> release check --project <project> --level repo-wide
```

证据文件目录：

```text
Projects/<Project>/.vault-meta/release/repo-wide/
```

每个 gate 必须有一个 JSON 证据文件，并且顶层包含 `"passed": true`。缺失、JSON 无效或 `"passed": false` 都必须保持 repo-wide release blocked。

证据写入命令：

```powershell
python scripts/kb.py --vault <vault> release evidence record --project <project> --gate public_claims_gate --from-file public-claims.json
python scripts/kb.py --vault <vault> release evidence record --project <project> --gate clean_install_gate --from-file clean-install.json
python scripts/kb.py --vault <vault> release evidence record --project <project> --gate user_journey_gate --from-file user-journeys.json
python scripts/kb.py --vault <vault> release evidence record --project <project> --gate support_matrix_gate --from-file support-matrix.json
```

如果证据文件声明 `"passed": true`，必须至少包含一个可观察证据字段，例如 `commands`、`reviewed_files`、`journeys`、`matrix`、`notes`、`artifacts` 或 `screenshots`。

公开承诺的自动 smoke 命令：

```powershell
python scripts/kb.py --vault <vault> release evidence public-claims-smoke --project <project>
```

这个命令检查 `README.md`、`README.en.md`、CLI 文档和 release plan 是否明确声明当前 release status，把 `Project KB preview`、`project-kb-full` 和 `repo-wide` 终端用户发布区分开，并限制 Obsidian CLI、Local REST、真实宿主注册等未 live 证据能力。它只证明公开承诺已经按证据范围收窄，不能替代 live 用户旅程。

clean install 的安全 dry-run 命令：

```powershell
python scripts/kb.py --vault <vault> release evidence clean-install-smoke --project <project>
```

这个命令只复制 `vault-template` 到临时目录并验证模板关键文件，同时检查 README/GUIDE/deployment 文档里的公开 `cd` 安装路径确实存在，并确认根目录 `setup.sh` / `setup.ps1` 存在。它不安装 Node.js、OpenCode、OpenCLI，也不修改真实 Obsidian 配置。它能证明模板发布包结构和公开安装入口一致，不能替代完整真人/真实机器 clean install。

用户旅程模板 smoke 命令：

```powershell
python scripts/kb.py --vault <vault> release evidence user-journey-smoke --project <project>
```

这个命令检查 README 与 `vault-template/AGENTS.md`、`AI_CONFIG.md`、`wiki/使用指南.md` 是否覆盖 `ingest`、`query`、`lint`、`social ingest` 四条公开用户旅程，先确认模板本身已经带有 `raw/social`、`wiki/log.md` 等基础工件，再把 `vault-template` 复制到临时 vault 后创建最小 raw ingest、wiki output、social ingest 和 lint log 文件。它能证明模板规则、公开说明和基础文件流之间有可追踪定义，不能替代 live LLM、浏览器或 OpenCLI 抓取实操。

支持矩阵 smoke 命令：

```powershell
python scripts/kb.py --vault <vault> release evidence support-matrix-smoke --project <project>
```

这个命令检查 repo-local adapter、host config、transport 状态，以及 Markdown/Canvas/Base 结构化产物，然后记录 `support_matrix_gate`。它会把当前未 live 验证的 Obsidian CLI、Local REST、真实 host 注册和 Obsidian 渲染继续标为 `blocked` 或只在说明里限定为 repo-local 证据，不能替代真实宿主接入。

### Public Claims Gate

必须逐条核对 README、README.en、部署指南、CLI 文档和 adapter 文档中的用户可见承诺。

证据文件：

```text
Projects/<Project>/.vault-meta/release/repo-wide/public-claims.json
```

要求：

- 已 live 验证的能力才能写成“可用”。
- draft、模板、配置片段、环境依赖未满足的能力必须明确标注为 draft only、repo-local only、optional transport 或 not in this release。
- 如果 README 继续宣称“自动录入素材、智能查询、定期体检、社交媒体录入、一键部署”，这些流程必须进入 User Journey Gate。

### Clean Install Gate

必须在目标 OS 上按公开文档从零安装一次。

证据文件：

```text
Projects/<Project>/.vault-meta/release/repo-wide/clean-install.json
```

最低证据：

- 克隆仓库。
- 执行公开部署脚本。
- 创建或打开目标 Obsidian vault。
- 安装或验证必要插件。
- 跑通 `doctor`。
- 记录命令、退出码、关键输出和失败修复步骤。

### User Journey Gate

必须按非技术用户的语言跑通端到端流程：

证据文件：

```text
Projects/<Project>/.vault-meta/release/repo-wide/user-journeys.json
```

- `ingest`：把一段真实素材加入知识库。
- `query`：查询刚写入或已有知识。
- `lint`：体检 wiki 并得到可理解结果。
- `social ingest`：如果 README 继续保留社交媒体采集承诺，则必须至少跑通一个真实或可复现样例；否则把它标为 not in this release。

每个流程都必须记录：

- 输入。
- agent/host 入口。
- 实际读写的 note 路径。
- 是否使用 Obsidian CLI、Local REST 或 filesystem。
- 用户可见结果。
- 失败时的错误信息和修复动作。

### Support Matrix Gate

必须维护一张支持矩阵，并把每项标成 `live verified`、`repo-local verified`、`draft only`、`blocked` 或 `not in this release`。

证据文件：

```text
Projects/<Project>/.vault-meta/release/repo-wide/support-matrix.json
```

最低维度：

- Host：Codex、Claude Code、OpenClaw、OpenCode。
- OS：Windows、macOS。
- Transport：filesystem、Obsidian CLI、Obsidian Local REST。
- Obsidian surface：Markdown notes、Canvas、Base。

`draft only` 的 host config 不能在 README 中描述成已自动接入。

## 7. 不重写 PRD 的理由

当前 PRD 的架构方向仍然成立：

- Facade 优先，禁止暴露原始危险 Obsidian 写操作。
- CLI 负责维护，MCP 负责 agent 实时访问。
- filesystem fallback 是可靠默认路径。
- Obsidian CLI / Local REST 是 transport，不是 agent 直接依赖。
- pilot 指标是产品验证，而不是基础工程完成条件。

需要补的是发布计划和 release gate，不是推翻原 PRD。

## 8. 下一步开发顺序

1. 保持 `engineering` gate 绿：测试、doctor、safe surface、文档审计同步。
2. 补环境 live：启用 Obsidian CLI，在当前打开的 Obsidian vault 安装/启用 Local REST，跑 transport smoke。
3. 跑 10 个真实任务 pilot，并逐条记录事件。
4. 将 live evidence 写回 `docs/project-kb/completion-audit.md`。
5. 如果目标升级到 repo-wide end-user release，先跑 Public Claims、Clean Install、User Journey 和 Support Matrix gates，再调整 README 的公开承诺。
6. 如果 P0 检索质量不足，再考虑 rerank 或向量检索，不提前引入基础设施。
