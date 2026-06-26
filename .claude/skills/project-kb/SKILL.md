---
name: project-kb
description: Use before architecture, refactor, historical decision, module boundary, known pitfall, or long-running task work.
---

# Project KB

Use the shared Project KB CLI/MCP facade instead of Claude-only memory when project facts should be inspectable by humans and other agents.

Vault resolution order is `--vault`, `PROJECT_KB_VAULT`, repo-local `.project-kb/project.json`, then `./vault`.

## Read Flow

```bash
python scripts/kb.py project-find --repo "<repo-path>"
python scripts/kb.py retrieve --project "<Project>" --query "<query>" --limit 5
python scripts/kb.py read --path "Projects/<Project>/hot.md"
```

Use `retrieve` for bounded BM25-ranked chunks, then `read` exact notes or sections only when more context is needed. Treat code, tests, command output, and checked-in docs as implementation truth.

## Write Flow

Write only after verification or explicit user request:

```bash
python scripts/kb.py append-log --project "<Project>" --from-file summary.json
```

Never expose delete, full-note overwrite, batch move, batch rename, or vault-wide rewrite as ordinary workflow steps.

## Access Disclosure

- Network access: none by default for filesystem-backed CLI/MCP use; optional host or Obsidian Local REST transports may use localhost or user-configured endpoints.
- Vault-external files: reads the configured source repository only when resolving repo paths, validating `source_paths`, or when the human/agent separately inspects source files.
- Remote LLM API: none in Project KB CLI/MCP; any model calls come from the surrounding agent host, not this skill.
- Telemetry: none emitted by Project KB CLI/MCP.
- Paid services: none required by Project KB CLI/MCP.
