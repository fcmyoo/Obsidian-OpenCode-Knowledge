---
name: project-kb
description: Use when a task involves architecture, long-running project context, historical decisions, module boundaries, known pitfalls, or cross-agent project knowledge.
---

# Project KB

Use this skill to access the shared project knowledge vault through the Project KB CLI or MCP facade.

Vault resolution order is `--vault`, `PROJECT_KB_VAULT`, repo-local `.project-kb/project.json`, then `./vault`.

## Read Flow

1. Resolve the project:
   ```bash
   python scripts/kb.py project-find --repo "<repo-path>"
   ```
2. Read `hot.md` if the project has one.
3. Retrieve only task-relevant chunks when the query is exploratory:
   ```bash
   python scripts/kb.py retrieve --project "<Project>" --query "<query>" --limit 5
   ```
4. Search only for task-relevant notes when you need note-level hits or type filters:
   ```bash
   python scripts/kb.py search --project "<Project>" --query "<query>" --limit 5
   ```
5. Read exact notes or sections only when the retrieved chunk is not enough.
6. Cite note paths in the response when a note materially influenced the answer.

## Truth Boundary

- Current code, tests, command output, and checked-in docs are implementation truth.
- Obsidian notes record history, decisions, explanations, and task context.
- If notes conflict with current code or verification output, trust the current code and mention the stale note.

## Write Flow

Only write after verification or explicit user request.

1. State target note path, summary, and reason.
2. Use append-only task logs by default:
   ```bash
   python scripts/kb.py append-log --project "<Project>" --from-file summary.json
   ```
3. Do not write secrets.
4. Do not delete, overwrite full notes, batch move, batch rename, or rewrite the vault.

## Access Disclosure

- Network access: none by default for filesystem-backed CLI/MCP use; optional host or Obsidian Local REST transports may use localhost or user-configured endpoints.
- Vault-external files: reads the configured source repository only when resolving repo paths, validating `source_paths`, or when the human/agent separately inspects source files.
- Remote LLM API: none in Project KB CLI/MCP; any model calls come from the surrounding agent host, not this skill.
- Telemetry: none emitted by Project KB CLI/MCP.
- Paid services: none required by Project KB CLI/MCP.
