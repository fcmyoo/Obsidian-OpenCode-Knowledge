# TROUBLESHOOTING

> 常见问题与修复建议

## OpenCode 面板没出现
- 确认 `opencode` 已安装：`opencode --version`
- 确认 Obsidian 插件已启用
- 重启 Obsidian

## AI 没按 wiki 规则执行
- 确认仓库根目录有 `AGENTS.md`
- 确认 Vault 根目录有 `wiki/` 和 `raw/`
- 重启对话或新开会话

## 安装 OpenCLI 失败
```bash
npm install -g @jackwener/opencli
```

如果仍失败，检查 npm 权限或网络。

## 笔记写错目录
- raw 素材放 `raw/` 或 `raw/social/<知识域>/`
- wiki 结果看 `wiki/`
- 图片建议放 `assets/`

## 想重置 AI 配置
- 编辑 `AI_CONFIG.md`
- 重启 OpenCode 会话后生效

## 运行 lint 报错
```bash
bash scripts/kb-lint-check.sh "$(pwd)/vault-template"
```

先确认 `vault-template/wiki/index.md` 存在。
