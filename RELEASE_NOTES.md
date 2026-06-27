# Release Notes

## [Unreleased]

### Added
- Non-interactive installer: `scripts/installer/install.sh` and `scripts/installer/install.ps1`
- Knowledge base docs: `docs/knowledge-workflow.md`, `docs/knowledge-maintenance.md`, `docs/git-policy.md`, `docs/quality-metrics.md`, `docs/plugin-recommendations.md`, `docs/privacy-and-security.md`
- AI tools integration doc: `docs/ai-tools-integration.md`
- CI workflows: `.github/workflows/ci.yml`, `.github/workflows/installer-smoke-test.yml`, `.github/workflows/kb-quality-check.yml`
- Quality check script: `scripts/kb-quality-check.sh`
- Multi-tool onboarding files: `.claude/CLAUDE.md`, `.codex/instructions.md`, `.reasonix/instructions.md`, `.hermes/instructions.md`
- KB lint improvements: removed jq dependency, added Windows PowerShell lint tests, made CI non-blocking
- Vault template examples: added sample wiki notes and raw social content structure
- Documentation: added QUICKSTART.md, TROUBLESHOOTING.md, and assets guide
- CI coverage: added Windows job for project KB tests

### Changed
- Updated `README.md` and `README.en.md` with environment checks, installer examples, and doc links
- Improved `.gitignore` to exclude local runtime artifacts
- Fixed OpenCLI package references across setup scripts and documentation
- Enhanced test coverage for kb-lint scripts (bash and PowerShell)

### Fixed
- Fixed PowerShell installer path resolution and dry-run behavior
- Fixed relative link resolution in kb-lint-check.sh for wiki root links
- Fixed frontmatter detection in PowerShell lint script
- Corrected OpenCLI package name and repository URLs in documentation


- [x] 创建 release
- [x] 监控 GitHub Actions
- [ ] 继续补充工具模板可执行示例
