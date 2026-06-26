# Project KB MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P0 filesystem-backed Project KB from `docs/project-kb-cross-agent-prd-cn.md`.

**Architecture:** `project_kb/core.py` owns schema, validation, search, read, append-only log writes, lock files, and audit records. `scripts/kb.py` is a thin JSON CLI wrapper that can later be called from MCP facade/adapters.

**Tech Stack:** Python 3 standard library, Markdown/YAML-like frontmatter, JSON audit/manifest files, Windows/macOS compatible file operations.

---

## Scope

This MVP implements the PRD's P0/P0-adjacent surface:

- Vault schema and project templates.
- CLI commands: `init-project`, `validate`, `status`, `transport detect`, `project-find`, `search`, `read`, `append-log`, `stale`.
- Append-only log writes with per-file lock and audit JSONL.
- Secret-like content detection during validation and writes.
- Thin Codex, Claude Code, OpenClaw, and generic CLI adapter guidance.

Out of scope for this pass:

- Vector search and model-based rerankers.
- Real MCP server process.
- Obsidian Local REST API integration.
- Destructive note operations.
- Automatic vault-wide restructuring.

## Files

- Create: `project_kb/__init__.py`
- Create: `project_kb/core.py`
- Create: `scripts/kb.py`
- Create: `tests/test_project_kb.py`
- Create: `docs/project-kb/cli.md`
- Create: `docs/project-kb/agent-adapters.md`
- Create: `vault-template/.opencode/skill/project-kb/SKILL.md`
- Create: `vault-template/.claude/skills/project-kb/SKILL.md`
- Create: `vault-template/.claude/commands/wiki.md`
- Modify: `README.md`

## Tasks

- [x] Add failing standard-library tests for P0 CLI behavior.
- [x] Implement filesystem-backed Project KB core.
- [x] Implement thin CLI wrapper with JSON output and non-zero validation failures.
- [x] Verify tests pass with `python -m unittest tests.test_project_kb -v`.
- [x] Add adapter and usage documentation.
- [x] Run final validation commands and inspect diff.
- [x] Add P1 structured writes: ADR creation, project status update, allowed frontmatter update.
- [x] Add P1 maintenance commands: index, retrieve, lock list, export-adapter.
- [x] Upgrade `index`/`retrieve` from simple note search to heading chunks with a local BM25 score and contextual prefixes.
- [x] Extend MCP facade with P1 structured tools while keeping destructive tools unavailable.
- [x] Extend validation for schema version, wikilinks, and generated-noise markers.
- [x] Add pilot event recording and metrics summary for the PRD trial thresholds.
- [x] Add repo-local `.project-kb/` adapter export for Codex, Claude, OpenClaw, and generic CLI agents.
- [x] Add host config export snippets for Codex, Claude, OpenClaw, and generic MCP hosts.
- [x] Add Obsidian-facing Canvas/Base view export for project map and note tables.
- [x] Restrict CLI/MCP `read` to Project KB Markdown notes and block `.vault-meta` internals.
- [x] Ensure per-file locks for root notes and nested notes stay under the owning project metadata directory.
- [x] Validate PRD-required sections for project, module, and decision notes.
- [x] Add task note schema, example template, and validation for PRD task-log fields.
- [x] Add machine-readable frontmatter to append-created monthly log notes.
- [x] Validate append-log target notes before committing writes and audit entries.
- [x] Track lock contention events and expose `lock_contention_count` in pilot metrics.
