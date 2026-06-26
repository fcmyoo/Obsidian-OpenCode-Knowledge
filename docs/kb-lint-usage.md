# KB Lint Usage

> 知识库质量检查脚本的使用说明。

## 1. 基本用法

```bash
bash scripts/kb-lint-check.sh "$HOME/Desktop/我的知识库"
```

脚本会检查：
- vault 和 wiki 目录存在性
- `wiki/index.md` 存在性
- wiki 内部链接有效性
- `index.md` 对 wiki 文件的覆盖情况
- wiki -> `raw/` 来源链接有效性
- 孤岛页面候选
- frontmatter 完整率
- 标签重复度

## 2. 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `KB_LINT_JSON` | 输出 JSON 格式 | `0` |
| `KB_TAG_DUPLICATE_THRESHOLD` | 标签重复告警阈值 | `2` |

示例：

```bash
KB_LINT_JSON=1 bash scripts/kb-lint-check.sh "$HOME/Desktop/我的知识库"
```

## 3. CI 集成

本仓库提供 GitHub Actions 工作流：

```bash
.github/workflows/kb-lint.yml
```

触发条件：
- `vault-template/**` 变更
- `docs/**` 变更
- `scripts/kb-lint-check.sh` 变更
- `tests/test_kb_lint_check.py` 变更

## 4. 常见问题

### Q1: 为什么 `使用指南.md` 报告 missing from index？

模板默认状态，后续补齐 `wiki/index.md` 即可。

### Q2: 如何降低标签重复告警？

调整环境变量：

```bash
KB_TAG_DUPLICATE_THRESHOLD=5 bash scripts/kb-lint-check.sh "$HOME/Desktop/我的知识库"
```

### Q3: 如何只检查链接？

当前脚本为全量检查；如需单点检查，可直接 grep：

```bash
grep -oE '\[[^][]+\]\(([^)]+)\)' wiki/*.md | sed -E 's/.*\]\(([^)]+)\)/\1/'
```
