# 常见问题排查

## 连接问题

### OpenCode 面板显示「连接失败」
1. 确认网络正常
2. 检查 `~/.config/opencode/opencode.json` 里的 API Key
3. 终端运行 `opencode` 看能否启动

### 端口占用
```bash
bash scripts/opencode-obsidian-doctor.sh --vault "$HOME/Desktop/我的知识库" --kill-port
```

## 安装问题

### Node.js 安装失败
- macOS：重新运行 `bash setup.sh`，选择重新安装 Node.js
- Windows：以管理员身份运行 PowerShell，再执行 `setup.ps1`

### OpenCLI 安装失败
```bash
npm install -g @jackwener/opencli
```

## 笔记问题

### 笔记没有自动索引
- 检查 frontmatter 是否包含 `title/source/created/domain`
- 手动运行 `lint wiki` 查看告警

### 图片不显示
- 使用相对路径：`![](assets/xiaohongshu/<笔记标题>/image.jpg)`
- 确认图片已复制到 `assets/` 目录

## 重置配置

如果配置混乱，可以重置：

```bash
# 备份后删除配置
mv ~/.config/opencode/opencode.json ~/.config/opencode/opencode.json.bak
# 重新运行 setup
bash setup.sh
```
