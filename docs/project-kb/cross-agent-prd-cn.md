# Project Knowledge Vault 中文 PRD 与实施方案

状态：草案 v1  
日期：2026-06-23  
目标用户：Codex、Claude Code、OpenClaw、OpenCode 以及其他 agent CLI 用户  
主要存储：基于 Markdown / YAML / JSON 文件的 Obsidian vault

## 1. 执行摘要

本方案要建设一套跨 agent 的项目知识层，让多个编码 agent 共享同一个持久、可人工编辑、可审计的项目知识库。

系统以 Obsidian 作为知识 vault，以 Project KB MCP Facade 作为面向 agent 的安全 API，以 Project KB CLI 作为初始化、校验、索引和维护工具，并为 Codex、Claude Code、OpenClaw、OpenCode 以及其他 agent CLI 提供薄适配层。

这个系统不是为了替代 Codex memory、Claude memory 或 OpenClaw memory。它的目标是建立一个项目级知识底座，用开放格式记录架构决策、模块说明、长期任务上下文、已知坑点、任务日志和经过验证的事实，保证人和 agent 都能直接检查和维护。

最重要的设计决策是：

```text
不要把原始 Obsidian 写入/删除工具直接暴露给 agent。
必须通过安全的 MCP Facade 暴露项目级操作。
```

## 2. 开源项目调研结论

本 PRD 结合了四个开源仓库及其当前公开设计模式。

| 仓库 | 定位 | 应该采纳 | 应该避免 |
|---|---|---|---|
| `obsidianmd/obsidian-releases` | Obsidian 官方 release、社区插件、主题目录元数据仓库，不是 Obsidian 源码。 | 把 Obsidian 视为可扩展应用，尊重插件生态、release 元数据、兼容性元数据和治理字段。 | 不依赖修改 Obsidian 核心。 |
| `kepano/obsidian-skills` | 面向 agent 的 Obsidian Markdown、Bases、Canvas、CLI、网页清理技能包。 | 直接作为 Obsidian 语法和 CLI 基础能力层。 | 不要从零重写 Obsidian Markdown/Bases/Canvas 规则。 |
| `AgriciDaniel/claude-obsidian` | 面向 Claude/agent 的知识工作流包和预配置 Obsidian vault。 | 借鉴 `hot.md`、`index.md`、`log.md`、`.raw`、ingest/query/lint/save workflow、transport fallback、检索和多 writer 安全思路。 | 不把 Claude 专属 plugin hooks/slash commands 当成核心系统契约。 |
| `MarkusPfundstein/mcp-obsidian` | 通过 Obsidian Local REST API 访问 vault 的 MCP server。 | 作为底层 Obsidian I/O 实现或参考。 | 不直接向 agent 暴露原始 `put_content` 或 `delete_file` 工具。 |

关键来源：

- https://github.com/obsidianmd/obsidian-releases
- https://github.com/kepano/obsidian-skills
- https://github.com/AgriciDaniel/claude-obsidian
- https://github.com/MarkusPfundstein/mcp-obsidian
- https://github.com/coddingtonbear/obsidian-local-rest-api

## 3. 问题陈述

当前 agent 工作流的记忆和项目知识是碎片化的：

- Codex、Claude Code、OpenClaw、OpenCode 等工具各自拥有不同的 memory、skill、hook、MCP 机制。
- 项目知识散落在聊天历史、agent memory、README、issue 线程、本地笔记和临时任务日志里。
- 开源项目二次开发通常需要稳定记住架构决策、模块边界、坑点、失败方案和验证命令。
- agent 自带 memory 有价值，但不适合作为项目事实源，因为它通常不透明、宿主绑定、难审查、容易漂移。
- Obsidian 可人工编辑、可链接，但裸 vault 访问权限过大、粒度过低，不适合直接交给 agent 自动操作。

系统需要让项目知识具备以下特性：

- 持久
- 可检查
- 可版本化
- 可人工编辑
- 可被 agent 读取
- 可安全更新
- 可跨 agent runtime 复用

## 4. 目标

### 4.1 产品目标

1. 建立一个可被 Codex、Claude Code、OpenClaw、OpenCode 和通用 agent CLI 共用的项目知识 vault。
2. 允许 agent 按需搜索、读取和引用项目笔记。
3. 允许 agent 安全追加任务日志，并在确认后创建架构决策记录。
4. 使用开放格式：Markdown、YAML frontmatter、JSON 元数据，以及可选 JSON Canvas/Base 文件。
5. 支持项目级知识对象：项目首页、模块、ADR、任务、日志、坑点、术语表、来源和热缓存。
6. 明确区分当前代码事实和项目知识。
7. 提供 CLI 校验，防止 vault 静默腐化。
8. 先交付可测试 MVP，再考虑复杂向量检索或自动重组 vault。

### 4.2 工程目标

1. 使用 MCP 作为 agent 实时访问接口。
2. 使用 CLI 进行初始化、校验、索引、transport 检测和批处理维护。
3. 使用 Facade 层，避免向 agent 暴露低层 Obsidian 危险操作。
4. 实现保守写权限。
5. 在开启多 agent 写入前实现按文件写锁。
6. 保持 adapter 薄而明确，核心协议与宿主无关。

## 5. 非目标

MVP 不做以下事项：

- 替代 Codex memory、Claude memory 或 OpenClaw memory。
- 做成通用个人知识管理产品。
- 自动重组整个 Obsidian vault。
- 删除、重命名或批量移动笔记。
- 向 agent 暴露原始 Obsidian 删除/覆盖工具。
- 强依赖向量数据库基础设施。
- 依赖 Claude-only slash commands 或 hooks。
- 依赖修改 Obsidian 核心源码。
- 在未验证时把 Obsidian 笔记视为当前代码事实。

## 6. 用户与用例

### 6.1 主要用户

- 正在做开源项目二次开发的开发者。
- 在 Codex、Claude Code、OpenClaw、OpenCode 或其他 CLI agent 间切换的 agent 操作者。
- 希望项目决策和任务历史脱离聊天记录、可被长期检查的维护者。

### 6.2 核心用例

1. 为本地仓库创建项目知识空间。
2. 要求 agent 分析架构，并自动检索相关项目笔记。
3. 要求 agent 延续长期重构任务，并复用历史决策和坑点。
4. 在实现和验证后记录任务结果。
5. 基于已确认的架构决策创建 ADR。
6. 检查笔记相对当前 repo commit 是否过期。
7. Codex 和 Claude Code 使用同一个知识库，不再手动复制 memory。
8. OpenClaw 托管的会话通过同一个 MCP server 访问知识库。

## 7. 设计原则

1. 开放文件优先于不透明 memory。  
   Markdown/YAML/JSON 是主要持久格式。

2. 项目真相分层。  
   代码、测试和构建输出是当前实现真相；Obsidian 记录意图、决策、解释和历史。

3. MCP 负责交互，CLI 负责维护。  
   agent 用 MCP 搜索、读取、追加；人和自动化用 CLI 初始化、校验、索引和迁移。

4. Skill 描述 workflow，不承载大块知识正文。  
   Skill 负责说明何时、如何查询 KB，不应该塞入大量项目知识。

5. Adapter 保持薄。  
   Codex、Claude Code、OpenClaw、OpenCode 只做最小 glue，核心知识协议应独立于宿主。

6. 写入保守。  
   从只读开始，再到 append-only，再到有限结构化更新。

7. 所有持久事实都要有来源。  
   笔记应引用 source path、命令、commit、URL 或来源笔记。

8. 检索必须有边界。  
   agent 应读取少量相关笔记，而不是把整个 vault 注入上下文。

## 8. 系统架构

```text
                +---------------------------+
                |       Obsidian Vault       |
                | Markdown / YAML / JSON     |
                +-------------+-------------+
                              |
                              v
                +---------------------------+
                |   Project KB Core Layer    |
                | schema / lock / validate   |
                +------+----------+---------+
                       |          |
                       v          v
          +----------------+   +----------------+
          | Project KB CLI |   | Project KB MCP |
          | setup/validate |   | safe Facade    |
          +-------+--------+   +-------+--------+
                  |                    |
                  |                    v
                  |       +--------------------------+
                  |       | Low-level Transports      |
                  |       | Obsidian CLI              |
                  |       | mcp-obsidian              |
                  |       | filesystem fallback       |
                  |       +------------+-------------+
                  |                    |
                  v                    v
        +----------------+   +-----------------------------+
        | Human/CI usage |   | Agent Runtime Adapters       |
        | terminal jobs  |   | Codex / Claude / OpenClaw    |
        +----------------+   | OpenCode / generic CLI       |
                             +-----------------------------+
```

## 9. 仓库与 Vault 布局

推荐 vault 布局：

```text
Vault/
  Projects/
    <ProjectName>/
      _index.md
      hot.md
      context.md
      architecture.md
      glossary.md
      pitfalls.md
      decisions/
        ADR-0001-example.md
      modules/
        module-a.md
      tasks/
        2026-06-23-example-task.md
      logs/
        2026-06.md
      sources/
        _index.md
      .manifest.json
      .vault-meta/
        transport.json
        locks/
        bm25/
        chunks/
```

可选 repo 集成布局：

```text
<repo>/
  AGENTS.md
  CLAUDE.md
  .project-kb/
    project.json
    adapters/
      codex/
      claude/
      openclaw/
```

vault 是知识源。repo 只保存 adapter 提示和长期 agent 指令。

## 10. 知识对象模型

### 10.1 项目首页

文件：

```text
Projects/<ProjectName>/_index.md
```

Frontmatter：

```yaml
---
type: project
project: WeFlow
repo: H:/code/github/WeFlow
status: active
agent_scope:
  - codex
  - claude
  - openclaw
source_of_truth: repo
last_verified_commit:
last_verified_at:
transport: auto
tags:
  - project
  - weflow
---
```

必需章节：

```md
# WeFlow

## Purpose

## Current State

## Important Modules

## Active Decisions

## Known Pitfalls

## Verification Commands

## Links
```

### 10.2 热缓存

文件：

```text
Projects/<ProjectName>/hot.md
```

用途：

- 最近任务上下文
- 最近已知 branch/worktree 状态
- 当前焦点
- 未解决决策
- 最近命令与结果

规则：

- 保持简洁。
- 控制在 1-2 屏文本以内。
- 只在完成验证工作或明确生成会话摘要后更新。
- 不存储密钥。

### 10.3 ADR

文件：

```text
Projects/<ProjectName>/decisions/ADR-0001-title.md
```

Frontmatter：

```yaml
---
type: decision
project: WeFlow
status: proposed
date: 2026-06-23
source_paths:
  - src/example.ts
verified_commit:
confidence: medium
tags:
  - adr
  - architecture
---
```

模板：

```md
# ADR-0001: Title

## Context

## Decision

## Consequences

## Alternatives Considered

## Verification
```

### 10.4 任务日志

文件：

```text
Projects/<ProjectName>/logs/YYYY-MM.md
```

追加条目：

```md
## 2026-06-23: Short Task Title

- Status:
- Repo:
- Branch:
- Commit:
- Files:
- Commands:
- Result:
- Follow-ups:
```

### 10.5 模块笔记

文件：

```text
Projects/<ProjectName>/modules/<module>.md
```

Frontmatter：

```yaml
---
type: module
project: WeFlow
module: PairPilot
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
```

必需章节：

```md
# Module Name

## Responsibility

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
```

## 11. MCP Facade 合同

Project KB MCP Facade 暴露项目级工具。它内部可以使用 Obsidian CLI、`mcp-obsidian`、Local REST API 或 filesystem 操作。

### 11.1 P0 工具

#### `kb.project_find`

用途：根据 repo 路径或项目名解析项目知识根目录。

输入：

```json
{
  "repo_path": "H:/code/github/WeFlow",
  "project": "WeFlow"
}
```

输出：

```json
{
  "project": "WeFlow",
  "path": "Projects/WeFlow/_index.md",
  "status": "active",
  "repo": "H:/code/github/WeFlow",
  "hot": "Projects/WeFlow/hot.md"
}
```

#### `kb.search`

用途：以有边界的方式搜索项目知识。

输入：

```json
{
  "project": "WeFlow",
  "query": "PairPilot diagnostics architecture",
  "limit": 5,
  "filters": {
    "types": ["decision", "module", "pitfall"]
  }
}
```

输出：

```json
{
  "results": [
    {
      "path": "Projects/WeFlow/modules/pairpilot.md",
      "title": "PairPilot",
      "type": "module",
      "score": 0.87,
      "snippet": "..."
    }
  ]
}
```

#### `kb.read`

用途：读取笔记或笔记章节。

输入：

```json
{
  "path": "Projects/WeFlow/modules/pairpilot.md",
  "section": "Known Pitfalls"
}
```

输出：

```json
{
  "path": "Projects/WeFlow/modules/pairpilot.md",
  "content": "...",
  "frontmatter": {}
}
```

#### `kb.append_log`

用途：追加已验证任务日志。

输入：

```json
{
  "project": "WeFlow",
  "title": "Fix diagnostics panel filtering",
  "summary": "Implemented ...",
  "files": ["src/a.ts"],
  "commands": ["npm run typecheck"],
  "result": "passed",
  "commit": "abc123"
}
```

输出：

```json
{
  "path": "Projects/WeFlow/logs/2026-06.md",
  "appended": true
}
```

#### `kb.check_staleness`

用途：查找缺少验证信息或验证信息过期的笔记。

输入：

```json
{
  "project": "WeFlow",
  "current_commit": "abc123"
}
```

输出：

```json
{
  "stale": [
    {
      "path": "Projects/WeFlow/modules/pairpilot.md",
      "reason": "verified_commit missing"
    }
  ]
}
```

### 11.2 P1 工具

#### `kb.project_create`

根据模板创建项目目录。

#### `kb.create_decision`

创建 ADR。

#### `kb.update_project_status`

更新项目 `status` 字段。

#### `kb.update_frontmatter_field`

校验后更新一个允许的 frontmatter 字段。

### 11.3 默认拒绝的操作

Facade 不应把以下能力作为普通 agent 工具暴露：

```text
delete_file
put_content / overwrite full note
bulk_move
bulk_rename
bulk_rewrite
vault-wide format
```

如果确实需要，必须要求明确人工批准和 dry-run diff。

## 12. CLI 合同

本 PRD 中 CLI 名称暂定为 `kb`。

### 12.1 P0 命令

```bash
kb init-project --name WeFlow --repo H:/code/github/WeFlow
kb validate --project WeFlow
kb status --project WeFlow
kb transport detect --project WeFlow
kb search --project WeFlow --query "diagnostics"
kb read --path "Projects/WeFlow/_index.md"
kb append-log --project WeFlow --from-file summary.md
```

### 12.2 P1 命令

```bash
kb index --project WeFlow
kb retrieve --project WeFlow --query "PairPilot architecture"
kb stale --project WeFlow --commit HEAD
kb lock list --project WeFlow
kb export-adapter --agent codex --project WeFlow
kb export-adapter --agent claude --project WeFlow
kb export-adapter --agent openclaw --project WeFlow
```

### 12.3 校验规则

`kb validate` 必须检查：

- 必需 frontmatter 字段
- 合法 `type`
- 合法 `status`
- 本地 repo 路径存在
- 本地 source path 存在
- 内部 wikilink 可解析
- 日志文件日期格式正确
- 无明显密钥
- 无高风险生成噪音
- schema version 被支持

## 13. Transport 策略

Transport 选择顺序：

```text
1. Obsidian CLI
2. Project KB MCP Facade
3. mcp-obsidian through Local REST API
4. filesystem fallback
```

agent 面向的稳定合同始终是 Project KB MCP Facade。Transport 是内部实现细节。

Transport 元数据：

```json
{
  "preferred": "cli",
  "fallback_chain": ["cli", "mcp_obsidian", "filesystem"],
  "available": {
    "cli": true,
    "mcp_obsidian": true,
    "filesystem": true
  },
  "last_checked_at": "2026-06-23T00:00:00+08:00"
}
```

## 14. 检索策略

### 14.1 P0 检索

使用：

- frontmatter filters
- tag search
- filename/path search
- simple text search
- top 5 有界结果

默认流程：

```text
project_find -> read hot.md -> search -> read top notes -> answer with note paths
```

### 14.2 P1 检索

增加：

- BM25 index
- chunking
- contextual prefix
- 本地模型可用时 rerank

不要把向量基础设施作为 P0 依赖。

### 14.3 检索限制

agent 通常只应读取：

```text
hot.md + up to 5 search hits + source files required by the task
```

agent 不应读取：

```text
entire vault
all logs
all ADRs
all module notes
```

## 15. 写入安全与并发

所有写入必须经过 Facade 或 CLI。

写入流程：

```text
acquire lock
read current file
apply append/patch
validate target file
write audit entry
release lock
```

锁要求：

- per-file lock
- stale lock timeout
- lock list command
- safe release
- append 重试
- 多文件写入必须先有 transaction plan

审计条目：

```json
{
  "time": "2026-06-23T00:00:00+08:00",
  "actor": "codex",
  "operation": "append_log",
  "path": "Projects/WeFlow/logs/2026-06.md",
  "source": "mcp",
  "commit": "abc123"
}
```

## 16. Agent Adapter

### 16.1 Codex

文件：

```text
AGENTS.md
.codex/config.toml
~/.codex/skills/project-kb/SKILL.md or repo-local skill
```

`AGENTS.md` 片段：

```md
## Project Knowledge

- For architecture, historical decisions, module boundaries, long-running tasks, and known pitfalls, use the project-kb skill.
- Check current code, tests, and checked-in docs before trusting Obsidian notes.
- If Obsidian conflicts with current code, treat current code and verification output as implementation truth.
- Before writing to Obsidian, state the target note path, summary, and reason.
```

Skill 职责：

- 判断何时查询 KB
- 调用 MCP 工具
- 引用 note path
- 限制检索笔记数量
- 只在验证后写回

### 16.2 Claude Code

文件：

```text
CLAUDE.md
.claude/skills/project-kb/SKILL.md
.claude/commands/wiki.md optional
```

`CLAUDE.md` 片段：

```md
@AGENTS.md

## Project KB

Use the project-kb skill before architecture, refactor, historical decision, or long-running task work.
```

注意：

- 不依赖 slash command 注册作为核心能力。
- hooks 可以用来加载 `hot.md`，但不能作为唯一上下文恢复路径。
- CLI/MCP 合同是稳定核心。

### 16.3 OpenClaw

OpenClaw 角色：

- 注册 Project KB MCP
- 把 `project-kb` 暴露为 agent skill 或 plugin workflow
- 把托管的 Codex/Claude 会话路由到同一个知识源

规则：

- OpenClaw 不是知识真相源。
- OpenClaw 不应为同一项目事实创建平行 memory 系统。
- 写回仍走 Project KB MCP Facade。

### 16.4 通用 Agent CLI

最小 adapter：

```text
Read AGENTS.md
Use kb CLI if MCP unavailable
Never delete or overwrite notes
Write append-only logs
```

## 17. 安全与权限

### 17.1 权限等级

| 等级 | 允许操作 | 目标阶段 |
|---|---|---|
| Read-only | project_find, search, read, staleness check | P0 默认 |
| Append-only | append_log | P0 校验后 |
| Structured write | create_decision, update status | P1 |
| Destructive | delete, rename, overwrite, bulk rewrite | 默认拒绝 |

### 17.2 密钥策略

系统不得写入：

- API keys
- tokens
- passwords
- private keys
- cookies
- connection strings
- local-only credential files

`kb validate` 和写入路径应在保存前扫描明显 secret pattern。

### 17.3 外部访问披露

每个 adapter 或 skill 应明确披露：

- 是否使用网络访问
- 是否访问 vault 之外的文件
- 是否调用远程 LLM API
- 是否存储 telemetry
- 是否依赖付费服务

这与 Obsidian 插件治理要求保持一致。

## 18. 里程碑

### Milestone 0: 环境证明

耗时：0.5-1 天

任务：

- 选择 vault 路径
- 如果使用 `mcp-obsidian`，安装 Obsidian Local REST API
- 如果可用，验证 Obsidian CLI
- 验证一次 read/search 操作
- 确认 config 文件里没有密钥

退出标准：

- 能读取一条 note
- 能搜索一条 note
- 普通 Project KB surface 不能删除 note

### Milestone 1: Vault Schema 和模板

耗时：1-2 天

任务：

- 创建项目模板
- 创建 ADR 模板
- 创建模块模板
- 创建日志模板
- 定义 schema version
- 创建示例项目

退出标准：

- `kb init-project` 创建预期布局
- note 能在 Obsidian 中正常渲染
- frontmatter 可解析

### Milestone 2: CLI P0

耗时：2-3 天

任务：

- 实现 `kb init-project`
- 实现 `kb validate`
- 实现 `kb status`
- 实现 `kb transport detect`

退出标准：

- validation 能发现缺失必填字段
- validation 能发现非法 status
- validation 能发现明显 secret 字符串

### Milestone 3: MCP Facade P0

耗时：3-5 天

任务：

- 实现 `kb.project_find`
- 实现 `kb.search`
- 实现 `kb.read`
- 实现 `kb.append_log`
- 实现 `kb.check_staleness`
- 为 append 增加 lock 和 audit

退出标准：

- Codex 或 Claude 能调用 search/read/append
- append 写入预期月度日志
- lock 防止并发破坏
- 原始 delete/overwrite 不可用

### Milestone 4: Agent Adapter

耗时：2-4 天

任务：

- Codex skill 和 AGENTS 片段
- Claude skill/command 和 CLAUDE 片段
- OpenClaw skill/plugin 指令
- 通用 CLI fallback 指令

退出标准：

- Codex 能检索并引用 note
- Claude Code 能检索并引用同一条 note
- OpenClaw 会话能通过同一个 MCP 检索
- 所有 adapter 使用同一套项目 schema

### Milestone 5: 10 个真实任务试点

耗时：1-2 周

任务：

- 在 10 个真实项目任务中使用系统
- 记录检索命中
- 记录过期 note 事件
- 记录写回事件
- 根据失败情况更新规则

退出标准：

- 有效检索命中率 >= 60%
- 过时/错误 note 误导 <= 1 次
- 平均检索 note <= 5 条/任务
- 所有写回都有来源

### Milestone 6: P1 扩展

耗时：试点后

任务：

- ADR 创建工具
- 项目状态更新工具
- BM25 检索
- 可选 contextual prefix
- 可选 Canvas/Base 视图

退出标准：

- 创建 ADR 必须带 source path 或 verification command
- status update 已校验
- 检索质量提升且上下文增长不过量

## 19. 验收标准

### 19.1 功能验收

- 可从模板创建项目。
- 可从 repo path 解析项目。
- agent 可搜索项目笔记。
- agent 可读取有边界的笔记内容。
- agent 可追加已验证任务日志。
- CLI 可校验项目知识结构。
- agent 使用项目知识时引用 note path。
- 写入有 audit log。
- 危险原始操作不暴露。

### 19.2 跨 Agent 验收

- Codex 可使用 KB。
- Claude Code 可使用 KB。
- OpenClaw 可路由到同一 KB。
- 通用 CLI fallback 可通过 `kb` 命令工作。

### 19.3 安全验收

- 默认不能 delete。
- 默认不能 full overwrite。
- 不能 vault-wide rewrite。
- secret-like 内容会被标记。
- 并发 append 不破坏文件。

### 19.4 质量验收

- note 在 Obsidian 中正确渲染。
- frontmatter 可被机器解析。
- 内部链接有效。
- search 结果有边界且相关。
- 可检测 stale notes。

## 20. 指标

运行指标：

- 每个任务的 KB search 次数
- 每个任务的 note read 次数
- 每个任务的 write-back 次数
- validation failures
- stale note count
- lock contention count

质量指标：

- retrieval hit rate
- false positive retrieval rate
- stale note misguidance events
- average note count injected per task
- average context tokens from KB per task
- write-back acceptance rate

试点目标阈值：

```text
effective retrieval hit rate >= 60%
stale misguidance <= 1 event in 10 tasks
average injected notes <= 5
100% write-backs include provenance
0 destructive write incidents
```

## 21. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 笔记与代码漂移 | agent 可能做出错误决策 | 要求 `verified_commit`、staleness check 和 code-first 规则。 |
| 原始 MCP 暴露 delete/overwrite | 数据丢失 | 使用 Facade，默认拒绝破坏性工具。 |
| agent 读取过多内容 | token 浪费 | 限制 search 结果，要求 section read。 |
| hook 行为因宿主不同而不一致 | 上下文恢复失败 | hooks 只做增强，核心是 CLI/MCP。 |
| slash command 未注册 | agent UX 失败 | command 只是 adapter，不是核心能力。 |
| 多 agent 写入竞争 | note 损坏 | per-file lock，先 append-only。 |
| Obsidian 插件变化 | transport 失效 | transport fallback chain。 |
| 密钥写入笔记 | 凭证泄露 | 写入路径和 validate 进行 secret scan。 |
| 跨 agent 规则漂移 | 行为不一致 | 从共享模板生成 adapters。 |

## 22. 实施建议

按以下顺序构建：

1. Vault templates 和 schema。
2. CLI validation。
3. MCP Facade read/search。
4. Append-only write-back。
5. Codex adapter。
6. Claude Code adapter。
7. OpenClaw adapter。
8. 用 10 个真实任务试点。
9. 增加 ADR 创建和状态更新。
10. 如果 P0 检索不够，再增加 BM25 retrieval。

不要从以下事项开始：

- complex vector DB
- auto-reorganizing the vault
- full Claude plugin replication
- raw `mcp-obsidian` exposure
- destructive write workflows

## 23. 初始 Backlog

### Epic 1: Vault Schema

- 定义 project frontmatter schema。
- 定义 ADR schema。
- 定义 module schema。
- 定义 task log schema。
- 创建 note templates。

### Epic 2: CLI

- 实现 project initialization。
- 实现 validation。
- 实现 status reporting。
- 实现 transport detection。

### Epic 3: MCP Facade

- 实现 project resolution。
- 实现 bounded search。
- 实现 note read。
- 实现 append log。
- 实现 staleness check。
- 增加 audit log。

### Epic 4: Write Safety

- 增加 per-file lock。
- 增加 stale lock cleanup。
- 增加 secret scan。
- 增加 write validation。

### Epic 5: Agent Adapters

- Codex `project-kb` skill。
- Codex `AGENTS.md` snippet。
- Claude `CLAUDE.md` snippet。
- Claude skill/command wrapper。
- OpenClaw skill/plugin wrapper。
- Generic CLI instructions。

### Epic 6: Pilot and Metrics

- 跑 10 个任务。
- 收集 retrieval metrics。
- 收集 write-back metrics。
- 复盘失败。
- 决定 P1 scope。

## 24. 开放问题

1. 所有项目放进一个全局 vault，还是每个 repo 单独一个 vault？
2. P0 后 write-back 默认启用，还是每个任务都手动确认？
3. Windows 上 primary transport 应该是 Obsidian CLI、Local REST API，还是 filesystem？
4. 项目笔记是否和源码 repo 一起 Git version，还是放在独立 vault repo？
5. Facade 应使用 Python、TypeScript，还是其他 runtime？
6. OpenClaw 应托管 MCP server，还是只注册外部 MCP server？

推荐默认值：

- 一个全局 vault，结构为 `Projects/<ProjectName>`。
- 明确任务完成后允许 append-only write-back。
- Facade 是 primary，transport 是内部实现。
- 如果知识跨仓库共享，使用独立 vault repo。
- TypeScript 或 Python，取决于本地 agent 工具链。

## 25. 附录：Adapter 示例片段

### 25.1 Codex Skill Trigger

```md
---
name: project-kb
description: Use when a task involves architecture, long-running project context, historical decisions, module boundaries, known pitfalls, or cross-agent project knowledge.
---

# Project KB

1. Resolve the project with `kb.project_find`.
2. Read `hot.md` if available.
3. Search only for task-relevant notes.
4. Read at most 5 notes unless the user asks for deeper research.
5. Treat current code, tests, and checked-in docs as implementation truth.
6. Append a task log only after verification.
```

### 25.2 Claude Code Command

```md
---
description: Resolve the current repository to a Project KB entry and show recent context.
---

Use the project-kb skill.
Resolve the current repository.
Read the project hot cache.
Summarize current context and ask what task to continue.
```

### 25.3 OpenClaw Skill Rule

```md
# Project KB for OpenClaw

For coding or project maintenance tasks:

1. Resolve repo to project through Project KB MCP.
2. Search/read project notes only when they materially help.
3. Do not write unless the task was verified or the user explicitly requests a note.
4. Use append-only logs by default.
5. Do not expose delete or overwrite operations.
```

## 26. 附录：参考链接

- Obsidian releases and community plugin directory: https://github.com/obsidianmd/obsidian-releases
- Obsidian developer docs: https://docs.obsidian.md
- kepano Obsidian skills: https://github.com/kepano/obsidian-skills
- claude-obsidian: https://github.com/AgriciDaniel/claude-obsidian
- mcp-obsidian: https://github.com/MarkusPfundstein/mcp-obsidian
- Obsidian Local REST API: https://github.com/coddingtonbear/obsidian-local-rest-api
