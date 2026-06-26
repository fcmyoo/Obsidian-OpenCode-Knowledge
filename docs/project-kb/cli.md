# Project KB CLI

`scripts/kb.py` implements the filesystem-backed P0 CLI described in `docs/project-kb-cross-agent-prd-cn.md`.

## Vault Selection

The CLI resolves the vault root in this order:

1. `--vault <path>`
2. `PROJECT_KB_VAULT`
3. Repo-local `.project-kb/project.json` when the command runs inside an installed repository
4. `./vault`

## Commands

```powershell
python scripts/kb.py init-project --name WeFlow --repo H:\code\github\WeFlow
python scripts/kb.py project-find --repo H:\code\github\WeFlow
python scripts/kb.py validate --project WeFlow
python scripts/kb.py doctor --project WeFlow
python scripts/kb.py status --project WeFlow
python scripts/kb.py transport detect --project WeFlow
python scripts/kb.py search --project WeFlow --query "diagnostics architecture" --limit 5
python scripts/kb.py read --path Projects/WeFlow/_index.md
python scripts/kb.py read --path Projects/WeFlow/modules/example.md --section "Known Pitfalls"
python scripts/kb.py append-log --project WeFlow --from-file summary.json
python scripts/kb.py stale --project WeFlow --commit HEAD
python scripts/kb.py create-decision --project WeFlow --title "Use safe facade" --source-path src/example.ts --verification-command "npm run typecheck"
python scripts/kb.py update-project-status --project WeFlow --status paused
python scripts/kb.py update-frontmatter-field --path Projects/WeFlow/modules/example.md --field confidence --value high
python scripts/kb.py index --project WeFlow
python scripts/kb.py retrieve --project WeFlow --query "PairPilot architecture" --limit 5
python scripts/kb.py lock list --project WeFlow
python scripts/kb.py export-adapter --agent codex --project WeFlow
python scripts/kb.py pilot plan --project WeFlow
python scripts/kb.py pilot record --project WeFlow --from-file pilot-event.json
python scripts/kb.py pilot status --project WeFlow
python scripts/kb.py metrics --project WeFlow
python scripts/kb.py install-repo-adapters --project WeFlow --repo H:\code\github\WeFlow
python scripts/kb.py export-host-configs --project WeFlow
python scripts/kb.py export-views --project WeFlow
python scripts/kb.py release check --project WeFlow --level engineering
python scripts/kb.py release check --project WeFlow --level engineering --commit HEAD --require-artifacts
python scripts/kb.py release check --project WeFlow --level environment
python scripts/kb.py release check --project WeFlow --level pilot
python scripts/kb.py release report --project WeFlow
```

`status` returns a compact project overview including the project `status`, `_index.md` `path`, configured `repo`, `hot` note path, `transport` mode, note counts by type, and validation totals.

`lock list` returns active per-file locks with their path, stale flag, and any recorded lock metadata such as `created_at` and `target`.

## Append Log Payload

`append-log --from-file` accepts a JSON object with provenance. Plain Markdown without provenance is rejected because Project KB write-backs must be tied to observable evidence.

```json
{
  "title": "Fix diagnostics panel filtering",
  "summary": "Implemented RAG-only diagnostics filtering and verified typecheck.",
  "repo": "H:/code/github/WeFlow",
  "branch": "codex/rag-diagnostics",
  "commit": "abc123",
  "files": ["src/a.ts"],
  "commands": ["npm run typecheck"],
  "source_paths": ["docs/diagnostics.md"],
  "url": "https://example.com/reference",
  "result": "passed",
  "follow_ups": ""
}
```

At least one provenance field must be non-empty: `commit`, `commands`, `files`, `source_paths`, `url`, `urls`, or `repo`.

The command writes to `Projects/<Project>/logs/YYYY-MM.md`, including source paths and URLs when present, creates machine-readable `type: log` frontmatter for new monthly logs, validates the target log note before committing the write, creates a project-relative per-file lock under `.vault-meta/locks/`, and appends an audit record to `.vault-meta/audit.jsonl`.

## Pilot Metrics Payload

`pilot plan` writes `Projects/<Project>/.vault-meta/pilot/plan.json`, a 10-task pilot plan that covers architecture/module understanding, implementation, verification, documentation/write-back, and multiple host entrypoints. It also writes editable event templates under `Projects/<Project>/.vault-meta/pilot/events/task-*.json`. These templates are planning artifacts only; the pilot gate still requires real task events recorded with `pilot record`.

`pilot record --from-file` accepts one JSON object per completed task. A task event is only accepted after `pilot plan` has frozen the 10-task plan. The `task_id` must match one planned task, all required event fields from the generated template must be present, and numeric counters must be non-negative integers. Invalid events are rejected before `events.jsonl` is written.

Each planned `task_id` can be recorded only once. Events preserve `status`, `host`, `category`, `notes`, and `evidence`; use `status: "environment_blocked"` when a required host was genuinely attempted but its runtime was unavailable. Otherwise use `status: "completed"`.

```json
{
  "task_id": "task-001",
  "title": "Use KB on real task",
  "searches": 2,
  "notes_read": 3,
  "write_backs": 1,
  "stale_notes": 0,
  "effective_hit": true,
  "false_positive": false,
  "stale_misguidance": false,
  "injected_notes": 3,
  "context_tokens": 1200,
  "write_back_accepted": true,
  "destructive_write_incident": false,
  "lock_contention_count": 2,
  "validation_failures": 1
}
```

Events are appended to `Projects/<Project>/.vault-meta/pilot/events.jsonl`. `metrics` writes and returns a summary with the PRD pilot thresholds:

- effective retrieval hit rate >= 60%
- stale misguidance <= 1 event
- average injected notes <= 5
- write-back provenance/acceptance = 100% when writes exist
- validation failures are summed from task events
- lock contention count is tracked from pilot events and real lock wait events
- destructive write incidents = 0

`pilot status` compares `plan.json` with recorded task events, reports `planned`, `recorded`, and `missing`, and includes the current metrics summary. It does not count event templates as completed pilot tasks.

## Release Gates

`release check` turns the release plan into machine-readable gates:

```powershell
python scripts/kb.py release check --project WeFlow --level engineering
python scripts/kb.py release check --project WeFlow --level environment
python scripts/kb.py release check --project WeFlow --level pilot
python scripts/kb.py release check --project WeFlow --level full
python scripts/kb.py release check --project WeFlow --level repo-wide
python scripts/kb.py release evidence record --project WeFlow --gate public_claims_gate --from-file public-claims.json
python scripts/kb.py release evidence public-claims-smoke --project WeFlow
python scripts/kb.py release evidence clean-install-smoke --project WeFlow
python scripts/kb.py release evidence user-journey-smoke --project WeFlow
python scripts/kb.py release evidence support-matrix-smoke --project WeFlow
python scripts/kb.py release diagnose --project WeFlow --level environment
python scripts/kb.py release smoke --project WeFlow --level environment
python scripts/kb.py release report --project WeFlow
```

Levels:

- `engineering`: repository-local implementation is releasable as a preview. It requires `doctor` readiness and no destructive ordinary tool surface. It does not require Obsidian CLI, Local REST, or a 10-task pilot. Add `--commit <sha>` to require tracked notes to match the current commit, and `--require-artifacts` to require repo-local and vault-local release artifacts.
- `environment`: current host environment is live-ready. It requires the engineering checks plus Obsidian CLI state `ready`, Local REST availability, and a recorded environment transport smoke.
- `pilot`: product validation is ready. It requires at least 10 pilot task events and all pilot metric thresholds passing.
- `full`: cumulative Project KB release gate. It requires `engineering`, `environment`, and `pilot` to all be ready. This is `project-kb-full`, not a repo-wide end-user product release gate.
- `repo-wide`: whole-repository end-user release gate. It requires `project-kb-full` plus public claims, clean install, user journey, and support matrix evidence artifacts.

Exit codes:

- `0` when the requested level returns `status: "ready"`.
- non-zero when the requested level returns `status: "blocked"`.

The MCP facade also exposes the same read-only check as `kb.release_check`.

`release report` is the cumulative release entrypoint for humans and automation. It runs the release gates, returns the highest cumulative Project KB version that is ready, lists blocked gates and individual blockers, and includes ordered `next_actions` plus verification commands. When repo-wide release evidence is missing, `next_actions` lists the four concrete smoke commands (`public-claims-smoke`, `clean-install-smoke`, `user-journey-smoke`, and `support-matrix-smoke`) before the final `release check --level repo-wide` verification. Its top-level `status` and exit code require both `project-kb-full` and `repo-wide` to be ready; `project_kb_status` separately reports the Project KB full gate.

For repo-wide end-user publication, run the explicit `repo-wide` gate. It looks for these evidence artifacts under `Projects/<Project>/.vault-meta/release/repo-wide/`:

- `public-claims.json`
- `clean-install.json`
- `user-journeys.json`
- `support-matrix.json`

Each artifact must be valid JSON with `"passed": true` after the corresponding evidence has been collected. Missing, invalid, or `"passed": false` artifacts keep the repo-wide gate blocked.

Use `release evidence record` to write these artifacts instead of editing `.vault-meta` files by hand:

```powershell
python scripts/kb.py release evidence record --project WeFlow --gate public_claims_gate --from-file public-claims.json
python scripts/kb.py release evidence record --project WeFlow --gate clean_install_gate --from-file clean-install.json
python scripts/kb.py release evidence record --project WeFlow --gate user_journey_gate --from-file user-journeys.json
python scripts/kb.py release evidence record --project WeFlow --gate support_matrix_gate --from-file support-matrix.json
```

Allowed gates:

- `public_claims_gate`
- `clean_install_gate`
- `user_journey_gate`
- `support_matrix_gate`

If an evidence file sets `"passed": true`, it must include at least one observable evidence field such as `commands`, `reviewed_files`, `journeys`, `matrix`, `notes`, `artifacts`, or `screenshots`.

`release evidence public-claims-smoke` scans `README.md`, `README.en.md`, `docs/project-kb/cli.md`, and `docs/project-kb/release-plan-cn.md`, then records `public_claims_gate` evidence. It requires the README files to declare the current release status, distinguish `Project KB preview` from `project-kb-full` / `repo-wide` release, and state live limitations for Obsidian CLI, Local REST, and host registration. It does not prove the claims are live; it proves the public claims are scoped to the current evidence.

`release evidence clean-install-smoke` is a safe dry-run for the clean install gate. It copies `vault-template` into a temporary vault, verifies the public template artifacts such as `AGENTS.md`, `AI_CONFIG.md`, `wiki/`, `raw/`, `assets/`, and the bundled `.opencode/skill/*/SKILL.md` entries, checks that the documented install `cd` paths in README/GUIDE/deployment docs exist, verifies root `setup.sh` and `setup.ps1`, then records `clean_install_gate` evidence. It does not install Node.js, OpenCode, OpenCLI, or modify a live Obsidian configuration.

`release evidence user-journey-smoke` verifies that README and the vault template define the four public user journeys: ingest, query, lint, and social ingest. It checks `vault-template/AGENTS.md`, `AI_CONFIG.md`, `wiki/使用指南.md`, and `README.md`, verifies that the template already includes baseline journey artifacts such as `raw/social` and `wiki/log.md`, then copies `vault-template` into a temporary vault and creates minimal file artifacts for raw ingest, wiki output, social ingest, and lint logging before recording `user_journey_gate` evidence. It does not run a live LLM, browser, or OpenCLI scraping session.

`release evidence support-matrix-smoke` records the repo-wide support matrix evidence. It verifies repo-local adapter and host-config artifacts for Codex, Claude Code, OpenClaw, and OpenCode, checks filesystem/Obsidian CLI/Local REST transport status, and verifies generated Markdown, Canvas, and Base artifacts. It marks live transports as `blocked` unless they are actually reachable, and it does not claim live host registration or live Obsidian rendering.

`release diagnose --level environment` is a read-only diagnostic command for v0.2 blockers. It returns:

- `target_version`: `v0.2-beta`
- `summary`: concise blocked/ready explanation
- `blocked_checks`: normalized `state`, `expected`, `observed`, and `path`/`url` fields
- `remediation`: user actions plus `verify_command`
- `verification_commands`: the exact smoke/check commands to rerun

For `local_rest_ready`, `release diagnose` also includes a read-only `plugin` object derived from the current Obsidian app config and open vault. It reports:

- `open_vault`
- `.obsidian/community-plugins.json`
- `.obsidian/plugins`
- whether `obsidian-local-rest-api` is installed
- whether `obsidian-local-rest-api` is enabled
- installed and enabled plugin ids

It exits with `0` even when the environment is blocked because the command itself is diagnostic.

`release smoke --level environment` is an explicit CLI maintenance command. It writes `Projects/<Project>/.vault-meta/release/environment-smoke.json` and a probe note at `Projects/<Project>/.vault-meta/release/environment-smoke-probe.md` after attempting:

- Obsidian CLI read.
- Obsidian CLI search.
- Obsidian Local REST append to the probe note.
- Filesystem readback of a generated nonce from the probe note.

This command is intentionally not exposed as an ordinary MCP tool because it writes smoke evidence and appends a log entry.

## BM25 Retrieval

`index` builds a local chunk index under the project metadata directory:

- `Projects/<Project>/.vault-meta/bm25/index.json`
- `Projects/<Project>/.vault-meta/bm25/index.md`
- `Projects/<Project>/.vault-meta/chunks/index.json`

The index stores heading-based chunks, term frequencies, document frequencies, average chunk length, and contextual prefixes such as `Architecture > Boundaries`.

`retrieve` uses that persisted BM25 index when available, builds it on demand when missing, and returns bounded chunk hits rather than whole-vault context:

- `path`
- `title`
- `type`
- `heading`
- `chunk_id`
- `contextual_prefix`
- `score`
- `snippet`
- `content`

The implementation is local and dependency-free. It does not use vector storage or model-based reranking.

## Validation

`validate` checks:

- Required frontmatter for project, hot, context, architecture, glossary, pitfall, decision, module, task, log, and source notes.
- Required PRD sections for project, module, decision, and task notes.
- Note `type` must match the Project KB path family, such as `modules/` -> `module` and `logs/` -> `log`.
- Supported `type` and `status` values.
- Supported `schema_version`.
- Project repo path existence.
- Source path existence where a repo can be resolved. Missing source paths are validation errors.
- Internal wikilink resolution.
- Monthly log filename format.
- Obvious secret-like strings.
- High-risk generated-noise markers such as `node_modules/`, `.vite/`, `__pycache__/`, `dist/`, and `build/`. These are validation errors.

Validation exits with code `1` when errors are found and still prints machine-readable JSON.

## Doctor And Transport

`doctor` proves the local Project KB surface is usable before agent integration:

- `validate`: project structure has no validation errors.
- `read_note`: `hot.md` can be read.
- `search_note`: bounded search returns at least one note.
- `safe_surface`: ordinary tools do not include delete, overwrite, or bulk rewrite names.
- `transport`: filesystem, bundled CLI, and bundled Project KB MCP facade evidence are present.
  - A ready result means the filesystem transport plus Project KB CLI/MCP facade are available. Obsidian CLI and Local REST remain optional runtime transports.

`transport detect` writes `Projects/<Project>/.vault-meta/transport.json` with runtime evidence:

- `preferred`: first available transport in the PRD priority order `cli -> mcp_obsidian -> filesystem`.
- Stable `fallback_chain`: `cli`, `mcp_obsidian`, `filesystem`.
- `available.cli`: Obsidian CLI executable discovery (`obsidian` on PATH) when present.
- `available.mcp_obsidian`: optional Obsidian Local REST API probe, default `https://127.0.0.1:27124/`.
- `available.filesystem`: project root readability/writability.
- `evidence.obsidian_cli`: optional `obsidian` executable discovery.
- `evidence.project_kb_cli`: bundled `scripts/kb.py`.
- `evidence.obsidian_local_rest_api`: raw Local REST probe evidence.
- `evidence.project_kb_mcp`: bundled `scripts/kb_mcp.py`.

Set `PROJECT_KB_OBSIDIAN_REST_URL` to probe a different Obsidian Local REST API endpoint and `PROJECT_KB_OBSIDIAN_REST_API_KEY` for authenticated requests. The official plugin's loopback-only self-signed HTTPS endpoint is supported; set `PROJECT_KB_OBSIDIAN_REST_CA_CERT` when a specific CA certificate should be trusted instead. Certificate verification is never disabled for non-loopback hosts. REST/Obsidian transports are optional; filesystem + Project KB CLI/MCP are the verified default path when Obsidian CLI is not installed or is installed but disabled in Obsidian settings.

Set `PROJECT_KB_OBSIDIAN_CLI_PATH` to an explicit Obsidian CLI executable when auto-discovery is unsuitable. If the variable is present but does not point to a file, CLI transport is treated as unavailable; this also provides deterministic isolation for tests and CI.

When a project's root note frontmatter sets `transport: cli` and the local `obsidian` executable is available, `read` and `search` now prefer the Obsidian CLI and fall back to filesystem behavior if the CLI is unavailable or the command fails. For `append-log`, existing monthly log notes prefer `obsidian append`, while first-time monthly log creation prefers `obsidian create`; both still fall back to the filesystem-backed path if the CLI is unavailable or the command fails. Structured frontmatter updates such as `update-project-status` and `update-frontmatter-field` likewise prefer `obsidian property:set` before falling back to direct file writes. `create-decision` now also prefers `obsidian create` before falling back to filesystem note creation.

When a project's root note frontmatter sets `transport: mcp_obsidian` and the configured Local REST endpoint is reachable, `read`, `search`, structured frontmatter updates, monthly log creation/appends, and ADR note creation now enter the Obsidian Local REST transport layer before falling back to filesystem behavior. The current repository still treats live endpoint reachability and auth as environment-dependent and keeps filesystem fallback as the verified default.

`transport detect` distinguishes three Obsidian CLI states:

- executable not found
- executable found but command line interface not enabled
- executable found and `obsidian --help` succeeds

These states are surfaced as `available.cli.state` values:

- `missing`
- `disabled`
- `ready`

## Safety Boundary

The CLI intentionally does not expose note delete, full overwrite, batch move, batch rename, or vault-wide rewrite commands. Project agents should use `search`, `read`, `stale`, and verified `append-log` by default.

Structured writes are limited:

- `create-decision` requires at least one `--source-path` or `--verification-command`.
- `update-project-status` only accepts `active`, `paused`, or `archived`.
- `update-frontmatter-field` only updates an allowlist: `status`, `confidence`, `verified_commit`, `last_verified_commit`, `last_verified_at`, `transport`, and `tags`.

`install-repo-adapters` writes only inside the target repo's `.project-kb/` directory:

- `.project-kb/project.json`
- `.project-kb/adapters/codex/AGENTS.project-kb.md`
- `.project-kb/adapters/claude/CLAUDE.project-kb.md`
- `.project-kb/adapters/openclaw/OPENCLAW.project-kb.md`
- `.project-kb/adapters/opencode/OPENCODE.project-kb.md`
- `.project-kb/adapters/generic/GENERIC.project-kb.md`
- `.project-kb/host-configs/codex.config.toml`
- `.project-kb/host-configs/claude.mcp.json`
- `.project-kb/host-configs/openclaw.mcp.json5`
- `.project-kb/host-configs/opencode.md`
- `.project-kb/host-configs/README.md`

The host config files are repo-local drafts. They do not auto-install anything into Codex, Claude Code, OpenClaw, or a global user profile.

`export-host-configs` writes auditable host-registration aids inside the vault project:

- `Projects/<Project>/.vault-meta/host-configs/mcp-server.json`
- `Projects/<Project>/.vault-meta/host-configs/codex.md`
- `Projects/<Project>/.vault-meta/host-configs/claude.md`
- `Projects/<Project>/.vault-meta/host-configs/openclaw.md`
- `Projects/<Project>/.vault-meta/host-configs/opencode.md`
- `Projects/<Project>/.vault-meta/host-configs/generic.md`

The shared `mcp-server.json` includes both `PROJECT_KB_VAULT` and `PROJECT_KB_PROJECT` in its `env` block.

These files do not modify Codex, Claude Code, OpenClaw, or any other host automatically. Verify the current host documentation before copying a snippet into a real host config.

`export-views` writes Obsidian-facing project views inside the vault project:

- `Projects/<Project>/views/project-map.canvas`
- `Projects/<Project>/views/project-notes.base`

The canvas follows JSON Canvas by writing `nodes` and `edges` with file nodes for the project index, hot cache, architecture, pitfalls, modules, decisions, and sources. The base file is YAML that filters Markdown notes under `Projects/<Project>` and provides table/card views over frontmatter fields such as `type`, `status`, `confidence`, and `verified_commit`.

## MCP Facade

`scripts/kb_mcp.py` exposes the safe Project KB tools over stdio JSON-RPC for MCP-compatible hosts:

- `kb.project_find`
- `kb.search`
- `kb.retrieve`
- `kb.read`
- `kb.append_log`
- `kb.check_staleness`
- `kb.project_create`
- `kb.create_decision`
- `kb.update_project_status`
- `kb.update_frontmatter_field`

It intentionally does not expose delete, full overwrite, batch move, batch rename, or vault-wide rewrite tools.

`kb.append_log` uses the same provenance contract as the CLI. Its schema exposes `commit`, `commands`, `files`, `source_paths`, `url`, `urls`, and `repo`; at least one must be non-empty.

`kb.create_decision` also exposes its provenance contract in schema: provide either `source_paths` or `verification_command`.

Use `kb.retrieve` when a host should receive bounded BM25-ranked chunks with contextual prefixes. Use `kb.read` when the agent already knows the exact Markdown note path or section it needs. `kb.read` intentionally refuses `.vault-meta` internals, host config drafts, audit files, indexes, and non-Markdown artifacts, and it returns an error when a requested section does not exist.

Example MCP server command:

```powershell
python scripts/kb_mcp.py
```

Set `PROJECT_KB_VAULT` in the host environment, or pass `"vault": "<path>"` inside tool arguments for local testing.
