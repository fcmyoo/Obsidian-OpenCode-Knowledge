# Project KB Completion Audit

Date: 2026-06-23

This audit maps `docs/project-kb-cross-agent-prd-cn.md` to the current implementation.

## Implemented And Verified

- Vault schema and templates: `init-project` creates `_index.md`, `hot.md`, `context.md`, `architecture.md`, `glossary.md`, `pitfalls.md`, ADR/module/task/source examples, `.manifest.json`, PRD-shaped seed transport metadata with the same object structure and evidence block used by runtime `transport detect`, lock directories, BM25/chunk directories, and PRD-aligned project defaults such as `agent_scope: [codex, claude, openclaw]` and `transport: auto`.
- CLI P0: `init-project`, `validate`, `status`, `transport detect`, `project-find`, `search`, `read`, `append-log`, `stale`.
- CLI status: `status` now returns the project status, `_index.md` path, repo path, hot note path, transport mode, note counts, and validation totals as a compact project overview.
- Project resolution: `project-find` now resolves both the repo root and repo-internal subdirectories back to the owning Project KB entry, and the CLI can discover the vault from repo-local `.project-kb/project.json` when `--vault` and `PROJECT_KB_VAULT` are not supplied.
- CLI P1: `index`, `retrieve`, `lock list`, `export-adapter`, `create-decision`, `update-project-status`, `update-frontmatter-field`.
- Lock visibility: `lock list` now surfaces `created_at` / `target` metadata from active lock files instead of only path + stale.
- MCP Facade: stdio JSON-RPC server with `kb.project_find`, `kb.search`, `kb.retrieve`, `kb.read`, `kb.append_log`, `kb.check_staleness`, `kb.project_create`, `kb.create_decision`, `kb.update_project_status`, and `kb.update_frontmatter_field`; `kb.append_log` and `kb.create_decision` advertise the same provenance schema alternatives enforced by the core write path.
- Write safety: append-only logs and structured writes use project-relative per-file locks and audit JSONL; append logs require and persist at least one provenance field; new monthly logs include `type: log` frontmatter; append-log, create-decision, and update-frontmatter-field validate target notes before writing/auditing, including repo/source-path and broken-wikilink checks where applicable; ADR creation now serializes numbering with a project-level sequence lock; lock handling covers stale lock reclamation and safe release; structured writes are field-limited; ADR creation requires source path or verification command; secret-like payloads are refused.
- Validation: required frontmatter across core Project KB note types, including PRD-required project `agent_scope`/`transport`/`last_verified_*` fields and module/decision `verified_commit`; required PRD sections for project/module/decision/task notes; note type/path-family consistency; valid type/status; supported schema version; repo path; source paths as error-level checks; internal wikilinks; monthly log filenames; secret-like content; and generated-noise markers as error-level checks.
- Staleness checks: `stale` now covers project, context, architecture, glossary, pitfall, decision, module, task, and source notes by looking at `verified_commit` or `last_verified_commit`.
- Agent adapters: repo-root Codex/OpenCode skills, repo-root Claude `project-kb` skill/`wiki` command, OpenClaw, OpenCode, and generic adapter documentation/export templates, with explicit access disclosure for network use, vault-external files, remote LLM APIs, telemetry, and paid services. The repo-local entrypoints now line up as `AGENTS.md` + `.codex/config.toml` + `.codex/skills/project-kb/SKILL.md` for Codex, `CLAUDE.md` + `.claude/...` for Claude Code, and `.opencode/skill/project-kb/SKILL.md` for OpenCode.
- Repo integration export: `install-repo-adapters` writes `.project-kb/project.json`, per-agent adapter guidance including `opencode`, and repo-local host config drafts including `host-configs/opencode.md` plus the updated README inventory into a target repository.
- Host config export: `export-host-configs` writes a shared MCP server manifest with `PROJECT_KB_VAULT` and `PROJECT_KB_PROJECT`, plus Codex, Claude, OpenClaw, OpenCode, and generic registration snippets under `.vault-meta/host-configs/`.
- Obsidian views export: `export-views` writes `views/project-map.canvas` and `views/project-notes.base` for local visual/table navigation of the project KB, including task notes in the Canvas project map.
- Pilot metrics plumbing: `pilot plan` writes a 10-task pilot plan to `.vault-meta/pilot/plan.json`; `pilot record` appends per-task metrics to `.vault-meta/pilot/events.jsonl` only after validating that task events match the frozen plan, include all required template fields, and use non-negative integer counters; `lock_file` records real lock-contention events; `metrics` aggregates task-level ratios from `event_type == "task"` records while separately summing validation failures, lock contention counters, and destructive write incidents, and now exposes threshold entries for those runtime counters as well.
- Release gates: `release check --level engineering|environment|pilot|full|repo-wide` exposes the Project KB release-plan split plus the repo-wide end-user publication gate as machine-readable checks. `engineering` covers repository-local doctor/safe-surface readiness, can optionally enforce stale-note commit parity with `--commit`, and can require repo/vault release artifacts with `--require-artifacts`; `environment` covers Obsidian CLI and Local REST live availability plus a recorded `release smoke --level environment`; `pilot` covers the 10-task metric thresholds; `full` is `project-kb-full`, requiring engineering, environment, and pilot to all be ready; `repo-wide` additionally requires public claims, clean install, user journey, and support matrix evidence artifacts. `release evidence record` writes those repo-wide evidence artifacts with basic empty-passed-evidence protection, `release evidence public-claims-smoke` verifies README/CLI/release-plan scope limitations before recording public-claims evidence, `release evidence clean-install-smoke` safely copies `vault-template` into a temporary vault and verifies documented install paths plus root setup scripts before recording clean-install evidence, `release evidence user-journey-smoke` verifies README/template coverage for ingest, query, lint, and social ingest, requires baseline template artifacts such as `raw/social` and `wiki/log.md`, and creates minimal temporary-vault file artifacts before recording user-journey evidence, and `release evidence support-matrix-smoke` records repo-local host/OS/transport/Obsidian-surface support matrix evidence while preserving live transport blockers. `release report` now aggregates those gates into a cumulative Project KB publish report and a separate repo-wide status with blockers, concrete repo-wide smoke next actions, verification commands, and a top-level status that remains blocked until both `project-kb-full` and `repo-wide` are ready. The MCP facade exposes the read-only Project KB gate check as `kb.release_check`.
- P1 retrieval: `index` writes heading-based chunks plus a dependency-free BM25 index with term/document frequencies and average chunk length; `retrieve` returns bounded contextual chunk hits instead of injecting whole notes.
- Bounded search and retrieval: `search` and `retrieve` now enforce the PRD `top 5` limit in the core implementation, and the MCP `kb.search` / `kb.retrieve` schemas cap `limit` at 5.
- Environment proof: `doctor` verifies validation, read, search, safe tool surface, and required local transports; `transport detect` now exposes PRD-shaped transport metadata with `cli -> mcp_obsidian -> filesystem` fallback ordering, where `available.cli` means Obsidian CLI discovery and the bundled Project KB CLI stays in the evidence block as `project_kb_cli`. `release diagnose --level environment` now adds read-only Obsidian app/vault plugin diagnostics for `obsidian-local-rest-api`, including the current open vault, `.obsidian/community-plugins.json`, installed plugin ids, enabled plugin ids, and installed/enabled booleans.
- MCP audit provenance: MCP write calls now record audit entries with `actor: "mcp"` and `source: "mcp"` instead of being misattributed to the CLI source.
- Read safety: CLI and MCP `read` only return Project KB Markdown notes under `Projects/<Project>` and refuse `.vault-meta` internals, host config drafts, indexes, audit files, and non-Markdown artifacts.
- Obsidian transport execution layers:
  - `transport: cli` now covers `read`, `search`, existing/new monthly `append-log`, `update-project-status`, `update-frontmatter-field`, and `create-decision`, all with filesystem fallback when the Obsidian CLI is unavailable or fails.
  - `transport: mcp_obsidian` now covers `read`, `search`, frontmatter patch operations, existing/new monthly `append-log`, and `create-decision`, with concrete HTTP request shapes and filesystem fallback when Local REST is unavailable or fails.

Verification command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_project_kb -v
```

Current result: 119 tests, 0 failures.

Local end-to-end smoke verification was also run against a temporary vault and repo:

```powershell
python scripts\kb.py --vault <temp-vault> init-project --name Demo --repo <temp-repo>
python scripts\kb.py --vault <temp-vault> validate --project Demo
python scripts\kb.py --vault <temp-vault> index --project Demo
python scripts\kb.py --vault <temp-vault> retrieve --project Demo --query "architecture verification" --limit 3
python scripts\kb.py --vault <temp-vault> append-log --project Demo --from-file <payload.json>
python scripts\kb.py --vault <temp-vault> export-host-configs --project Demo
python scripts\kb.py --vault <temp-vault> export-views --project Demo
python scripts\kb.py --vault <temp-vault> doctor --project Demo
python scripts\kb.py --vault <temp-vault> release check --project Demo --level engineering
python scripts\kb.py --vault <temp-vault> release check --project Demo --level engineering --require-artifacts
python scripts\kb.py --vault <temp-vault> release diagnose --project Demo --level environment
python scripts\kb.py --vault <temp-vault> release smoke --project Demo --level environment
python scripts\kb.py --vault <temp-vault> release report --project Demo
python scripts\kb.py --vault <temp-vault> release check --project Demo --level full
```

Current result: `doctor`, the strict engineering artifact gate, and the environment gate all return `status: "ready"`. Obsidian CLI read/search and authenticated Local REST append/file-read verification passed against `tmp-live-vault`; `release report` now reports `highest_ready_version: "v0.2-beta"`. Public-claims, clean-install, user-journey, and support-matrix evidence artifacts are present, and the refreshed support matrix marks Obsidian CLI and Local REST as `live verified` on the current Windows host. The cumulative `project-kb-full` and repo-wide release remain blocked only because the frozen 10-task pilot has `recorded: 0`; real Claude Code, OpenCode, and OpenClaw pilot tasks must not be replaced with synthetic events.

## Not Yet Proven Complete

- Real Claude Code/OpenCode/OpenClaw host registration was not exercised against those applications; generated host snippets and repo-local drafts are registration aids only.
- Obsidian CLI read/search and Local REST authenticated write/readback are live-verified on the current Windows host.
- The 10-real-task pilot plan exists, but the pilot itself has not been run with real project work. The metrics pipeline exists and is tested with synthetic events, but real hit-rate and stale-note quality claims require live pilot data.
- `release check --level environment` is ready on the current Windows host.
- `release check --level pilot` remains blocked until at least 10 real task events are recorded and all pilot thresholds pass.
- `release check --level repo-wide` remains blocked until Project KB full passes. The clean-install smoke is dry-run template evidence, not full live installer evidence; the user-journey smoke is template coverage evidence, not live LLM/browser execution evidence; the support-matrix smoke is repo-local matrix evidence, not live host registration or live Obsidian rendering evidence.
- Model-based reranking and vector retrieval are not implemented.
- Canvas/Base views are generated and structurally tested, but visual rendering inside a live Obsidian app was not exercised.

## Current Completion Position

The repository now has a working, verified P0 plus several P1 structured-write, repo integration, maintenance, environment-proof, and pilot-metrics capabilities. The full PRD goal remains active until live agent integration and real pilot evidence are produced or intentionally scoped out by the project owner.

## Requirement Audit

### Proven In-Repo

- Shared project KB core exists as a reusable package: `project_kb/__init__.py` exports `ProjectKb`, and the core behavior is exercised through the CLI/MCP regression suite.
- CLI maintenance surface required by the PRD exists in `scripts/kb.py`: project init, validation, status, transport detect, bounded search/read, append-log, stale checks, BM25 index/retrieve, lock listing, adapter export, repo adapter install, host-config export, view export, pilot record, and metrics.
- MCP facade exists in `scripts/kb_mcp.py` and exposes only the safe project-level tools required by the PRD, with no raw delete/overwrite/bulk rewrite surface.
- Repo-local adapter entrypoints now exist for the named hosts:
  - Codex: `AGENTS.md`, `.codex/config.toml`, `.codex/skills/project-kb/SKILL.md`
  - Claude Code: `CLAUDE.md`, `.claude/skills/project-kb/SKILL.md`, `.claude/commands/wiki.md`
  - OpenCode: `.opencode/skill/project-kb/SKILL.md`
- Repo-local adapter/export drafts exist for downstream target repos through `install-repo-adapters`, including Codex, Claude, OpenClaw, OpenCode, and generic files under `.project-kb/`.
- Host registration drafts exist through `export-host-configs`, but only as auditable artifacts under `.vault-meta/host-configs/`.
- Obsidian-facing canvas/base exports exist through `export-views`.
- Validation, staleness, lock safety, provenance enforcement, structured write bounds, retrieval limits, and CLI/REST preference-vs-fallback behavior are all covered by automated regression tests.

### Fresh Evidence

- Automated verification command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_project_kb -v
```

- Latest observed result on 2026-06-24: `Ran 119 tests`, `OK`.

- Live Codex project-scoped MCP proof:

```powershell
codex mcp list
codex mcp get project-kb
codex exec --json -c "mcp_servers.project-kb.env.PROJECT_KB_VAULT='H:\code\github\Obsidian-OpenCode-Knowledge\tmp-live-vault'" "Use the available project-kb MCP tool if it is present. Resolve project DemoLive, read its hot note, and return the project path, hot note path, and one-sentence summary of the hot note. Do not modify any files."
```

- Latest observed Codex runtime behavior:
  - Inside `H:\code\github\Obsidian-OpenCode-Knowledge`, `codex mcp list` showed `project-kb` as an enabled stdio MCP server and `codex mcp get project-kb` resolved `command: python`, `args: scripts/kb_mcp.py`, and `env: PROJECT_KB_VAULT=...`.
  - Outside the repository (`C:\Users\Administrator`), `project-kb` disappeared from `codex mcp list`, and `codex mcp get project-kb` returned `No MCP server named 'project-kb' found.` This proves the server is coming from the repo-local `.codex/config.toml` layer rather than only from global user config.
  - The non-interactive `codex exec --json ...` run emitted real `mcp_tool_call` items for `kb.project_find` and `kb.read` on the `project-kb` server, and returned:
    - project path: `Projects/DemoLive/_index.md`
    - hot note path: `Projects/DemoLive/hot.md`
    - summary: no active focus recorded; created by `kb init-project`; open question about write-back policy

- Live Obsidian environment evidence:

```powershell
Get-Process Obsidian -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Path
Invoke-WebRequest -UseBasicParsing 'https://127.0.0.1:27124/' -SkipCertificateCheck -TimeoutSec 3
& 'D:\soft\Obsidian\Obsidian.com' help
```

- Latest observed Obsidian runtime behavior:
  - Obsidian 1.12.7 is running with `tmp-live-vault` open.
  - The official `obsidian-local-rest-api` 4.1.3 plugin is installed and enabled from release assets whose SHA-256 digests match the official GitHub release.
  - The secure loopback endpoint `https://127.0.0.1:27124/` is reachable; authenticated Local REST append and file readback passed without persisting the API key in repository configuration.
  - `D:\soft\Obsidian\Obsidian.com help` succeeds, and CLI read/search passed against the actual vault name rather than incorrectly using the Project KB project name.
  - `release smoke --level environment`, `release check --level environment`, and `release diagnose --level environment` now report ready.

### Still Not Proven

- Real Codex host registration using this repository's `.codex/config.toml` is now proven for the Codex CLI runtime: the repo-local `project-kb` MCP server appears only inside this repository and was successfully used by a live `codex exec --json ...` run to call `kb.project_find` and `kb.read`.
- Real Codex desktop app registration using this repository's `.codex/config.toml` was not separately exercised; current proof is CLI runtime evidence.
- Real Claude Code host registration using this repository's `.claude/...` entrypoints was not exercised in a live Claude Code runtime.
- Real OpenClaw routing to the same Project KB MCP facade was not exercised.
- Live Obsidian Local REST read/write is verified; live rendering of generated Canvas/Base views is still not exercised.
- The PRD's 10-real-task pilot and its target hit-rate / stale-misguidance metrics are still unproven with real work.
- Because those items require external runtime evidence or human task usage, the full PRD cannot yet be marked complete from repository-local evidence alone.
