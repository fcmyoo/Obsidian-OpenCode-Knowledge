# AI Tools Integration

> Unified onboarding for multiple AI coding agents to use this knowledge base.

## 1. Supported Tools

- Claude Code
- Codex
- OpenCode / OpenClaw
- Reasonix
- Hermes

## 2. Common Setup

1. Clone the repo
2. Open the vault in Obsidian
3. Configure the tool-specific instructions file to load `AGENTS.md` or the relevant skill

## 3. Tool Configs

### Claude Code

Create or update the project instruction file:

- `.claude/CLAUDE.md` (root)
- Optionally add repo-local instructions in `.claude/`

Ensure these rules are respected:
- Do not edit `raw/`
- Update `wiki/index.md` and `wiki/log.md` after changes
- Use relative paths for internal wiki links

### Codex

Use the repo-level instructions file:

- Root: `AGENTS.md`
- Optional: `.codex/instructions.md`

Load the vault template rules from `vault-template/AGENTS.md` for knowledge base workflows.

### OpenCode / OpenClaw

Use the built-in skill system:

- Skills root: `.opencode/skill/`
- Vault skills: `vault-template/.opencode/skill/`

When working inside the vault, load `vault-template/AGENTS.md` and `vault-template/AI_CONFIG.md`.

### Reasonix

Use project and global instructions:

- Project: `AGENTS.md`
- Repo-local: `.reasonix/instructions.md`

Include the knowledge base workflow and privacy rules in the instruction set.

### Hermes

Use the project instructions file:

- Root: `AGENTS.md`
- Repo-local instructions: `.hermes/instructions.md`

If Hermes supports skill loading, point it to `.opencode/skill/` for vault operations.

## 4. Cross-Tool Invariants

All tools should follow these constraints regardless of interface:

- `raw/` is append-only and read-only for AI
- `wiki/` is AI-maintained output
- `assets/` contains media referenced from raw/wiki
- `wiki/index.md` and `wiki/log.md` must stay consistent with wiki content
- External URLs belong in raw frontmatter only

## 5. Troubleshooting

- If a tool ignores vault rules, verify it loads the correct instructions file for this repo
- If skills are missing, confirm the tool supports local skill/plugin loading
- If paths break, re-check relative link rules in `vault-template/AGENTS.md`
