# Installer

> Plan for a non-interactive knowledge base installer that can run in CI or scripts.

## 1. Goal

Provide an automated path from repo checkout to a ready vault without manual prompts.

## 2. Scope

- Install dependencies
- Install OpenCode and OpenCLI
- Create vault from template at a custom path
- Generate plugin configuration

## 3. Interface

```bash
bash scripts/installer/install.sh --vault "$HOME/Desktop/我的知识库" --provider deepseek --api-key "$DEEPSEEK_KEY"
```

Flags:
- `--vault`
- `--provider`
- `--api-key`
- `--skip-plugin`

## 4. Behavior

- Use existing `setup.sh` logic where possible
- Default to non-interactive when flags are provided
- Preserve existing manual installer for users who prefer prompts

## 5. Future

- Add `install.ps1` for Windows automation
- Add `--dry-run` mode
