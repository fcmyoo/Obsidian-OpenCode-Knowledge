# Knowledge Workflow

> 把 raw 素材稳定转换成 wiki 笔记的可执行 SOP。

## 1. 命名规范

### 1.1 raw

- 通用素材：`raw/<主题>/YYYY-MM-DD-来源-关键词.md`
- 社交素材：`raw/social/<domain>/<平台>-<作者>-YYYYMMDD.md`
- 非 Markdown 文件保留原名

### 1.2 wiki

按“核心主题”命名，不按 raw 文件名。
示例：`wiki/技能方法/本地知识库自动化.md`

## 2. frontmatter 最小集

```yaml
---
title: 标题
source: 来源
created: YYYY-MM-DD
domain: 知识域
content_type: 内容类型
---
```

其余字段按需补充。

## 3. 合并/新建判断

- 同核心论点：合并进现有文章
- 全新概念：新建文章
- 跨主题：主文章 + See Also

## 4. 输出检查

- 更新 `wiki/index.md`
- 追加 `wiki/log.md`
- 确认内部链接可用
