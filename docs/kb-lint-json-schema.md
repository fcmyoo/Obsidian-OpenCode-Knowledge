# KB Lint JSON Schema

> 知识库质量检查脚本的 JSON 输出格式说明。

## 1. 环境变量

| 脚本 | 环境变量/参数 | 说明 |
|------|---------------|------|
| `scripts/kb-lint-check.sh` | `KB_LINT_JSON=1` | 启用 JSON 输出 |
| `scripts/kb-lint-check.ps1` | `-JsonMode 1` | 启用 JSON 输出 |

## 2. 顶层结构

```json
{
  "vault": "<vault path>",
  "issues": [
    {
      "check": "string",
      "status": "ok | error",
      "path": "string",
      "count": "number"
    }
  ],
  "warnings": [
    {
      "check": "string",
      "message": "string"
    }
  ],
  "errors": [
    {
      "check": "string",
      "message": "string"
    }
  ],
  "exitCode": "number"
}
```

## 3. 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `vault` | string | 检查的 vault 路径 |
| `issues` | array | 检查项结果数组 |
| `issues.check` | string | 检查项名称 |
| `issues.status` | string | `ok` 或 `error` |
| `issues.path` | string | 相关路径 |
| `issues.count` | number | 错误数量 |
| `warnings` | array | 警告信息数组 |
| `warnings.check` | string | 检查项名称 |
| `warnings.message` | string | 警告详情 |
| `errors` | array | 错误信息数组 |
| `errors.check` | string | 检查项名称 |
| `errors.message` | string | 错误详情 |
| `exitCode` | number | 脚本退出码 |

## 4. 检查项名称

- `vault`
- `wiki_directory`
- `index_file`
- `broken_links`
- `raw_links`
- `orphaned_pages`
- `frontmatter`
- `tag_duplicates`

## 5. CI 使用示例

```yaml
- name: Run KB lint script
  run: |
    JSON=$(bash scripts/kb-lint-check.sh "$GITHUB_WORKSPACE/vault-template")
    echo "$JSON" > kb-lint-report.json
```
