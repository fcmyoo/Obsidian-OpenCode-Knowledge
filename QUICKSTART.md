# 快速开始

> 目标：2 分钟内完成第一次知识库测试。

## 前提
- 已安装 Obsidian
- 已克隆本仓库
- 已运行 `bash setup.sh`

## 快速测试命令

在 OpenCode / AI 助手里直接发送：

```
把这个加到 wiki：

标题：我的第一篇 AI 笔记
内容：
- 今天学到了 OpenCode + Obsidian 知识库方案
- 关键点：本地部署、自动整理、定期体检
```

观察 AI 是否完成：
- 创建 `raw/` 原始素材
- 生成 `wiki/` 消化笔记
- 更新 `wiki/index.md`
- 追加 `wiki/log.md`

## 验证清单

- [ ] Obsidian 左侧边栏能看到 OpenCode 面板
- [ ] `wiki/index.md` 出现新条目
- [ ] `wiki/log.md` 有最新操作记录
- [ ] 运行 `lint wiki` 无报错
