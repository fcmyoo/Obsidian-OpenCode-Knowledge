[根目录](../../CLAUDE.md) > **vault-template**

# vault-template

> Obsidian vault 模板，AI 知识库的核心结构。

## 模块职责

提供完整的 Obsidian vault 模板，包含：
- AI 行为规则（AGENTS.md）
- 用户可配置 AI 行为（AI_CONFIG.md）
- 消化笔记目录（wiki/）
- 原始素材目录（raw/）
- 配图目录（assets/）
- 预装 AI 技能（.opencode/skill/，9个技能）

## 入口与启动

这不是一个可执行项目，而是部署时复制到用户电脑上的模板。部署入口为仓库根的 `setup.sh`。

关键文件：
- `AGENTS.md` - AI 规则（opencode 启动时自动加载）
- `AI_CONFIG.md` - 用户自定义配置
- `wiki/index.md` - 全局索引（AI 自动维护）
- `wiki/log.md` - 操作日志（AI 自动追加）

## 对外接口

### 目录结构（部署后）

```
我的知识库/
├── AGENTS.md               # AI 规则
├── AI_CONFIG.md            # AI 配置（用户可编辑）
├── raw/                   # 原始素材（AI 只读）
│   └── social/            # 社交媒体内容（按知识域分类）
│       ├── 消费研究/
│       ├── 技能方法/
│       ├── 行业洞察/
│       ├── 生活方式/
│       ├── 观点思考/
│       ├── 创意灵感/
│       └── 资源收藏/
├── wiki/                  # AI 维护的消化笔记
│   ├── index.md           # 全局索引
│   ├── log.md             # 操作日志
│   └── 使用指南.md         # 使用说明
├── assets/                # 配图资源
└── .opencode/skill/      # AI 技能（9个）
```

### AI 四个触发行为

| 触发词 | 行为 | 说明 |
|--------|------|------|
| "加到 wiki"、"ingest 这个" | Ingest | 录入素材到 raw/ 和 wiki/ |
| "我知道啥关于"、"wiki 里有没有" | Query | 查询知识库内容 |
| "lint wiki"、"体检" | Lint | 检查知识库健康度 |
| "爬了这个"、"收录这条" | Social Ingest | 社交媒体内容录入 |

## 关键依赖与配置

- **OpenCode**: AI 助手运行时
- **Obsidian**: 笔记软件
- **AI_CONFIG.md 可配置项**:
  - `language`: 输出语言（zh/en）
  - `triggers`: 触发词自定义
  - `domains`: 知识域分类
  - `platforms`: 社交平台
  - `content_types`: 内容类型
  - `polish`: 润色规则
  - `lint_checks`: 体检检查项

## 数据模型

### raw/ 素材文件

原始素材，AI 只读不改。文件名保持原样（PDF/视频/图片）或起描述性名（md 笔记）。

### wiki/ 消化笔记

AI 维护的结构化笔记。每篇文章 md 格式，命名自由。

### frontmatter 规范（社交媒体）

```yaml
---
title: 标题
source: Xiaohongshu | Douyin | ...
author: 作者名
created: YYYY-MM-DD
note_url: 原始链接
domain: 消费研究 | ...
content_type: 实测体验 | ...
credibility: high | medium | low
metrics:
  likes: 0
  collects: 0
  comments: 0
tags: []
---
```

## 测试与质量

本模块为模板文件，无传统测试。主要验证方式：
- 部署后在 Obsidian 中打开 vault
- 测试 AI 对话是否正常
- 验证 `lint wiki` 等触发行为

## 常见问题 (FAQ)

**Q: 如何自定义 AI 行为？**
A: 编辑 `AI_CONFIG.md`，修改后下次对话自动生效。

**Q: raw/ 里的文件会被 AI 修改吗？**
A: 不会。raw/ 是只读的，AI 永不修改。

**Q: wiki 的 Sources 链接到哪？**
A: 必须链接到本地 raw 文件，使用相对路径（如 `[素材标题](../../raw/social/消费研究/xxx.md)`），禁止使用外部 URL。

## 相关文件清单

- `AGENTS.md` - AI 行为规则（核心）
- `AI_CONFIG.md` - 用户可配置项
- `wiki/index.md` - 全局索引模板
- `wiki/log.md` - 操作日志模板
- `wiki/使用指南.md` - 使用说明
- `.opencode/skill/` - 9个预装 AI 技能
- `.claude/skills/project-kb/SKILL.md` - 跨 agent 项目知识 skill

## 变更记录 (Changelog)

- **2026-04-22**: 初始化模块文档
- **2026-06-23**: 增加 Project KB 跨 agent 项目知识适配说明
