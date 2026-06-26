# Project KB Agent Adapters

Adapters are thin rules around the same Project KB CLI/Core contract. They should not become separate knowledge stores.

## Shared Rules

- Use Project KB for architecture, historical decisions, module boundaries, known pitfalls, and long-running task context.
- Check current code, tests, and checked-in docs before trusting notes.
- If notes conflict with current code or verification output, treat current code and verification output as implementation truth.
- Default read flow: project find, read `hot.md`, search task-relevant notes, read at most 5 notes.
- Default write flow: append task logs only after verification.
- Before writing, state the target note path, summary, and reason.
- Never expose delete, full overwrite, batch move, batch rename, or vault-wide rewrite as ordinary agent tools.
- Do not write API keys, tokens, passwords, private keys, cookies, connection strings, or local-only credential files.

## Access Disclosure

Every generated adapter and project-kb skill must disclose the same operating boundary:

- Network access: none by default for filesystem-backed CLI/MCP use; optional host or Obsidian Local REST transports may use localhost or user-configured endpoints.
- Vault-external files: reads the configured source repository only when resolving repo paths, validating `source_paths`, or when the human/agent separately inspects source files.
- Remote LLM API: none in Project KB CLI/MCP; any model calls come from the surrounding agent host, not the adapter.
- Telemetry: none emitted by Project KB CLI/MCP.
- Paid services: none required by Project KB CLI/MCP.

## Host Config Snippets

Run `python scripts/kb.py export-host-configs --project <Project>` to write auditable MCP host-registration aids under `Projects/<Project>/.vault-meta/host-configs/`.

The exported snippets are documentation artifacts, not automatic host registration. Before pasting them into Codex, Claude Code, OpenClaw, or another host, verify the current host config format and keep `PROJECT_KB_VAULT` pointed at the intended vault.

Run `python scripts/kb.py install-repo-adapters --project <Project> --repo <repo>` to write repo-local drafts under `.project-kb/host-configs/`:

- `codex.config.toml`
- `claude.mcp.json`
- `openclaw.mcp.json5`
- `opencode.md`
- `README.md`

These drafts are intended for review and copy/paste into the real host configuration. They do not edit `~/.codex`, Claude Code config, OpenClaw config, or any global profile.

## Codex

Repo or vault files:

- `AGENTS.md`
- `.codex/config.toml` optional repo-local MCP draft
- `.codex/skills/project-kb/SKILL.md`
- `.project-kb/host-configs/codex.config.toml` optional MCP draft

Suggested `AGENTS.md` snippet:

```md
## Project Knowledge

- For architecture, historical decisions, module boundaries, long-running tasks, and known pitfalls, use the project-kb skill.
- Check current code, tests, and checked-in docs before trusting Obsidian notes.
- If Obsidian notes conflict with current code, treat current code and verification output as implementation truth.
- Before writing to Obsidian, state the target note path, summary, and reason.
```

## Claude Code

Repo or vault files:

- `CLAUDE.md`
- `.claude/skills/project-kb/SKILL.md`
- `.claude/commands/wiki.md` optional convenience command
- `.project-kb/host-configs/claude.mcp.json` optional MCP draft

Suggested `CLAUDE.md` snippet:

```md
@AGENTS.md

## Project KB

Use the project-kb skill before architecture, refactor, historical decision, or long-running task work.
```

## OpenClaw

OpenClaw should register or route to the same Project KB CLI/MCP facade. It should not create a parallel memory system for the same project facts.

Use `.project-kb/host-configs/openclaw.mcp.json5` as an external MCP registration draft and adapt it to the current OpenClaw config schema before enabling it.

Minimum workflow:

1. Resolve repo to project through Project KB.
2. Read/search only when notes materially help.
3. Write only verified append-only logs unless the user explicitly asks for a note.
4. Keep destructive note operations unavailable.

## OpenCode

OpenCode should use the same Project KB CLI/MCP facade and repo-local skill entrypoints instead of inventing a separate project fact store.

Use `.opencode/skill/project-kb/SKILL.md` for the workflow boundary and `.project-kb/host-configs/opencode.md` as the local MCP registration draft when OpenCode needs host-side wiring help.

## Generic Agent CLI

Minimum fallback:

1. Read the repository `AGENTS.md`.
2. Use `python scripts/kb.py project-find --repo <repo>`.
3. Use `search` and `read` with a limit of 5 notes.
4. Use `append-log` only after verification.
5. Never delete or overwrite notes.
