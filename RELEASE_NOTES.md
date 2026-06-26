# Release Notes

## [Unreleased]

### Added
- Non-interactive installer: `scripts/installer/install.sh` and `scripts/installer/install.ps1`
- Knowledge base docs: `docs/knowledge-workflow.md`, `docs/knowledge-maintenance.md`, `docs/git-policy.md`, `docs/quality-metrics.md`, `docs/plugin-recommendations.md`, `docs/privacy-and-security.md`
- AI tools integration doc: `docs/ai-tools-integration.md`
- CI workflows: `.github/workflows/ci.yml`, `.github/workflows/installer-smoke-test.yml`, `.github/workflows/kb-quality-check.yml`
- Quality check script: `scripts/kb-quality-check.sh`
- Multi-tool onboarding files: `.claude/CLAUDE.md`, `.codex/instructions.md`, `.reasonix/instructions.md`, `.hermes/instructions.md`

### Changed
- Updated `README.md` and `README.en.md` with environment checks, installer examples, and doc links
- Improved `.gitignore` to exclude local runtime artifacts

### Fixed
- Fixed PowerShell installer path resolution and dry-run behavior

## 阻塞

- 推送被网络/代理阻断：`Failed to connect to github.com port 443 via 127.0.0.1`
- 待恢复后执行：`git push origin main`

## 待做

- [ ] 恢复网络后推送 `main`
- [ ] 监控 GitHub Actions
- [ ] 打 release
- [ ] 继续补充工具模板可执行示例
