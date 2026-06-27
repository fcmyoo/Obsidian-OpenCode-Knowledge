# QUICKSTART

> 2 分钟上手你的 AI 知识库

## 1. 复制 Vault

把 `vault-template` 复制到 Obsidian 能打开的目录，例如：

```bash
cp -R vault-template "$HOME/Desktop/我的知识库"
```

## 2. 在 Obsidian 中打开

打开 Obsidian → 打开文件夹作为仓库 → 选择 `我的知识库`

## 3. 试试第一条指令

在 OpenCode / AI 面板输入：

```text
把这个加到 wiki：

[粘贴一篇短文或笔记内容]
```

AI 会自动：
- 存到 `raw/`
- 生成 wiki 笔记
- 更新 `wiki/index.md`
- 记录 `wiki/log.md`

## 4. 查一下有没有生效

```text
我的 wiki 里关于 XX 有什么？
```

## 5. 每周体检一次

```text
lint wiki
```
