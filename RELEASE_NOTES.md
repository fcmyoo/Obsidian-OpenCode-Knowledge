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

## 状态

- 已推送 `main` 到远程：`fc38d6d`

## 待做

- [ ] 创建 release
- [ ] 监控 GitHub Actions
- [ ] 继续补充工具模板可执行示例
