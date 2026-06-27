import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.parse
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "scripts" / "kb.py"
KB_MCP = ROOT / "scripts" / "kb_mcp.py"

from project_kb import ProjectKb  # noqa: E402
from project_kb.core import make_note  # noqa: E402


class ProjectKbCliTests(unittest.TestCase):
    def run_kb(self, workspace, *args, check=True):
        env = os.environ.copy()
        env["PROJECT_KB_VAULT"] = str(workspace / "vault")
        env["PROJECT_KB_OBSIDIAN_CLI_PATH"] = str(workspace / "missing-obsidian")
        env["PROJECT_KB_OBSIDIAN_REST_URL"] = "http://127.0.0.1:1/"
        env.pop("PROJECT_KB_OBSIDIAN_REST_API_KEY", None)
        result = subprocess.run(
            [sys.executable, str(KB), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        if check and result.returncode != 0:
            self.fail(
                f"command failed: {result.args}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result

    def parse_json(self, result):
        return json.loads(result.stdout)

    def test_init_project_creates_schema_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()

            result = self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            data = self.parse_json(result)

            project_root = workspace / "vault" / "Projects" / "Demo"
            self.assertEqual(data["project"], "Demo")
            self.assertTrue((project_root / "_index.md").exists())
            self.assertTrue((project_root / "hot.md").exists())
            self.assertTrue((project_root / "modules" / "example.md").exists())
            self.assertTrue((project_root / "decisions" / "ADR-0001-example.md").exists())
            self.assertTrue((project_root / "tasks" / "example-task.md").exists())
            self.assertTrue((project_root / ".manifest.json").exists())
            self.assertTrue((project_root / ".vault-meta" / "locks").is_dir())
            project_note = ProjectKb(workspace / "vault").read_note(project_root / "_index.md")
            self.assertEqual(project_note.frontmatter["agent_scope"], ["codex", "claude", "openclaw"])
            self.assertEqual(project_note.frontmatter["transport"], "auto")
            transport_meta = json.loads((project_root / ".vault-meta" / "transport.json").read_text(encoding="utf-8"))
            self.assertEqual(transport_meta["preferred"], "filesystem")
            self.assertEqual(transport_meta["fallback_chain"], ["cli", "mcp_obsidian", "filesystem"])
            self.assertEqual(set(transport_meta["available"].keys()), {"cli", "mcp_obsidian", "filesystem"})
            self.assertFalse(transport_meta["available"]["cli"]["available"])
            self.assertIn("path", transport_meta["available"]["cli"])
            self.assertIn("reason", transport_meta["available"]["cli"])
            self.assertIn("checked", transport_meta["available"]["mcp_obsidian"])
            self.assertIn("reason", transport_meta["available"]["mcp_obsidian"])
            self.assertIn("path", transport_meta["available"]["filesystem"])
            self.assertIn("evidence", transport_meta)
            self.assertIn("obsidian_cli", transport_meta["evidence"])
            self.assertIn("project_kb_cli", transport_meta["evidence"])
            self.assertIn("obsidian_local_rest_api", transport_meta["evidence"])
            self.assertIn("project_kb_mcp", transport_meta["evidence"])

    def test_project_find_resolves_windows_backslash_repo_paths_from_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            vault = workspace / "vault"
            project_root = vault / "Projects" / "WinDemo"
            project_root.mkdir(parents=True)
            repo = workspace / "repo"
            nested = repo / "src" / "pkg"
            nested.mkdir(parents=True)
            windows_repo = str(repo.resolve()).replace("/", "\\")
            (project_root / "_index.md").write_text(
                f"""---
schema_version: 1
type: project
project: WinDemo
repo: "{windows_repo}"
status: active
---
# WinDemo
""",
                encoding="utf-8",
            )

            result = ProjectKb(vault).project_find(repo_path=str(nested))

            self.assertEqual(result["project"], "WinDemo")
            self.assertEqual(Path(result["repo"]).resolve(), repo.resolve())

    def test_cli_discovers_vault_from_repo_local_project_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "pilot", "plan", "--project", "Demo")
            self.run_kb(workspace, "install-repo-adapters", "--project", "Demo", "--repo", str(repo))

            env = os.environ.copy()
            env.pop("PROJECT_KB_VAULT", None)
            result = subprocess.run(
                [sys.executable, str(KB), "project-find", "--repo", str(repo)],
                cwd=repo,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["project"], "Demo")
            self.assertEqual(Path(payload["repo"]).resolve(), repo.resolve())

    def test_validate_reports_missing_required_frontmatter_and_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            (project_root / "modules" / "bad.md").write_text(
                """---
type: module
project: Demo
---
# Bad

OPENAI_API_KEY=sk-proj-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
""",
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "validate", "--project", "Demo", check=False)
            data = self.parse_json(result)

            self.assertEqual(result.returncode, 1)
            messages = "\n".join(item["message"] for item in data["errors"])
            self.assertIn("missing required frontmatter field: module", messages)
            self.assertIn("secret-like content", messages)

    def test_validate_reports_missing_source_paths_as_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            (project_root / "modules" / "missing-source.md").write_text(
                """---
schema_version: 1
type: module
project: Demo
module: MissingSource
source_paths:
  - src/missing.ts
verified_commit:
confidence: medium
tags:
  - module
---
# MissingSource

## Responsibility

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
""",
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "validate", "--project", "Demo", check=False)
            data = self.parse_json(result)
            error_messages = "\n".join(f"{item['path']}: {item['message']}" for item in data["errors"])
            warning_messages = "\n".join(f"{item['path']}: {item['message']}" for item in data["warnings"])

            self.assertEqual(result.returncode, 1)
            self.assertIn("Projects/Demo/modules/missing-source.md: source path does not exist: src/missing.ts", error_messages)
            self.assertNotIn("source path does not exist: src/missing.ts", warning_messages)

    def test_validate_reports_missing_required_frontmatter_for_core_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            (project_root / "hot.md").write_text(
                """---
schema_version: 1
type: hot
---
# Bad Hot
""",
                encoding="utf-8",
            )
            (project_root / "context.md").write_text(
                """---
schema_version: 1
type: context
project: Demo
tags:
  - context
---
# Bad Context
""",
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "validate", "--project", "Demo", check=False)
            data = self.parse_json(result)
            messages = "\n".join(f"{item['path']}: {item['message']}" for item in data["errors"])

            self.assertEqual(result.returncode, 1)
            self.assertIn("Projects/Demo/hot.md: missing required frontmatter field: project", messages)
            self.assertIn("Projects/Demo/hot.md: missing required frontmatter field: tags", messages)
            self.assertIn("Projects/Demo/context.md: missing required frontmatter field: source_paths", messages)
            self.assertIn("Projects/Demo/context.md: missing required frontmatter field: confidence", messages)

    def test_validate_reports_missing_required_frontmatter_for_project_module_and_decision_prd_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            (project_root / "_index.md").write_text(
                f"""---
schema_version: 1
type: project
project: Demo
repo: {repo}
status: active
source_of_truth: repo
tags:
  - project
---
# Demo

## Purpose

## Current State

## Important Modules

## Active Decisions

## Known Pitfalls

## Verification Commands

## Links
""",
                encoding="utf-8",
            )
            (project_root / "modules" / "example.md").write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Example
source_paths: []
confidence: medium
tags:
  - module
---
# Example

## Responsibility

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
""",
                encoding="utf-8",
            )
            (project_root / "decisions" / "ADR-0001-example.md").write_text(
                """---
schema_version: 1
type: decision
project: Demo
status: proposed
date: 2026-06-23
source_paths: []
confidence: medium
tags:
  - adr
---
# ADR-0001: Example

## Context

## Decision

## Consequences

## Alternatives Considered

## Verification
""",
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "validate", "--project", "Demo", check=False)
            data = self.parse_json(result)
            messages = "\n".join(f"{item['path']}: {item['message']}" for item in data["errors"])

            self.assertEqual(result.returncode, 1)
            self.assertIn("Projects/Demo/_index.md: missing required frontmatter field: agent_scope", messages)
            self.assertIn("Projects/Demo/_index.md: missing required frontmatter field: last_verified_commit", messages)
            self.assertIn("Projects/Demo/_index.md: missing required frontmatter field: last_verified_at", messages)
            self.assertIn("Projects/Demo/_index.md: missing required frontmatter field: transport", messages)
            self.assertIn("Projects/Demo/modules/example.md: missing required frontmatter field: verified_commit", messages)
            self.assertIn("Projects/Demo/decisions/ADR-0001-example.md: missing required frontmatter field: verified_commit", messages)

    def test_validate_reports_missing_required_sections_for_project_module_and_decision_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            index = project_root / "_index.md"
            index.write_text(
                """---
schema_version: 1
type: project
project: Demo
repo: {}
status: active
source_of_truth: repo
tags:
  - project
---
# Demo

## Purpose
""".format(str(repo)),
                encoding="utf-8",
            )
            module = project_root / "modules" / "example.md"
            module.write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Example
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Example

## Responsibility
""",
                encoding="utf-8",
            )
            decision = project_root / "decisions" / "ADR-0001-example.md"
            decision.write_text(
                """---
schema_version: 1
type: decision
project: Demo
status: proposed
date: 2026-06-23
source_paths: []
verified_commit:
confidence: medium
tags:
  - adr
---
# ADR-0001: Example

## Context
""",
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "validate", "--project", "Demo", check=False)
            data = self.parse_json(result)
            messages = "\n".join(f"{item['path']}: {item['message']}" for item in data["errors"])

            self.assertEqual(result.returncode, 1)
            self.assertIn("Projects/Demo/_index.md: missing required section: Current State", messages)
            self.assertIn("Projects/Demo/modules/example.md: missing required section: Data Flow", messages)
            self.assertIn(
                "Projects/Demo/decisions/ADR-0001-example.md: missing required section: Consequences",
                messages,
            )

    def test_validate_reports_missing_required_task_frontmatter_and_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            task = project_root / "tasks" / "bad-task.md"
            task.write_text(
                """---
schema_version: 1
type: task
project: Demo
---
# Bad Task

## Status
""",
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "validate", "--project", "Demo", check=False)
            data = self.parse_json(result)
            messages = "\n".join(f"{item['path']}: {item['message']}" for item in data["errors"])

            self.assertEqual(result.returncode, 1)
            self.assertIn("Projects/Demo/tasks/bad-task.md: missing required frontmatter field: task_id", messages)
            self.assertIn("Projects/Demo/tasks/bad-task.md: missing required frontmatter field: source_paths", messages)
            self.assertIn("Projects/Demo/tasks/bad-task.md: missing required section: Commands", messages)
            self.assertIn("Projects/Demo/tasks/bad-task.md: missing required section: Result", messages)

    def test_search_read_and_project_find_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            for idx in range(6):
                module = project_root / "modules" / f"retrieval-{idx}.md"
                module.write_text(
                    f"""---
schema_version: 1
type: module
project: Demo
module: Retrieval{idx}
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Retrieval {idx}

## Responsibility

Searches project notes with a bounded result limit.

## Known Pitfalls

Do not inject every note into context.
""",
                    encoding="utf-8",
                )

            found = self.parse_json(self.run_kb(workspace, "project-find", "--repo", str(repo)))
            self.assertEqual(found["project"], "Demo")
            self.assertEqual(found["hot"], "Projects/Demo/hot.md")

            repo_subdir = repo / "src"
            repo_subdir.mkdir()
            found_from_subdir = self.parse_json(self.run_kb(workspace, "project-find", "--repo", str(repo_subdir)))
            self.assertEqual(found_from_subdir["project"], "Demo")

            search = self.parse_json(
                self.run_kb(
                    workspace,
                    "search",
                    "--project",
                    "Demo",
                    "--query",
                    "bounded context",
                    "--limit",
                    "10",
                )
            )
            self.assertEqual(len(search["results"]), 5)
            self.assertTrue(all(result["path"].startswith("Projects/Demo/modules/retrieval-") for result in search["results"]))

            read = self.parse_json(
                self.run_kb(
                    workspace,
                    "read",
                    "--path",
                    search["results"][0]["path"],
                    "--section",
                    "Known Pitfalls",
                )
            )
            self.assertIn("Do not inject every note", read["content"])
            self.assertNotIn("Responsibility", read["content"])

            missing_section = self.run_kb(
                workspace,
                "read",
                "--path",
                search["results"][0]["path"],
                "--section",
                "Does Not Exist",
                check=False,
            )
            self.assertNotEqual(missing_section.returncode, 0)
            self.assertIn("section not found: Does Not Exist", missing_section.stderr)

    def test_read_refuses_internal_metadata_and_non_markdown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "transport", "detect", "--project", "Demo")
            self.run_kb(workspace, "export-host-configs", "--project", "Demo")

            metadata_read = self.run_kb(
                workspace,
                "read",
                "--path",
                "Projects/Demo/.vault-meta/transport.json",
                check=False,
            )
            self.assertNotEqual(metadata_read.returncode, 0)
            self.assertIn("read only supports Project KB Markdown notes", metadata_read.stderr)

            view_read = self.run_kb(
                workspace,
                "read",
                "--path",
                "Projects/Demo/.vault-meta/host-configs/codex.md",
                check=False,
            )
            self.assertNotEqual(view_read.returncode, 0)
            self.assertIn("read only supports Project KB Markdown notes", view_read.stderr)

    def test_mcp_read_refuses_internal_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "transport", "detect", "--project", "Demo")

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.read",
                        "arguments": {
                            "vault": str(vault),
                            "path": "Projects/Demo/.vault-meta/transport.json",
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            response = json.loads(proc.stdout)
            self.assertIn("error", response)
            self.assertIn("read only supports Project KB Markdown notes", response["error"]["message"])

    def test_append_log_writes_audit_and_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            summary = workspace / "summary.md"
            summary.write_text(
                json.dumps(
                    {
                        "title": "Build P0 CLI",
                        "summary": "Implemented filesystem-backed Project KB commands.",
                        "files": ["scripts/kb.py"],
                        "commands": ["python -m unittest"],
                        "result": "passed",
                        "commit": "abc123",
                    }
                ),
                encoding="utf-8",
            )

            appended = self.parse_json(
                self.run_kb(workspace, "append-log", "--project", "Demo", "--from-file", str(summary))
            )
            log_path = workspace / "vault" / appended["path"]
            self.assertTrue(appended["appended"])
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("Build P0 CLI", log_text)
            log_note = ProjectKb(workspace / "vault").read_note(log_path)
            self.assertEqual(log_note.frontmatter["type"], "log")
            self.assertEqual(log_note.frontmatter["project"], "Demo")
            self.assertEqual(log_note.frontmatter["period"], log_path.stem)
            self.assertIn("log", log_note.frontmatter["tags"])

            audit = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "audit.jsonl"
            audit_lines = audit.read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(audit_lines[-1])["operation"], "append_log")

            stale = self.parse_json(self.run_kb(workspace, "stale", "--project", "Demo", "--commit", "HEAD"))
            self.assertTrue(any(item["reason"] == "verified_commit missing" for item in stale["stale"]))

    def test_status_reports_repo_hot_and_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            status = self.parse_json(self.run_kb(workspace, "status", "--project", "Demo"))
            self.assertEqual(status["status"], "active")
            self.assertEqual(status["path"], "Projects/Demo/_index.md")
            self.assertEqual(Path(status["repo"]).resolve(), repo.resolve())
            self.assertEqual(status["hot"], "Projects/Demo/hot.md")
            self.assertEqual(status["transport"], "auto")
            self.assertIn("project", status["types"])

    def test_stale_includes_context_and_task_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            context_path = project_root / "context.md"
            context_path.write_text(
                """---
schema_version: 1
type: context
project: Demo
source_paths: []
verified_commit: abc123
confidence: medium
tags:
  - context
---
# Context

## Current Context

## Sources
""",
                encoding="utf-8",
            )
            task_path = project_root / "tasks" / "example-task.md"
            task_path.write_text(
                """---
schema_version: 1
type: task
project: Demo
task_id: example-task
status: proposed
source_paths: []
verified_commit:
confidence: medium
tags:
  - task
---
# Example Task

## Status

- proposed

## Repo

## Branch

## Commit

## Files

## Commands

## Result

## Follow-ups
""",
                encoding="utf-8",
            )

            stale = self.parse_json(self.run_kb(workspace, "stale", "--project", "Demo", "--commit", "HEAD"))
            reasons = {item["path"]: item["reason"] for item in stale["stale"]}
            self.assertEqual(reasons["Projects/Demo/context.md"], "verified_commit differs from HEAD")
            self.assertEqual(reasons["Projects/Demo/tasks/example-task.md"], "verified_commit missing")

    def test_append_log_requires_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            summary = workspace / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "title": "Unproven task",
                        "summary": "This write-back has no file, command, commit, source, URL, or repo evidence.",
                        "result": "passed",
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "append-log", "--project", "Demo", "--from-file", str(summary), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("append-log requires provenance", result.stderr)
            log_dir = workspace / "vault" / "Projects" / "Demo" / "logs"
            self.assertFalse(any(log_dir.glob("*.md")))

    def test_append_log_refuses_invalid_existing_log_before_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            month = datetime.now().strftime("%Y-%m")
            project_root = workspace / "vault" / "Projects" / "Demo"
            log_path = project_root / "logs" / f"{month}.md"
            log_path.write_text(f"# Demo Task Log {month}\n\n", encoding="utf-8")

            payload = workspace / "summary.json"
            payload.write_text(
                json.dumps(
                    {
                        "title": "Append to invalid log",
                        "summary": "This should not be audited because the log lacks frontmatter.",
                        "commands": ["python -m unittest"],
                        "result": "passed",
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_kb(workspace, "append-log", "--project", "Demo", "--from-file", str(payload), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target validation failed", result.stderr)
            self.assertNotIn("Append to invalid log", log_path.read_text(encoding="utf-8"))
            audit = project_root / ".vault-meta" / "audit.jsonl"
            self.assertFalse(audit.exists())

    def test_append_log_persists_source_path_and_url_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            summary = workspace / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "title": "Record external source",
                        "summary": "Captured a verified external reference.",
                        "source_paths": ["docs/design.md"],
                        "url": "https://example.com/reference",
                        "result": "passed",
                    }
                ),
                encoding="utf-8",
            )

            appended = self.parse_json(
                self.run_kb(workspace, "append-log", "--project", "Demo", "--from-file", str(summary))
            )
            log_text = (workspace / "vault" / appended["path"]).read_text(encoding="utf-8")
            self.assertIn("- Source Paths: docs/design.md", log_text)
            self.assertIn("- URLs: https://example.com/reference", log_text)

    def test_cli_does_not_expose_destructive_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            help_text = self.run_kb(workspace, "--help").stdout
            self.assertNotIn("delete", help_text)
            self.assertNotIn("overwrite", help_text)
            self.assertNotIn("bulk", help_text)

    def test_mcp_lists_only_safe_facade_tools_and_can_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.search",
                        "arguments": {
                            "vault": str(vault),
                            "project": "Demo",
                            "query": "Known Pitfalls",
                            "limit": 1,
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses = [json.loads(line) for line in proc.stdout.splitlines()]
            tools = responses[1]["result"]["tools"]
            tool_names = {tool["name"] for tool in tools}
            self.assertTrue(
                {"kb.project_find", "kb.search", "kb.read", "kb.append_log", "kb.check_staleness"}.issubset(
                    tool_names
                )
            )
            self.assertFalse(any("delete" in name or "overwrite" in name or "bulk" in name for name in tool_names))
            search_tool = next(tool for tool in tools if tool["name"] == "kb.search")
            self.assertEqual(search_tool["inputSchema"]["properties"]["limit"]["maximum"], 5)
            retrieve_tool = next(tool for tool in tools if tool["name"] == "kb.retrieve")
            self.assertEqual(retrieve_tool["inputSchema"]["properties"]["limit"]["maximum"], 5)
            append_tool = next(tool for tool in tools if tool["name"] == "kb.append_log")
            append_properties = append_tool["inputSchema"]["properties"]
            self.assertIn("source_paths", append_properties)
            self.assertIn("url", append_properties)
            self.assertIn("urls", append_properties)
            provenance_alternatives = {
                tuple(item["required"]) for item in append_tool["inputSchema"].get("anyOf", [])
            }
            self.assertEqual(
                provenance_alternatives,
                {("commit",), ("commands",), ("files",), ("source_paths",), ("url",), ("urls",), ("repo",)},
            )
            decision_tool = next(tool for tool in tools if tool["name"] == "kb.create_decision")
            decision_alternatives = {
                tuple(item["required"]) for item in decision_tool["inputSchema"].get("anyOf", [])
            }
            self.assertEqual(decision_alternatives, {("source_paths",), ("verification_command",)})
            search_payload = json.loads(responses[2]["result"]["content"][0]["text"])
            self.assertEqual(len(search_payload["results"]), 1)

    def test_mcp_exposes_readonly_bm25_retrieve_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            module = vault / "Projects" / "Demo" / "modules" / "retrieval.md"
            module.write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Retrieval
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Retrieval

## BM25 MCP

The MCP retrieve tool should return contextual chunk hits for agent runtimes.
""",
                encoding="utf-8",
            )

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.retrieve",
                        "arguments": {
                            "vault": str(vault),
                            "project": "Demo",
                            "query": "contextual chunk agent runtimes",
                            "limit": 1,
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses = [json.loads(line) for line in proc.stdout.splitlines()]
            tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
            self.assertIn("kb.retrieve", tool_names)
            self.assertFalse(any("delete" in name or "overwrite" in name or "bulk" in name for name in tool_names))

            payload = json.loads(responses[2]["result"]["content"][0]["text"])
            self.assertEqual(payload["notes"][0]["heading"], "BM25 MCP")
            self.assertIn("Retrieval > BM25 MCP", payload["notes"][0]["contextual_prefix"])
            self.assertIn("agent runtimes", payload["notes"][0]["content"])

    def test_mcp_append_log_writes_audit_source_as_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.append_log",
                        "arguments": {
                            "vault": str(vault),
                            "project": "Demo",
                            "title": "MCP append audit",
                            "summary": "Verified append through the MCP facade.",
                            "result": "passed",
                            "commit": "abc123",
                            "source_paths": ["docs/mcp.md"],
                            "url": "https://example.com/mcp",
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses = [json.loads(line) for line in proc.stdout.splitlines()]
            payload = json.loads(responses[1]["result"]["content"][0]["text"])
            self.assertTrue(payload["appended"])
            log_text = (vault / payload["path"]).read_text(encoding="utf-8")
            self.assertIn("- Source Paths: docs/mcp.md", log_text)
            self.assertIn("- URLs: https://example.com/mcp", log_text)

            audit = vault / "Projects" / "Demo" / ".vault-meta" / "audit.jsonl"
            entry = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(entry["operation"], "append_log")
            self.assertEqual(entry["actor"], "mcp")
            self.assertEqual(entry["source"], "mcp")

    def test_p1_cli_creates_decisions_updates_frontmatter_and_exports_adapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            (repo / "src").mkdir()
            (repo / "src" / "example.ts").write_text("export const example = true;\n", encoding="utf-8")
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            decision = self.parse_json(
                self.run_kb(
                    workspace,
                    "create-decision",
                    "--project",
                    "Demo",
                    "--title",
                    "Use safe facade",
                    "--status",
                    "accepted",
                    "--source-path",
                    "src/example.ts",
                    "--verification-command",
                    "python -m unittest tests.test_project_kb -v",
                    "--commit",
                    "abc123",
                )
            )
            decision_path = workspace / "vault" / decision["path"]
            decision_text = decision_path.read_text(encoding="utf-8")
            self.assertIn("# ADR-0002: Use safe facade", decision_text)
            self.assertIn("src/example.ts", decision_text)
            self.assertIn("python -m unittest", decision_text)

            updated_status = self.parse_json(
                self.run_kb(workspace, "update-project-status", "--project", "Demo", "--status", "paused")
            )
            self.assertEqual(updated_status["status"], "paused")
            project_locks = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "locks"
            stray_locks = workspace / "vault" / "Projects" / ".vault-meta" / "locks"
            self.assertTrue(project_locks.exists())
            self.assertFalse(stray_locks.exists())

            updated_field = self.parse_json(
                self.run_kb(
                    workspace,
                    "update-frontmatter-field",
                    "--path",
                    "Projects/Demo/modules/example.md",
                    "--field",
                    "confidence",
                    "--value",
                    "high",
                )
            )
            self.assertEqual(updated_field["field"], "confidence")
            module = self.parse_json(
                self.run_kb(workspace, "read", "--path", "Projects/Demo/modules/example.md")
            )
            self.assertEqual(module["frontmatter"]["confidence"], "high")

            index = self.parse_json(self.run_kb(workspace, "index", "--project", "Demo"))
            self.assertTrue((workspace / "vault" / index["path"]).exists())
            retrieved = self.parse_json(
                self.run_kb(workspace, "retrieve", "--project", "Demo", "--query", "safe facade", "--limit", "3")
            )
            self.assertLessEqual(len(retrieved["notes"]), 3)
            self.assertTrue(any("ADR-0002" in note["title"] for note in retrieved["notes"]))

            locks = self.parse_json(self.run_kb(workspace, "lock", "list", "--project", "Demo"))
            self.assertEqual(locks["locks"], [])

            for agent in ["codex", "claude", "openclaw", "opencode", "generic"]:
                adapter = self.parse_json(
                    self.run_kb(workspace, "export-adapter", "--agent", agent, "--project", "Demo")
                )
                adapter_path = workspace / "vault" / adapter["path"]
                adapter_text = adapter_path.read_text(encoding="utf-8")
                self.assertIn("Access Disclosure", adapter_text)
                self.assertIn("Network access:", adapter_text)
                self.assertIn("Vault-external files:", adapter_text)
                self.assertIn("Remote LLM API:", adapter_text)
                self.assertIn("Telemetry:", adapter_text)
                self.assertIn("Paid services:", adapter_text)

    def test_lock_files_are_path_specific_for_same_named_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            kb = ProjectKb(workspace / "vault")
            project_root = workspace / "vault" / "Projects" / "Demo"
            module_path = project_root / "modules" / "same.md"
            decision_path = project_root / "decisions" / "same.md"

            with kb.lock_file(module_path):
                module_locks = kb.lock_list("Demo")["locks"]
            with kb.lock_file(decision_path):
                decision_locks = kb.lock_list("Demo")["locks"]

            self.assertEqual(len(module_locks), 1)
            self.assertEqual(len(decision_locks), 1)
            self.assertIn("created_at", module_locks[0])
            self.assertIn("created_at", decision_locks[0])
            self.assertNotEqual(module_locks[0]["path"], decision_locks[0]["path"])
            self.assertIn("modules", module_locks[0]["path"])
            self.assertIn("decisions", decision_locks[0]["path"])

    def test_create_decision_serializes_adr_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "one.ts").write_text("export const one = true;\n", encoding="utf-8")
            (repo / "src" / "two.ts").write_text("export const two = true;\n", encoding="utf-8")
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            kb = ProjectKb(workspace / "vault")
            original_write_if_missing = kb.write_if_missing
            delay_once = threading.Event()

            def delayed_write(path: Path, content: str) -> None:
                if path.name.startswith("ADR-") and "example" not in path.name and not delay_once.is_set():
                    delay_once.set()
                    time.sleep(0.2)
                original_write_if_missing(path, content)

            kb.write_if_missing = delayed_write  # type: ignore[method-assign]
            results: list[dict] = []
            errors: list[Exception] = []

            def create(title: str, source_path: str) -> None:
                try:
                    results.append(
                        kb.create_decision(
                            "Demo",
                            title,
                            source_paths=[source_path],
                            verification_command="python -m unittest tests.test_project_kb -v",
                            commit="abc123",
                        )
                    )
                except Exception as exc:  # pragma: no cover - test should fail explicitly
                    errors.append(exc)

            thread_one = threading.Thread(target=create, args=("Alpha", "src/one.ts"))
            thread_two = threading.Thread(target=create, args=("Beta", "src/two.ts"))
            thread_one.start()
            thread_two.start()
            thread_one.join(timeout=5)
            thread_two.join(timeout=5)

            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            paths = sorted(item["path"] for item in results)
            numbers = [Path(path).name.split("-")[1] for path in paths]
            self.assertEqual(numbers, ["0002", "0003"])

    def test_lock_contention_events_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            kb = ProjectKb(workspace / "vault")
            project_root = workspace / "vault" / "Projects" / "Demo"
            log_path = project_root / "logs" / "2026-06.md"
            log_path.write_text(kb.log_note("Demo", "2026-06"), encoding="utf-8")

            with kb.lock_file(log_path):
                started = threading.Event()
                finished = threading.Event()

                def contend() -> None:
                    started.set()
                    with kb.lock_file(log_path):
                        pass
                    finished.set()

                thread = threading.Thread(target=contend)
                thread.start()
                self.assertTrue(started.wait(timeout=1))
                time.sleep(0.15)
                self.assertFalse(finished.is_set())

            thread.join(timeout=2)
            self.assertTrue(finished.is_set())

            events = kb.read_pilot_events("Demo")
            contention = [event for event in events if event.get("event_type") == "lock_contention"]
            self.assertEqual(len(contention), 1)
            self.assertTrue(contention[0]["path"].endswith("logs/2026-06.md"))

    def test_stale_lock_is_reclaimed_and_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            kb = ProjectKb(workspace / "vault")
            project_root = workspace / "vault" / "Projects" / "Demo"
            log_path = project_root / "logs" / "2026-06.md"
            log_path.write_text(kb.log_note("Demo", "2026-06"), encoding="utf-8")

            lock_dir = project_root / ".vault-meta" / "locks"
            lock_path = lock_dir / f"{kb.lock_name(log_path)}.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(json.dumps({"target": str(log_path), "created_at": "stale"}), encoding="utf-8")
            stale_time = time.time() - 301
            os.utime(lock_path, (stale_time, stale_time))

            with kb.lock_file(log_path):
                self.assertTrue(lock_path.exists())
                self.assertFalse(kb.lock_list("Demo")["locks"][0]["stale"])

            self.assertFalse(lock_path.exists())

    def test_index_builds_bm25_chunks_and_retrieve_returns_contextual_chunk_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            for idx in range(6):
                (project_root / "modules" / f"writers-{idx}.md").write_text(
                    f"""---
schema_version: 1
type: module
project: Demo
module: Writers{idx}
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Writers {idx}

## Overview

This section talks about adapters, notes, and general project coordination.

## Multi Writer Safety

Concurrent append writers must acquire a per-file lock before writing audit-backed task logs.
The lock file prevents two agents from corrupting the same monthly log.
""",
                    encoding="utf-8",
                )
            (project_root / "modules" / "noise.md").write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Noise
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Noise

## Overview

facade facade facade facade facade facade facade facade facade facade
general note text that should not outrank the exact lock audit writer chunk.
""",
                encoding="utf-8",
            )

            indexed = self.parse_json(self.run_kb(workspace, "index", "--project", "Demo"))
            self.assertGreater(indexed["chunks"], indexed["notes"])

            bm25_index = json.loads(
                (project_root / ".vault-meta" / "bm25" / "index.json").read_text(encoding="utf-8")
            )
            self.assertIn("avgdl", bm25_index)
            self.assertTrue(any("term_freq" in chunk for chunk in bm25_index["chunks"]))

            chunk_index = json.loads(
                (project_root / ".vault-meta" / "chunks" / "index.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                any(
                    chunk["heading"] == "Multi Writer Safety"
                    and chunk["contextual_prefix"].endswith("Multi Writer Safety")
                    and chunk["path"].endswith(".md")
                    for chunk in chunk_index["chunks"]
                )
            )

            retrieved = self.parse_json(
                self.run_kb(
                    workspace,
                    "retrieve",
                    "--project",
                    "Demo",
                    "--query",
                    "lock audit writers",
                    "--limit",
                    "10",
                )
            )
            self.assertEqual(len(retrieved["notes"]), 5)
            first = retrieved["notes"][0]
            self.assertIn("modules/writers-", first["path"])
            self.assertEqual(first["heading"], "Multi Writer Safety")
            self.assertTrue(first["contextual_prefix"].endswith("Multi Writer Safety"))
            self.assertIn("per-file lock", first["content"])
            self.assertNotIn("## Overview", first["content"])

    def test_p1_rejects_unsafe_structured_writes_and_validate_checks_links_schema_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            bad_status = self.run_kb(
                workspace,
                "update-project-status",
                "--project",
                "Demo",
                "--status",
                "deleted",
                check=False,
            )
            self.assertNotEqual(bad_status.returncode, 0)

            unsafe_field = self.run_kb(
                workspace,
                "update-frontmatter-field",
                "--path",
                "Projects/Demo/modules/example.md",
                "--field",
                "repo",
                "--value",
                "H:/elsewhere",
                check=False,
            )
            self.assertNotEqual(unsafe_field.returncode, 0)

            missing_source_decision = self.run_kb(
                workspace,
                "create-decision",
                "--project",
                "Demo",
                "--title",
                "No provenance",
                check=False,
            )
            self.assertNotEqual(missing_source_decision.returncode, 0)

            project_root = workspace / "vault" / "Projects" / "Demo"
            (project_root / "modules" / "broken.md").write_text(
                """---
schema_version: 999
type: module
project: Demo
module: Broken
source_paths: []
verified_commit:
confidence: medium
tags: []
---
# Broken

Links to [[missing-note]].

node_modules/.vite/cache
""",
                encoding="utf-8",
            )
            validation = self.parse_json(self.run_kb(workspace, "validate", "--project", "Demo", check=False))
            messages = "\n".join(item["message"] for item in validation["errors"])
            self.assertIn("unsupported schema_version: 999", messages)
            self.assertIn("broken wikilink: missing-note", messages)
            self.assertIn("generated-noise marker", messages)

    def test_create_decision_validates_target_file_before_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(
                workspace,
                "create-decision",
                "--project",
                "Demo",
                "--title",
                "Broken source path",
                "--source-path",
                "src/missing.ts",
                "--commit",
                "abc123",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target validation failed", result.stderr)
            decisions = workspace / "vault" / "Projects" / "Demo" / "decisions"
            self.assertFalse(any(path.name.endswith("broken-source-path.md") for path in decisions.glob("ADR-*.md")))
            audit = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "audit.jsonl"
            if audit.exists():
                self.assertFalse(any("create_decision" in line for line in audit.read_text(encoding="utf-8").splitlines()))

    def test_update_frontmatter_field_validates_target_file_before_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            module_path = project_root / "modules" / "example.md"
            module_path.write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Example
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Example

## Responsibility

## Entry Points

## Key Files

## Known Pitfalls

## Verification
""",
                encoding="utf-8",
            )

            result = self.run_kb(
                workspace,
                "update-frontmatter-field",
                "--path",
                "Projects/Demo/modules/example.md",
                "--field",
                "confidence",
                "--value",
                "high",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target validation failed", result.stderr)
            module_text = module_path.read_text(encoding="utf-8")
            self.assertIn("confidence: medium", module_text)
            self.assertNotIn("confidence: high", module_text)
            audit = project_root / ".vault-meta" / "audit.jsonl"
            if audit.exists():
                self.assertFalse(any("update_frontmatter:confidence" in line for line in audit.read_text(encoding="utf-8").splitlines()))

    def test_update_frontmatter_field_rejects_invalid_source_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            module_path = project_root / "modules" / "example.md"
            module_path.write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Example
source_paths:
  - src/missing.ts
verified_commit:
confidence: medium
tags:
  - module
---
# Example

## Responsibility

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
""",
                encoding="utf-8",
            )

            result = self.run_kb(
                workspace,
                "update-frontmatter-field",
                "--path",
                "Projects/Demo/modules/example.md",
                "--field",
                "confidence",
                "--value",
                "high",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target validation failed", result.stderr)
            self.assertIn("source path does not exist: src/missing.ts", result.stderr)
            module_text = module_path.read_text(encoding="utf-8")
            self.assertIn("confidence: medium", module_text)
            self.assertNotIn("confidence: high", module_text)

    def test_update_frontmatter_field_rejects_broken_wikilinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            module_path = project_root / "modules" / "example.md"
            module_path.write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Example
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Example

## Responsibility

Links to [[missing-note]].

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
""",
                encoding="utf-8",
            )

            result = self.run_kb(
                workspace,
                "update-frontmatter-field",
                "--path",
                "Projects/Demo/modules/example.md",
                "--field",
                "confidence",
                "--value",
                "high",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target validation failed", result.stderr)
            self.assertIn("broken wikilink: missing-note", result.stderr)
            module_text = module_path.read_text(encoding="utf-8")
            self.assertIn("confidence: medium", module_text)
            self.assertNotIn("confidence: high", module_text)

    def test_update_frontmatter_field_rejects_generated_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = workspace / "vault" / "Projects" / "Demo"
            module_path = project_root / "modules" / "example.md"
            module_path.write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Example
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Example

## Responsibility

node_modules/.vite/cache

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
""",
                encoding="utf-8",
            )

            result = self.run_kb(
                workspace,
                "update-frontmatter-field",
                "--path",
                "Projects/Demo/modules/example.md",
                "--field",
                "confidence",
                "--value",
                "high",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target validation failed", result.stderr)
            self.assertIn("generated-noise marker: node_modules/", result.stderr)
            module_text = module_path.read_text(encoding="utf-8")
            self.assertIn("confidence: medium", module_text)
            self.assertNotIn("confidence: high", module_text)

    def test_mcp_exposes_p1_structured_tools_without_destructive_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.update_project_status",
                        "arguments": {"vault": str(vault), "project": "Demo", "status": "paused"},
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses = [json.loads(line) for line in proc.stdout.splitlines()]
            tool_names = {tool["name"] for tool in responses[0]["result"]["tools"]}
            self.assertIn("kb.project_create", tool_names)
            self.assertIn("kb.create_decision", tool_names)
            self.assertIn("kb.update_project_status", tool_names)
            self.assertIn("kb.update_frontmatter_field", tool_names)
            self.assertFalse(any("delete" in name or "overwrite" in name or "bulk" in name for name in tool_names))
            payload = json.loads(responses[1]["result"]["content"][0]["text"])
            self.assertEqual(payload["status"], "paused")

    def test_mcp_update_frontmatter_field_returns_error_for_invalid_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            module_path = vault / "Projects" / "Demo" / "modules" / "example.md"
            module_path.write_text(
                """---
schema_version: 1
type: module
project: Demo
module: Example
source_paths: []
verified_commit:
confidence: medium
tags:
  - module
---
# Example

## Responsibility

Links to [[missing-note]].

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
""",
                encoding="utf-8",
            )

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.update_frontmatter_field",
                        "arguments": {
                            "vault": str(vault),
                            "path": "Projects/Demo/modules/example.md",
                            "field": "confidence",
                            "value": "high",
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            response = json.loads(proc.stdout)
            self.assertIn("error", response)
            self.assertIn("broken wikilink: missing-note", response["error"]["message"])

    def test_mcp_create_decision_returns_error_for_invalid_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.create_decision",
                        "arguments": {
                            "vault": str(vault),
                            "project": "Demo",
                            "title": "Broken source path",
                            "source_paths": ["src/missing.ts"],
                            "commit": "abc123",
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            response = json.loads(proc.stdout)
            self.assertIn("error", response)
            self.assertIn("source path does not exist: src/missing.ts", response["error"]["message"])

    def test_mcp_update_project_status_returns_error_for_invalid_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.update_project_status",
                        "arguments": {
                            "vault": str(vault),
                            "project": "Demo",
                            "status": "deleted",
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            response = json.loads(proc.stdout)
            self.assertIn("error", response)
            self.assertIn("invalid project status: deleted", response["error"]["message"])

    def test_mcp_check_staleness_includes_context_and_task_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            project_root = vault / "Projects" / "Demo"
            (project_root / "context.md").write_text(
                """---
schema_version: 1
type: context
project: Demo
source_paths: []
verified_commit: abc123
confidence: medium
tags:
  - context
---
# Context

## Current Context

## Sources
""",
                encoding="utf-8",
            )
            (project_root / "tasks" / "example-task.md").write_text(
                """---
schema_version: 1
type: task
project: Demo
task_id: example-task
status: proposed
source_paths: []
verified_commit:
confidence: medium
tags:
  - task
---
# Example Task

## Status

- proposed

## Repo

## Branch

## Commit

## Files

## Commands

## Result

## Follow-ups
""",
                encoding="utf-8",
            )

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.check_staleness",
                        "arguments": {
                            "vault": str(vault),
                            "project": "Demo",
                            "current_commit": "HEAD",
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            response = json.loads(proc.stdout)
            payload = json.loads(response["result"]["content"][0]["text"])
            reasons = {item["path"]: item["reason"] for item in payload["stale"]}
            self.assertEqual(reasons["Projects/Demo/context.md"], "verified_commit differs from HEAD")
            self.assertEqual(reasons["Projects/Demo/tasks/example-task.md"], "verified_commit missing")

    def test_root_agent_docs_reference_project_kb_workflow(self):
        agents_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude_text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("project-kb", agents_text.lower())
        self.assertIn("project-kb", claude_text.lower())
        self.assertIn("hot.md", agents_text)
        self.assertIn("historical decision", claude_text.lower())

    def test_root_claude_project_kb_entrypoints_exist(self):
        self.assertTrue((ROOT / ".claude" / "skills" / "project-kb" / "SKILL.md").exists())
        self.assertTrue((ROOT / ".claude" / "commands" / "wiki.md").exists())

    def test_root_opencode_project_kb_skill_exists(self):
        self.assertTrue((ROOT / ".opencode" / "skill" / "project-kb" / "SKILL.md").exists())

    def test_root_codex_project_kb_skill_exists(self):
        self.assertTrue((ROOT / ".codex" / "skills" / "project-kb" / "SKILL.md").exists())

    def test_root_codex_config_registers_project_kb_mcp_draft(self):
        config_path = ROOT / ".codex" / "config.toml"
        self.assertTrue(config_path.exists())
        config_text = config_path.read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.project-kb]", config_text)
        self.assertIn('command = "python"', config_text)
        self.assertIn("scripts/kb_mcp.py", config_text)
        self.assertIn("PROJECT_KB_VAULT", config_text)

    def test_root_claude_index_references_project_kb_entrypoints(self):
        index_data = json.loads((ROOT / ".claude" / "index.json").read_text(encoding="utf-8"))
        modules = index_data["modules"]
        self.assertTrue(any(module["path"] == ".claude/skills/project-kb/" and "SKILL.md" in module["entry_files"] for module in modules))
        self.assertTrue(any(module["path"] == ".claude/commands/" and "wiki.md" in module["entry_files"] for module in modules))

    def test_agent_adapter_doc_references_root_codex_and_opencode_entrypoints(self):
        doc = (ROOT / "docs" / "project-kb" / "agent-adapters.md").read_text(encoding="utf-8")
        self.assertIn("`.codex/config.toml`", doc)
        self.assertIn("`.codex/skills/project-kb/SKILL.md`", doc)
        self.assertIn("`.opencode/skill/project-kb/SKILL.md`", doc)

    def test_root_agent_docs_describe_project_kb_automated_tests(self):
        agents_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude_text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("不含传统单元测试", agents_text)
        self.assertNotIn("不含传统单元测试", claude_text)
        self.assertIn("tests/test_project_kb.py", agents_text)
        self.assertIn("tests/test_project_kb.py", claude_text)

    def test_pilot_metrics_and_repo_integration_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "pilot", "plan", "--project", "Demo")

            event_file = workspace / "pilot-event.json"
            event_file.write_text(
                json.dumps(
                    {
                        "task_id": "task-001",
                        "title": "Use KB on real task",
                        "searches": 2,
                        "notes_read": 3,
                        "write_backs": 1,
                        "stale_notes": 0,
                        "effective_hit": True,
                        "false_positive": False,
                        "stale_misguidance": False,
                        "injected_notes": 3,
                        "context_tokens": 1200,
                        "write_back_accepted": True,
                        "destructive_write_incident": False,
                        "lock_contention_count": 2,
                        "validation_failures": 1,
                    }
                ),
                encoding="utf-8",
            )

            recorded = self.parse_json(
                self.run_kb(workspace, "pilot", "record", "--project", "Demo", "--from-file", str(event_file))
            )
            self.assertTrue((workspace / "vault" / recorded["path"]).exists())
            contention_file = workspace / "contention-event.json"
            contention_file.write_text(
                json.dumps(
                    {
                        "event_type": "lock_contention",
                        "lock_contention_count": 1,
                        "path": "Projects/Demo/logs/2026-06.md",
                    }
                ),
                encoding="utf-8",
            )
            self.run_kb(workspace, "pilot", "record", "--project", "Demo", "--from-file", str(contention_file))

            metrics = self.parse_json(self.run_kb(workspace, "metrics", "--project", "Demo"))
            self.assertEqual(metrics["tasks"], 1)
            self.assertEqual(metrics["effective_retrieval_hit_rate"], 1.0)
            self.assertEqual(metrics["average_injected_notes"], 3.0)
            self.assertEqual(metrics["destructive_write_incidents"], 0)
            self.assertEqual(metrics["lock_contention_count"], 3)
            self.assertEqual(metrics["validation_failures"], 1)
            self.assertTrue(metrics["thresholds"]["effective_retrieval_hit_rate"]["passed"])
            self.assertEqual(metrics["thresholds"]["validation_failures"]["actual"], 1)
            self.assertEqual(metrics["thresholds"]["lock_contention_count"]["actual"], 3)

            install = self.parse_json(
                self.run_kb(workspace, "install-repo-adapters", "--project", "Demo", "--repo", str(repo))
            )
            expected = {
                ".project-kb/project.json",
                ".project-kb/adapters/codex/AGENTS.project-kb.md",
                ".project-kb/adapters/claude/CLAUDE.project-kb.md",
                ".project-kb/adapters/openclaw/OPENCLAW.project-kb.md",
                ".project-kb/adapters/opencode/OPENCODE.project-kb.md",
                ".project-kb/adapters/generic/GENERIC.project-kb.md",
                ".project-kb/host-configs/codex.config.toml",
                ".project-kb/host-configs/claude.mcp.json",
                ".project-kb/host-configs/openclaw.mcp.json5",
                ".project-kb/host-configs/opencode.md",
                ".project-kb/host-configs/README.md",
            }
            self.assertEqual(set(install["files"]), expected)
            project_json = json.loads((repo / ".project-kb" / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["project"], "Demo")
            self.assertEqual(Path(project_json["repo"]).resolve(), repo.resolve())
            codex_config = (repo / ".project-kb" / "host-configs" / "codex.config.toml").read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.project-kb]", codex_config)
            self.assertIn("scripts/kb_mcp.py", codex_config)
            self.assertIn("PROJECT_KB_VAULT", codex_config)
            host_readme = (repo / ".project-kb" / "host-configs" / "README.md").read_text(encoding="utf-8")
            self.assertIn("draft", host_readme.lower())
            self.assertIn("do not auto-install", host_readme.lower())
            self.assertIn("opencode.md", host_readme)

    def test_pilot_plan_writes_ten_task_plan_with_required_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            plan = kb.pilot_plan("Demo")

            self.assertEqual(plan["project"], "Demo")
            self.assertEqual(plan["task_count"], 10)
            self.assertEqual(plan["path"], "Projects/Demo/.vault-meta/pilot/plan.json")
            categories = {task["category"] for task in plan["tasks"]}
            self.assertTrue({"architecture", "implementation", "verification"}.issubset(categories))
            hosts = {task["host"] for task in plan["tasks"]}
            self.assertIn("Codex", hosts)
            self.assertIn("Claude Code", hosts)
            self.assertIn("OpenCode", hosts)
            self.assertTrue(all(task["event_file"].endswith(".json") for task in plan["tasks"]))
            self.assertIn("python scripts/kb.py pilot record --project Demo --from-file", plan["record_command_template"])
            stored = json.loads((workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "pilot" / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["task_count"], 10)
            first_template = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "pilot" / "events" / "task-001.json"
            self.assertTrue(first_template.exists())
            template_payload = json.loads(first_template.read_text(encoding="utf-8"))
            self.assertEqual(template_payload["task_id"], "task-001")
            self.assertEqual(template_payload["status"], "planned")
            self.assertIn("Record actual KB search count", template_payload["notes"])

    def test_cli_pilot_plan_writes_plan_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "pilot", "plan", "--project", "Demo")

            payload = self.parse_json(result)
            self.assertEqual(payload["task_count"], 10)
            self.assertEqual(payload["path"], "Projects/Demo/.vault-meta/pilot/plan.json")
            self.assertTrue((workspace / "vault" / payload["path"]).exists())

    def test_pilot_status_reports_planned_recorded_and_missing_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            kb.pilot_plan("Demo")
            kb.pilot_record(
                "Demo",
                {
                    "task_id": "task-001",
                    "title": "Completed first task",
                    "searches": 1,
                    "notes_read": 2,
                    "write_backs": 0,
                    "stale_notes": 0,
                    "effective_hit": True,
                    "false_positive": False,
                    "stale_misguidance": False,
                    "injected_notes": 2,
                    "context_tokens": 800,
                    "write_back_accepted": True,
                    "destructive_write_incident": False,
                    "lock_contention_count": 0,
                    "validation_failures": 0,
                },
            )

            status = kb.pilot_status("Demo")

            self.assertEqual(status["project"], "Demo")
            self.assertEqual(status["planned"], 10)
            self.assertEqual(status["recorded"], 1)
            self.assertEqual(status["missing"], 9)
            self.assertEqual(status["tasks"][0]["status"], "recorded")
            self.assertEqual(status["tasks"][1]["status"], "planned")
            self.assertEqual(status["metrics"]["tasks"], 1)

    def test_pilot_record_rejects_events_missing_plan_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            kb.pilot_plan("Demo")

            with self.assertRaises(ValueError) as missing_required:
                kb.pilot_record(
                    "Demo",
                    {
                        "task_id": "task-001",
                        "title": "Incomplete task event",
                        "searches": 1,
                        "notes_read": 1,
                        "effective_hit": True,
                    },
                )

            self.assertIn("missing pilot event fields", str(missing_required.exception))
            events_path = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "pilot" / "events.jsonl"
            self.assertFalse(events_path.exists())

    def test_pilot_record_rejects_unplanned_task_id_and_negative_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            kb.pilot_plan("Demo")

            complete_event = {
                "task_id": "task-999",
                "title": "Unplanned task event",
                "searches": 1,
                "notes_read": 1,
                "write_backs": 0,
                "stale_notes": 0,
                "effective_hit": True,
                "false_positive": False,
                "stale_misguidance": False,
                "injected_notes": 1,
                "context_tokens": 100,
                "write_back_accepted": True,
                "destructive_write_incident": False,
                "lock_contention_count": 0,
                "validation_failures": 0,
            }

            with self.assertRaises(ValueError) as unplanned:
                kb.pilot_record("Demo", complete_event)

            self.assertIn("not in pilot plan", str(unplanned.exception))

            complete_event["task_id"] = "task-001"
            complete_event["notes_read"] = -1
            with self.assertRaises(ValueError) as negative:
                kb.pilot_record("Demo", complete_event)

            self.assertIn("non-negative integer", str(negative.exception))

    def test_pilot_record_preserves_environment_blocked_evidence_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            kb.pilot_plan("Demo")
            payload = {
                "task_id": "task-009",
                "title": "Route an OpenClaw-hosted session to the shared KB for a context lookup.",
                "status": "environment_blocked",
                "host": "OpenClaw",
                "category": "architecture",
                "searches": 0,
                "notes_read": 0,
                "write_backs": 0,
                "stale_notes": 0,
                "effective_hit": False,
                "false_positive": False,
                "stale_misguidance": False,
                "injected_notes": 0,
                "context_tokens": 0,
                "write_back_accepted": False,
                "destructive_write_incident": False,
                "lock_contention_count": 0,
                "validation_failures": 0,
                "notes": "Gateway RPC probe failed.",
                "evidence": ["openclaw gateway status --deep"],
            }

            kb.pilot_record("Demo", payload)
            event = kb.read_pilot_events("Demo")[0]

            self.assertEqual(event["status"], "environment_blocked")
            self.assertEqual(event["host"], "OpenClaw")
            self.assertEqual(event["category"], "architecture")
            self.assertEqual(event["notes"], "Gateway RPC probe failed.")
            self.assertEqual(event["evidence"], ["openclaw gateway status --deep"])
            with self.assertRaisesRegex(ValueError, "already recorded"):
                kb.pilot_record("Demo", payload)

    def test_cli_pilot_status_outputs_plan_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "pilot", "plan", "--project", "Demo")

            result = self.run_kb(workspace, "pilot", "status", "--project", "Demo")

            payload = self.parse_json(result)
            self.assertEqual(payload["planned"], 10)
            self.assertEqual(payload["recorded"], 0)
            self.assertEqual(payload["missing"], 10)

    def test_cli_pilot_record_rejects_invalid_event_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "pilot", "plan", "--project", "Demo")
            event_file = workspace / "bad-pilot-event.json"
            event_file.write_text(
                json.dumps(
                    {
                        "task_id": "task-999",
                        "title": "Bad pilot event",
                        "searches": 1,
                        "notes_read": 1,
                        "write_backs": 0,
                        "stale_notes": 0,
                        "effective_hit": True,
                        "false_positive": False,
                        "stale_misguidance": False,
                        "injected_notes": 1,
                        "context_tokens": 100,
                        "write_back_accepted": True,
                        "destructive_write_incident": False,
                        "lock_contention_count": 0,
                        "validation_failures": 0,
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_kb(
                workspace,
                "pilot",
                "record",
                "--project",
                "Demo",
                "--from-file",
                str(event_file),
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not in pilot plan", result.stderr)

    def test_transport_detect_reports_runtime_evidence_and_doctor_checks_exit_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            transport = self.parse_json(self.run_kb(workspace, "transport", "detect", "--project", "Demo"))
            self.assertEqual(transport["preferred"], "filesystem")
            self.assertEqual(transport["fallback_chain"], ["cli", "mcp_obsidian", "filesystem"])
            self.assertIn("cli", transport["available"])
            self.assertFalse(transport["available"]["cli"]["available"])
            self.assertTrue(transport["available"]["cli"]["path"].endswith("Obsidian.com") or transport["available"]["cli"]["path"] == "")
            self.assertIn("mcp_obsidian", transport["available"])
            self.assertTrue(transport["available"]["filesystem"]["available"])
            self.assertIn("path", transport["available"]["cli"])
            self.assertIn("checked", transport["available"]["mcp_obsidian"])
            self.assertIn("obsidian_cli", transport["evidence"])
            self.assertIn("project_kb_cli", transport["evidence"])
            self.assertIn("obsidian_local_rest_api", transport["evidence"])
            self.assertIn("project_kb_mcp", transport["evidence"])

            doctor = self.parse_json(self.run_kb(workspace, "doctor", "--project", "Demo"))
            checks = {item["name"]: item for item in doctor["checks"]}
            self.assertEqual(doctor["status"], "ready")
            self.assertTrue(checks["read_note"]["passed"])
            self.assertTrue(checks["search_note"]["passed"])
            self.assertTrue(checks["safe_surface"]["passed"])
            self.assertTrue(checks["validate"]["passed"])
            self.assertIn("kb.retrieve", doctor["safe_tools"])
            self.assertFalse(any("delete" in tool or "overwrite" in tool for tool in doctor["safe_tools"]))

    def test_transport_detect_distinguishes_obsidian_cli_from_project_kb_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")):
                transport = kb.transport_detect("Demo")

            self.assertEqual(transport["preferred"], "cli")
            self.assertEqual(transport["fallback_chain"], ["cli", "mcp_obsidian", "filesystem"])
            self.assertTrue(transport["available"]["cli"]["available"])
            self.assertEqual(transport["available"]["cli"]["path"], r"C:\Program Files\Obsidian\obsidian.exe")
            self.assertEqual(transport["available"]["cli"]["state"], "ready")
            self.assertIn("obsidian help succeeded", transport["available"]["cli"]["reason"])
            self.assertFalse(transport["available"]["mcp_obsidian"]["available"])
            self.assertTrue(transport["available"]["filesystem"]["available"])
            self.assertIn("project_kb_cli", transport["evidence"])
            self.assertTrue(transport["evidence"]["project_kb_cli"]["available"])
            self.assertTrue(transport["evidence"]["project_kb_cli"]["path"].endswith(str(Path("scripts") / "kb.py")))
            self.assertTrue(transport["evidence"]["project_kb_mcp"]["available"])

    def test_transport_detect_reports_disabled_obsidian_cli_when_binary_exists_but_setting_is_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"D:\soft\Obsidian\Obsidian.com"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "command line interface is not enabled")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")):
                transport = kb.transport_detect("Demo")

            self.assertFalse(transport["available"]["cli"]["available"])
            self.assertEqual(transport["available"]["cli"]["path"], r"D:\soft\Obsidian\Obsidian.com")
            self.assertEqual(transport["available"]["cli"]["state"], "disabled")
            self.assertIn("not enabled", transport["available"]["cli"]["reason"])
            self.assertFalse(transport["evidence"]["obsidian_cli"]["available"])
            self.assertIn("not enabled", transport["evidence"]["obsidian_cli"]["reason"])

    def test_doctor_ready_without_obsidian_cli_when_project_kb_surface_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            kb.pilot_plan("Demo")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=""), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "obsidian executable not found")
            ), mock.patch.object(
                ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")
            ):
                doctor = kb.doctor("Demo")

            checks = {item["name"]: item for item in doctor["checks"]}
            self.assertEqual(doctor["status"], "ready")
            self.assertTrue(checks["transport"]["passed"])
            self.assertFalse(checks["transport"]["detail"]["available"]["cli"]["available"])
            self.assertEqual(checks["transport"]["detail"]["available"]["cli"]["state"], "missing")
            self.assertTrue(checks["transport"]["detail"]["evidence"]["project_kb_cli"]["available"])

    def test_release_check_separates_engineering_environment_and_pilot_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            kb.pilot_plan("Demo")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=""), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "obsidian executable not found")
            ), mock.patch.object(
                ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")
            ):
                engineering = kb.release_check("Demo", "engineering")
                environment = kb.release_check("Demo", "environment")
                pilot = kb.release_check("Demo", "pilot")

            self.assertEqual(engineering["release_level"], "engineering")
            self.assertEqual(engineering["status"], "ready")
            engineering_checks = {item["name"]: item for item in engineering["checks"]}
            self.assertTrue(engineering_checks["doctor"]["passed"])
            self.assertTrue(engineering_checks["dangerous_surface_absent"]["passed"])
            self.assertTrue(engineering_checks["pilot_not_required"]["passed"])

            self.assertEqual(environment["status"], "blocked")
            environment_checks = {item["name"]: item for item in environment["checks"]}
            self.assertFalse(environment_checks["obsidian_cli_ready"]["passed"])
            self.assertFalse(environment_checks["local_rest_ready"]["passed"])
            self.assertFalse(environment_checks["transport_smoke"]["passed"])

            self.assertEqual(pilot["status"], "blocked")
            pilot_checks = {item["name"]: item for item in pilot["checks"]}
            self.assertFalse(pilot_checks["ten_task_pilot"]["passed"])
            self.assertEqual(pilot_checks["ten_task_pilot"]["actual"], 0)

            for index in range(10):
                kb.pilot_record(
                    "Demo",
                    {
                        "task_id": f"task-{index + 1:03d}",
                        "title": f"Pilot task {index + 1}",
                        "searches": 1,
                        "notes_read": 3,
                        "write_backs": 1,
                        "stale_notes": 0,
                        "effective_hit": True,
                        "false_positive": False,
                        "stale_misguidance": False,
                        "injected_notes": 3,
                        "context_tokens": 1000,
                        "write_back_accepted": True,
                        "destructive_write_incident": False,
                        "lock_contention_count": 0,
                        "validation_failures": 0,
                    },
                )

            pilot_ready = kb.release_check("Demo", "pilot")
            self.assertEqual(pilot_ready["status"], "ready")
            pilot_ready_checks = {item["name"]: item for item in pilot_ready["checks"]}
            self.assertTrue(pilot_ready_checks["ten_task_pilot"]["passed"])
            self.assertTrue(pilot_ready_checks["pilot_thresholds"]["passed"])

            full = kb.release_check("Demo", "full")
            self.assertEqual(full["status"], "blocked")
            full_checks = {item["name"]: item for item in full["checks"]}
            self.assertFalse(full_checks["environment"]["passed"])
            self.assertTrue(full_checks["pilot"]["passed"])

    def test_cli_release_check_returns_nonzero_when_gate_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            engineering = self.parse_json(self.run_kb(workspace, "release", "check", "--project", "Demo", "--level", "engineering"))
            self.assertEqual(engineering["status"], "ready")

            pilot = self.run_kb(workspace, "release", "check", "--project", "Demo", "--level", "pilot", check=False)
            self.assertNotEqual(pilot.returncode, 0)
            payload = self.parse_json(pilot)
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["release_level"], "pilot")

            full = self.run_kb(workspace, "release", "check", "--project", "Demo", "--level", "full", check=False)
            self.assertNotEqual(full.returncode, 0)
            full_payload = self.parse_json(full)
            self.assertEqual(full_payload["release_level"], "full")

    def test_release_check_can_require_current_commit_and_publication_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            stale = kb.release_check("Demo", "engineering", commit="abc123")
            self.assertEqual(stale["status"], "blocked")
            stale_checks = {item["name"]: item for item in stale["checks"]}
            self.assertFalse(stale_checks["stale_notes"]["passed"])
            self.assertGreater(stale_checks["stale_notes"]["actual"], 0)

            stale_optional = kb.release_check("Demo", "engineering")
            self.assertEqual(stale_optional["status"], "ready")
            optional_checks = {item["name"]: item for item in stale_optional["checks"]}
            self.assertEqual(optional_checks["stale_notes"]["actual"], "not checked")

            missing_artifacts = kb.release_check("Demo", "engineering", require_artifacts=True)
            self.assertEqual(missing_artifacts["status"], "blocked")
            artifact_checks = {item["name"]: item for item in missing_artifacts["checks"]}
            self.assertFalse(artifact_checks["release_artifacts"]["passed"])
            self.assertIn(".project-kb/project.json", artifact_checks["release_artifacts"]["missing"])

            kb.install_repo_adapters("Demo", str(repo))
            kb.export_host_configs("Demo")
            ready = kb.release_check("Demo", "engineering", require_artifacts=True)
            ready_checks = {item["name"]: item for item in ready["checks"]}
            self.assertEqual(ready["status"], "ready")
            self.assertTrue(ready_checks["release_artifacts"]["passed"])
            self.assertEqual(ready_checks["release_artifacts"]["missing"], [])

    def test_cli_release_check_accepts_commit_and_require_artifacts_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            stale = self.run_kb(
                workspace,
                "release",
                "check",
                "--project",
                "Demo",
                "--level",
                "engineering",
                "--commit",
                "abc123",
                check=False,
            )
            self.assertNotEqual(stale.returncode, 0)
            stale_payload = self.parse_json(stale)
            stale_checks = {item["name"]: item for item in stale_payload["checks"]}
            self.assertFalse(stale_checks["stale_notes"]["passed"])

            missing_artifacts = self.run_kb(
                workspace,
                "release",
                "check",
                "--project",
                "Demo",
                "--level",
                "engineering",
                "--require-artifacts",
                check=False,
            )
            self.assertNotEqual(missing_artifacts.returncode, 0)
            artifact_payload = self.parse_json(missing_artifacts)
            artifact_checks = {item["name"]: item for item in artifact_payload["checks"]}
            self.assertFalse(artifact_checks["release_artifacts"]["passed"])

    def test_environment_gate_requires_live_smoke_after_transport_availability(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(True, "http 200")):
                no_smoke = kb.release_check("Demo", "environment")

            no_smoke_checks = {item["name"]: item for item in no_smoke["checks"]}
            self.assertEqual(no_smoke["status"], "blocked")
            self.assertTrue(no_smoke_checks["obsidian_cli_ready"]["passed"])
            self.assertTrue(no_smoke_checks["local_rest_ready"]["passed"])
            self.assertFalse(no_smoke_checks["transport_smoke"]["passed"])
            self.assertEqual(no_smoke_checks["transport_smoke"]["actual"], "missing")

            def append_probe(path, content):
                target = workspace / "vault" / path
                with target.open("a", encoding="utf-8") as handle:
                    handle.write(content)

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(True, "http 200")), mock.patch.object(
                ProjectKb, "obsidian_cli_read"
            ) as cli_read, mock.patch.object(
                ProjectKb, "obsidian_cli_search"
            ) as cli_search, mock.patch.object(
                ProjectKb, "obsidian_rest_append"
            ) as rest_append:
                project_root = workspace / "vault" / "Projects" / "Demo"
                index_path = project_root / "_index.md"
                index_note = kb.read_note(index_path)
                cli_read.return_value = {"content": index_note.body, "frontmatter": index_note.frontmatter}
                cli_search.return_value = {"results": [{"path": "Projects/Demo/_index.md", "title": "Demo", "type": "project", "score": 1.0, "snippet": "Demo"}]}
                rest_append.side_effect = append_probe
                smoke = kb.release_smoke("Demo", "environment")
                after_smoke = kb.release_check("Demo", "environment")

            self.assertTrue(smoke["passed"])
            self.assertTrue(cli_read.called)
            self.assertTrue(cli_search.called)
            self.assertTrue(rest_append.called)
            smoke_path = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "release" / "environment-smoke.json"
            self.assertTrue(smoke_path.exists())
            after_smoke_checks = {item["name"]: item for item in after_smoke["checks"]}
            self.assertEqual(after_smoke["status"], "ready")
            self.assertTrue(after_smoke_checks["transport_smoke"]["passed"])
            self.assertEqual(after_smoke_checks["transport_smoke"]["actual"], "passed")
            self.assertTrue(smoke["probe_note_path"].endswith(".vault-meta/release/environment-smoke-probe.md"))
            self.assertIn("probe_nonce", smoke)
            probe_path = workspace / "vault" / smoke["probe_note_path"]
            self.assertIn(smoke["probe_nonce"], probe_path.read_text(encoding="utf-8"))
            month_log = workspace / "vault" / "Projects" / "Demo" / "logs" / f"{datetime.now().strftime('%Y-%m')}.md"
            if month_log.exists():
                self.assertNotIn(smoke["probe_nonce"], month_log.read_text(encoding="utf-8"))

    def test_release_check_does_not_persist_transport_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            transport_path = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "transport.json"
            transport_path.unlink()

            kb.release_check("Demo", "engineering")
            self.assertFalse(transport_path.exists())

    def test_cli_release_smoke_environment_writes_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "release", "smoke", "--project", "Demo", "--level", "environment", check=False)
            self.assertNotEqual(result.returncode, 0)
            payload = self.parse_json(result)
            self.assertFalse(payload["passed"])
            self.assertEqual(payload["release_level"], "environment")

    def test_release_diagnose_environment_returns_actionable_remediation_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            transport_path = workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "transport.json"
            transport_path.unlink()

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"D:\soft\Obsidian\Obsidian.com"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "Command line interface is not enabled")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")):
                diagnosis = kb.release_diagnose("Demo", "environment")

            self.assertEqual(diagnosis["release_level"], "environment")
            self.assertEqual(diagnosis["target_version"], "v0.2-beta")
            self.assertEqual(diagnosis["status"], "blocked")
            self.assertIn("v0.2-beta blocked", diagnosis["summary"])
            self.assertFalse(transport_path.exists())
            self.assertFalse((workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "release" / "environment-smoke.json").exists())
            self.assertFalse((workspace / "vault" / "Projects" / "Demo" / ".vault-meta" / "release" / "environment-smoke-probe.md").exists())
            blocked = {item["name"]: item for item in diagnosis["blocked_checks"]}
            self.assertIn("obsidian_cli_ready", blocked)
            self.assertIn("local_rest_ready", blocked)
            self.assertIn("transport_smoke", blocked)
            self.assertEqual(blocked["obsidian_cli_ready"]["state"], "disabled")
            self.assertEqual(blocked["obsidian_cli_ready"]["expected"], "ready")
            self.assertEqual(blocked["obsidian_cli_ready"]["path"], r"D:\soft\Obsidian\Obsidian.com")
            self.assertEqual(blocked["local_rest_ready"]["state"], "unreachable")
            self.assertEqual(blocked["local_rest_ready"]["url"], "https://127.0.0.1:27124/")
            self.assertEqual(blocked["transport_smoke"]["state"], "missing")
            self.assertTrue(blocked["transport_smoke"]["path"].endswith("environment-smoke.json"))
            self.assertTrue(any("Settings > General > Advanced" in step["action"] for step in diagnosis["remediation"]))
            self.assertTrue(any("Obsidian Local REST API" in step["action"] for step in diagnosis["remediation"]))
            self.assertTrue(all("verify_command" in step for step in diagnosis["remediation"]))
            self.assertIn("python scripts/kb.py release smoke --project Demo --level environment", diagnosis["verification_commands"])
            self.assertIn("python scripts/kb.py release check --project Demo --level environment", diagnosis["verification_commands"])

    def test_release_diagnose_reports_missing_local_rest_plugin_in_open_obsidian_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            live_vault = workspace / "live-vault"
            plugins_dir = live_vault / ".obsidian" / "plugins"
            plugins_dir.mkdir(parents=True)
            (plugins_dir / "opencode-obsidian").mkdir()
            community_plugins = live_vault / ".obsidian" / "community-plugins.json"
            community_plugins.write_text(json.dumps(["opencode-obsidian"], ensure_ascii=False), encoding="utf-8")
            appdata = workspace / "appdata"
            obsidian_app = appdata / "obsidian"
            obsidian_app.mkdir(parents=True)
            (obsidian_app / "obsidian.json").write_text(
                json.dumps(
                    {
                        "vaults": {
                            "demo": {
                                "path": str(live_vault),
                                "open": True,
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with mock.patch.dict(os.environ, {"APPDATA": str(appdata)}), mock.patch.object(
                ProjectKb, "resolve_obsidian_cli_path", return_value=r"D:\soft\Obsidian\Obsidian.com"
            ), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "Command line interface is not enabled")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")):
                diagnosis = kb.release_diagnose("Demo", "environment")

            blocked = {item["name"]: item for item in diagnosis["blocked_checks"]}
            local_rest = blocked["local_rest_ready"]
            self.assertEqual(local_rest["plugin"]["id"], "obsidian-local-rest-api")
            self.assertEqual(Path(local_rest["plugin"]["open_vault"]).resolve(), live_vault.resolve())
            self.assertFalse(local_rest["plugin"]["installed"])
            self.assertFalse(local_rest["plugin"]["enabled"])
            self.assertIn("opencode-obsidian", local_rest["plugin"]["installed_plugins"])
            self.assertTrue(any("current open vault" in step["action"] for step in diagnosis["remediation"]))

    def test_release_diagnose_reports_disabled_local_rest_plugin_in_open_obsidian_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            live_vault = workspace / "live-vault"
            plugins_dir = live_vault / ".obsidian" / "plugins"
            plugins_dir.mkdir(parents=True)
            (plugins_dir / "obsidian-local-rest-api").mkdir()
            community_plugins = live_vault / ".obsidian" / "community-plugins.json"
            community_plugins.write_text(json.dumps(["opencode-obsidian"], ensure_ascii=False), encoding="utf-8")
            appdata = workspace / "appdata"
            obsidian_app = appdata / "obsidian"
            obsidian_app.mkdir(parents=True)
            (obsidian_app / "obsidian.json").write_text(
                json.dumps({"vaults": {"demo": {"path": str(live_vault), "open": True}}}, ensure_ascii=False),
                encoding="utf-8",
            )
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with mock.patch.dict(os.environ, {"APPDATA": str(appdata)}), mock.patch.object(
                ProjectKb, "resolve_obsidian_cli_path", return_value=r"D:\soft\Obsidian\Obsidian.com"
            ), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "Command line interface is not enabled")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")):
                diagnosis = kb.release_diagnose("Demo", "environment")

            blocked = {item["name"]: item for item in diagnosis["blocked_checks"]}
            local_rest = blocked["local_rest_ready"]
            self.assertTrue(local_rest["plugin"]["installed"])
            self.assertFalse(local_rest["plugin"]["enabled"])
            self.assertTrue(any("Enable the Obsidian Local REST API plugin" in step["action"] for step in diagnosis["remediation"]))

    def test_cli_release_diagnose_environment_outputs_json_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "release", "diagnose", "--project", "Demo", "--level", "environment")
            payload = self.parse_json(result)
            self.assertEqual(payload["release_level"], "environment")
            self.assertEqual(payload["target_version"], "v0.2-beta")
            self.assertIn("summary", payload)
            self.assertIn("blocked_checks", payload)
            self.assertIn("remediation", payload)

    def test_release_report_summarizes_cumulative_publish_status_and_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"D:\soft\Obsidian\Obsidian.com"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "Command line interface is not enabled")
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "connection refused")):
                report = kb.release_report("Demo")

            self.assertEqual(report["project"], "Demo")
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["highest_ready_version"], "v0.1-preview")
            self.assertEqual(report["target_version"], "repo-wide-end-user-release")
            self.assertEqual(report["project_kb_status"], "blocked")
            self.assertEqual(report["versions"]["v0.1-preview"]["status"], "ready")
            self.assertEqual(report["versions"]["v0.2-beta"]["status"], "blocked")
            self.assertEqual(report["versions"]["v0.3-pilot"]["status"], "blocked")
            self.assertEqual(report["versions"]["full"]["status"], "blocked")
            self.assertEqual(report["repo_wide"]["status"], "blocked")
            self.assertEqual(report["repo_wide"]["target_release"], "repo-wide-end-user-release")
            self.assertIn("environment", report["blocked_gates"])
            self.assertIn("pilot", report["blocked_gates"])
            self.assertIn("repo-wide", report["blocked_gates"])
            self.assertTrue(any(item["gate"] == "environment" and item["check"] == "obsidian_cli_ready" for item in report["blockers"]))
            self.assertTrue(any(item["gate"] == "repo-wide" and item["check"] == "public_claims_gate" for item in report["blockers"]))
            self.assertTrue(any(item["id"] == "enable_obsidian_cli" for item in report["next_actions"]))
            self.assertTrue(any(item["id"] == "collect_repo_wide_release_evidence" for item in report["next_actions"]))
            repo_wide_actions = {item["id"]: item for item in report["next_actions"] if item["gate"] == "repo-wide"}
            self.assertIn("run_public_claims_smoke", repo_wide_actions)
            self.assertIn("run_clean_install_smoke", repo_wide_actions)
            self.assertIn("run_user_journey_smoke", repo_wide_actions)
            self.assertIn("run_support_matrix_smoke", repo_wide_actions)
            self.assertEqual(
                repo_wide_actions["run_public_claims_smoke"]["verify_command"],
                "python scripts/kb.py release evidence public-claims-smoke --project Demo",
            )
            self.assertEqual(
                repo_wide_actions["run_clean_install_smoke"]["verify_command"],
                "python scripts/kb.py release evidence clean-install-smoke --project Demo",
            )
            self.assertEqual(
                repo_wide_actions["run_user_journey_smoke"]["verify_command"],
                "python scripts/kb.py release evidence user-journey-smoke --project Demo",
            )
            self.assertEqual(
                repo_wide_actions["run_support_matrix_smoke"]["verify_command"],
                "python scripts/kb.py release evidence support-matrix-smoke --project Demo",
            )
            self.assertIn("python scripts/kb.py release check --project Demo --level full", report["verification_commands"])
            self.assertIn("python scripts/kb.py release check --project Demo --level repo-wide", report["verification_commands"])

    def test_release_report_status_stays_blocked_when_repo_wide_gate_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            ready_gate = {"project": "Demo", "status": "ready", "checks": [], "metrics": {"tasks": 10}}
            repo_wide_blocked = {
                "project": "Demo",
                "release_level": "repo-wide",
                "target_release": "repo-wide-end-user-release",
                "status": "blocked",
                "checks": [
                    {
                        "name": "project_kb_full",
                        "passed": True,
                        "required_for": ["repo-wide"],
                        "detail": ready_gate,
                    },
                    {
                        "name": "user_journey_gate",
                        "passed": False,
                        "required_for": ["repo-wide"],
                        "actual": "missing",
                        "detail": {"path": "Projects/Demo/.vault-meta/release/repo-wide/user-journeys.json"},
                    },
                ],
                "metrics": {"tasks": 10},
            }

            def fake_release_check(project, level, commit=None, require_artifacts=False):
                if level == "repo-wide":
                    return repo_wide_blocked
                return dict(ready_gate, release_level=level)

            with mock.patch.object(kb, "release_check", side_effect=fake_release_check), mock.patch.object(
                kb,
                "release_diagnose",
                return_value={"remediation": [], "status": "ready", "blocked_checks": []},
            ):
                report = kb.release_report("Demo")

            self.assertEqual(report["gates"]["full"]["status"], "ready")
            self.assertEqual(report["repo_wide"]["status"], "blocked")
            self.assertEqual(report["status"], "blocked")
            self.assertIn("repo-wide", report["blocked_gates"])

    def test_release_check_repo_wide_requires_project_kb_full_and_end_user_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            result = kb.release_check("Demo", "repo-wide")

            self.assertEqual(result["release_level"], "repo-wide")
            self.assertEqual(result["target_release"], "repo-wide-end-user-release")
            self.assertEqual(result["status"], "blocked")
            checks = {item["name"]: item for item in result["checks"]}
            self.assertIn("project_kb_full", checks)
            self.assertIn("public_claims_gate", checks)
            self.assertIn("clean_install_gate", checks)
            self.assertIn("user_journey_gate", checks)
            self.assertIn("support_matrix_gate", checks)
            self.assertFalse(checks["project_kb_full"]["passed"])
            self.assertFalse(checks["public_claims_gate"]["passed"])
            self.assertIn("docs/project-kb/release-plan-cn.md", checks["public_claims_gate"]["detail"]["evidence_required"])

    def test_release_evidence_record_writes_repo_wide_gate_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            payload = {
                "passed": True,
                "reviewed_files": ["README.md", "docs/project-kb/cli.md"],
                "commands": ["python scripts/kb.py release check --project Demo --level repo-wide"],
            }

            result = kb.release_evidence_record("Demo", "public_claims_gate", payload)

            self.assertEqual(result["gate"], "public_claims_gate")
            self.assertEqual(result["path"], "Projects/Demo/.vault-meta/release/repo-wide/public-claims.json")
            artifact = json.loads((workspace / "vault" / result["path"]).read_text(encoding="utf-8"))
            self.assertTrue(artifact["passed"])
            self.assertEqual(artifact["gate"], "public_claims_gate")
            self.assertIn("recorded_at", artifact)
            repo_wide = kb.release_check("Demo", "repo-wide")
            checks = {item["name"]: item for item in repo_wide["checks"]}
            self.assertTrue(checks["public_claims_gate"]["passed"])
            self.assertFalse(checks["clean_install_gate"]["passed"])

    def test_cli_release_evidence_record_accepts_repo_wide_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            evidence = workspace / "evidence.json"
            evidence.write_text(
                json.dumps({"passed": True, "platform": "Windows", "commands": ["setup.ps1"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = self.run_kb(
                workspace,
                "release",
                "evidence",
                "record",
                "--project",
                "Demo",
                "--gate",
                "clean_install_gate",
                "--from-file",
                str(evidence),
            )

            payload = self.parse_json(result)
            self.assertEqual(payload["gate"], "clean_install_gate")
            self.assertEqual(payload["recorded"], True)
            self.assertEqual(payload["path"], "Projects/Demo/.vault-meta/release/repo-wide/clean-install.json")

    def test_release_public_claims_smoke_requires_readme_release_status_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with mock.patch.object(ProjectKb, "repo_root", return_value=workspace):
                (workspace / "README.md").write_text("# Demo\n\n一键部署\n", encoding="utf-8")
                (workspace / "README.en.md").write_text("# Demo\n\nOne-Click Deploy\n", encoding="utf-8")
                (workspace / "docs" / "project-kb").mkdir(parents=True)
                (workspace / "docs" / "project-kb" / "cli.md").write_text("repo-wide\n", encoding="utf-8")
                (workspace / "docs" / "project-kb" / "release-plan-cn.md").write_text("Public Claims Gate\n", encoding="utf-8")
                result = kb.release_public_claims_smoke("Demo")

            self.assertFalse(result["passed"])
            claims = {item["id"]: item for item in result["evidence"]["claims"]}
            self.assertEqual(claims["release_status_scope"]["status"], "missing")

    def test_release_public_claims_smoke_records_repo_wide_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            result = kb.release_public_claims_smoke("Demo")

            self.assertTrue(result["passed"])
            self.assertEqual(result["gate"], "public_claims_gate")
            self.assertIn("README.md", result["evidence"]["reviewed_files"])
            self.assertIn("README.en.md", result["evidence"]["reviewed_files"])
            claims = {item["id"]: item for item in result["evidence"]["claims"]}
            self.assertEqual(claims["release_status_scope"]["status"], "scoped")
            self.assertEqual(claims["preview_vs_repo_wide"]["status"], "scoped")
            self.assertEqual(claims["live_limitations"]["status"], "limited")
            live_evidence = " ".join(claims["live_limitations"]["evidence"]).lower()
            self.assertIn("obsidian cli", live_evidence)
            self.assertIn("local rest", live_evidence)
            repo_wide = kb.release_check("Demo", "repo-wide")
            checks = {item["name"]: item for item in repo_wide["checks"]}
            self.assertTrue(checks["public_claims_gate"]["passed"])

    def test_cli_release_evidence_public_claims_smoke_records_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "release", "evidence", "public-claims-smoke", "--project", "Demo")

            payload = self.parse_json(result)
            self.assertTrue(payload["passed"])
            self.assertEqual(payload["gate"], "public_claims_gate")
            self.assertEqual(payload["record"]["path"], "Projects/Demo/.vault-meta/release/repo-wide/public-claims.json")

    def test_release_clean_install_smoke_records_repo_wide_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            result = kb.release_clean_install_smoke("Demo")

            self.assertTrue(result["passed"])
            self.assertEqual(result["gate"], "clean_install_gate")
            self.assertEqual(result["evidence"]["passed"], True)
            self.assertIn("AGENTS.md", result["evidence"]["artifacts"])
            self.assertIn(".opencode/skill/obsidian-cli/SKILL.md", result["evidence"]["artifacts"])
            self.assertIn("README.md", result["evidence"]["reviewed_files"])
            self.assertIn("README.en.md", result["evidence"]["reviewed_files"])
            self.assertIn("setup.sh", result["evidence"]["install_scripts"])
            self.assertIn("setup.ps1", result["evidence"]["install_scripts"])
            self.assertEqual(result["evidence"]["missing_install_scripts"], [])
            self.assertEqual(result["evidence"]["invalid_doc_paths"], [])
            repo_wide = kb.release_check("Demo", "repo-wide")
            checks = {item["name"]: item for item in repo_wide["checks"]}
            self.assertTrue(checks["clean_install_gate"]["passed"])

    def test_release_clean_install_smoke_rejects_missing_documented_install_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            (workspace / "vault-template").mkdir()
            (workspace / "README.md").write_text("cd Obsidian-OpenCode-Knowledge/deploy\nbash setup.sh\n", encoding="utf-8")
            (workspace / "README.en.md").write_text("cd Obsidian-OpenCode-Knowledge/deploy\nbash setup.sh\n", encoding="utf-8")
            (workspace / "setup.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (workspace / "setup.ps1").write_text("Write-Host setup\n", encoding="utf-8")

            with mock.patch.object(ProjectKb, "repo_root", return_value=workspace):
                result = kb.release_clean_install_smoke("Demo")

            self.assertFalse(result["passed"])
            self.assertIn("README.md references missing directory: deploy", result["evidence"]["invalid_doc_paths"])

    def test_cli_release_evidence_clean_install_smoke_records_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "release", "evidence", "clean-install-smoke", "--project", "Demo")

            payload = self.parse_json(result)
            self.assertTrue(payload["passed"])
            self.assertEqual(payload["gate"], "clean_install_gate")
            self.assertEqual(payload["record"]["path"], "Projects/Demo/.vault-meta/release/repo-wide/clean-install.json")

    def test_release_user_journey_smoke_records_repo_wide_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            result = kb.release_user_journey_smoke("Demo")

            self.assertTrue(result["passed"])
            self.assertEqual(result["gate"], "user_journey_gate")
            journeys = {item["id"]: item for item in result["evidence"]["journeys"]}
            self.assertEqual(set(journeys.keys()), {"ingest", "query", "lint", "social_ingest"})
            self.assertIn("加到 wiki", journeys["ingest"]["triggers"])
            self.assertIn("wiki/index.md", journeys["query"]["verified_artifacts"])
            self.assertIn("wiki/log.md", journeys["lint"]["verified_artifacts"])
            self.assertIn("raw/social", journeys["social_ingest"]["verified_artifacts"])
            smoke_artifacts = result["evidence"]["smoke_artifacts"]
            self.assertIn("raw/release-smoke/source.md", smoke_artifacts)
            self.assertIn("wiki/release-smoke-note.md", smoke_artifacts)
            self.assertIn("raw/social/release-smoke-social.md", smoke_artifacts)
            self.assertIn("wiki/log.md", smoke_artifacts)
            self.assertEqual(result["evidence"]["smoke_missing"], [])
            repo_wide = kb.release_check("Demo", "repo-wide")
            checks = {item["name"]: item for item in repo_wide["checks"]}
            self.assertTrue(checks["user_journey_gate"]["passed"])

    def test_user_journey_artifact_smoke_reports_missing_raw_social(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            template = workspace / "vault-template"
            shutil.copytree(ROOT / "vault-template", template)
            raw_social = template / "raw" / "social"
            if raw_social.exists():
                shutil.rmtree(raw_social)
            kb = ProjectKb(workspace / "vault")

            result = kb.user_journey_artifact_smoke(template)

            self.assertIn("raw/social", result["smoke_missing"])

    def test_user_journey_artifact_smoke_reports_missing_wiki_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            template = workspace / "vault-template"
            shutil.copytree(ROOT / "vault-template", template)
            (template / "wiki" / "log.md").unlink()
            kb = ProjectKb(workspace / "vault")

            result = kb.user_journey_artifact_smoke(template)

            self.assertIn("wiki/log.md", result["smoke_missing"])

    def test_cli_release_evidence_user_journey_smoke_records_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "release", "evidence", "user-journey-smoke", "--project", "Demo")

            payload = self.parse_json(result)
            self.assertTrue(payload["passed"])
            self.assertEqual(payload["gate"], "user_journey_gate")
            self.assertEqual(payload["record"]["path"], "Projects/Demo/.vault-meta/release/repo-wide/user-journeys.json")

    @unittest.skipUnless(sys.platform == "win32", "Windows support matrix status is only verified on Windows runners")
    def test_release_support_matrix_smoke_records_repo_wide_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))
            kb.install_repo_adapters("Demo", str(repo))
            kb.export_host_configs("Demo")
            kb.export_views("Demo")

            with mock.patch.object(ProjectKb, "probe_obsidian_cli", return_value=(False, "disabled")), mock.patch.object(
                ProjectKb, "resolve_obsidian_cli_path", return_value=r"D:\soft\Obsidian\Obsidian.com"
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "unreachable")):
                result = kb.release_support_matrix_smoke("Demo")

            self.assertTrue(result["passed"])
            self.assertEqual(result["gate"], "support_matrix_gate")
            matrix = result["evidence"]["matrix"]
            self.assertEqual(matrix["hosts"]["Codex"]["status"], "repo-local verified")
            self.assertEqual(matrix["hosts"]["Claude Code"]["status"], "repo-local verified")
            self.assertEqual(matrix["hosts"]["OpenClaw"]["status"], "repo-local verified")
            self.assertEqual(matrix["hosts"]["OpenCode"]["status"], "repo-local verified")
            self.assertEqual(matrix["os"]["Windows"]["status"], "repo-local verified")
            self.assertEqual(matrix["os"]["macOS"]["status"], "draft only")
            self.assertEqual(matrix["transports"]["filesystem"]["status"], "repo-local verified")
            self.assertEqual(matrix["transports"]["Obsidian CLI"]["status"], "blocked")
            self.assertEqual(matrix["transports"]["Obsidian Local REST"]["status"], "blocked")
            self.assertEqual(matrix["obsidian_surfaces"]["Markdown notes"]["status"], "repo-local verified")
            self.assertEqual(matrix["obsidian_surfaces"]["Canvas"]["status"], "repo-local verified")
            self.assertEqual(matrix["obsidian_surfaces"]["Base"]["status"], "repo-local verified")
            self.assertIn(".project-kb/adapters/opencode/OPENCODE.project-kb.md", result["evidence"]["artifacts"])
            with mock.patch.object(ProjectKb, "probe_obsidian_cli", return_value=(False, "disabled")), mock.patch.object(
                ProjectKb, "resolve_obsidian_cli_path", return_value=r"D:\soft\Obsidian\Obsidian.com"
            ), mock.patch.object(ProjectKb, "check_http_endpoint", return_value=(False, "unreachable")):
                repo_wide = kb.release_check("Demo", "repo-wide")
            checks = {item["name"]: item for item in repo_wide["checks"]}
            self.assertTrue(checks["support_matrix_gate"]["passed"])

    def test_cli_release_evidence_support_matrix_smoke_records_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "install-repo-adapters", "--project", "Demo", "--repo", str(repo))
            self.run_kb(workspace, "export-host-configs", "--project", "Demo")
            self.run_kb(workspace, "export-views", "--project", "Demo")

            result = self.run_kb(workspace, "release", "evidence", "support-matrix-smoke", "--project", "Demo")

            payload = self.parse_json(result)
            self.assertTrue(payload["passed"])
            self.assertEqual(payload["gate"], "support_matrix_gate")
            self.assertEqual(payload["record"]["path"], "Projects/Demo/.vault-meta/release/repo-wide/support-matrix.json")

    def test_release_evidence_record_rejects_empty_passed_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            with self.assertRaisesRegex(ValueError, "requires observable evidence"):
                kb.release_evidence_record("Demo", "support_matrix_gate", {"passed": True})

    def test_cli_release_check_accepts_repo_wide_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "release", "check", "--project", "Demo", "--level", "repo-wide", check=False)

            self.assertNotEqual(result.returncode, 0)
            payload = self.parse_json(result)
            self.assertEqual(payload["release_level"], "repo-wide")
            self.assertEqual(payload["target_release"], "repo-wide-end-user-release")
            self.assertEqual(payload["status"], "blocked")

    def test_cli_release_report_outputs_json_and_nonzero_until_full_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            result = self.run_kb(workspace, "release", "report", "--project", "Demo", check=False)
            self.assertNotEqual(result.returncode, 0)
            payload = self.parse_json(result)
            self.assertEqual(payload["project"], "Demo")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("versions", payload)
            self.assertIn("next_actions", payload)

    def test_mcp_exposes_release_check_as_readonly_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            vault = workspace / "vault"
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "kb.release_check",
                        "arguments": {"vault": str(vault), "project": "Demo", "level": "engineering"},
                    },
                },
            ]
            proc = subprocess.run(
                [sys.executable, str(KB_MCP)],
                cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses = [json.loads(line) for line in proc.stdout.splitlines()]
            tool_names = {tool["name"] for tool in responses[0]["result"]["tools"]}
            self.assertIn("kb.release_check", tool_names)
            payload = json.loads(responses[1]["result"]["content"][0]["text"])
            self.assertEqual(payload["release_level"], "engineering")
            self.assertEqual(payload["status"], "ready")
            self.assertFalse((vault / "Projects" / "Demo" / ".vault-meta" / "pilot" / "metrics.json").exists())

    def test_read_prefers_obsidian_cli_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            cli_payload = {
                "content": "# Demo\n\n## Purpose\n\nLoaded through obsidian CLI.\n",
                "frontmatter": index_note.frontmatter,
            }
            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(
                ProjectKb, "obsidian_cli_read", return_value=cli_payload
            ) as obsidian_read:
                result = kb.read("Projects/Demo/_index.md")

            obsidian_read.assert_called_once_with("Demo", "Projects/Demo/_index.md")
            self.assertEqual(result["path"], "Projects/Demo/_index.md")
            self.assertIn("Loaded through obsidian CLI.", result["content"])

    def test_read_falls_back_to_filesystem_when_obsidian_cli_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=""), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "obsidian executable not found")
            ), mock.patch.object(
                ProjectKb, "obsidian_cli_read"
            ) as obsidian_read:
                result = kb.read("Projects/Demo/_index.md")

            obsidian_read.assert_not_called()
            self.assertEqual(result["path"], "Projects/Demo/_index.md")
            self.assertIn("# Demo", result["content"])

    def test_search_prefers_obsidian_cli_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            cli_results = {
                "results": [
                    {
                        "path": "Projects/Demo/_index.md",
                        "title": "Demo",
                        "type": "project",
                        "score": 1.0,
                        "snippet": "Loaded through obsidian CLI search.",
                    }
                ]
            }
            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "obsidian_cli_search", return_value=cli_results) as cli_search:
                result = kb.search("Demo", "demo", limit=5)

            cli_search.assert_called_once_with("Demo", "demo", 5, None)
            self.assertEqual(result, cli_results)

    def test_search_falls_back_to_filesystem_when_obsidian_cli_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=""), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "obsidian executable not found")
            ), mock.patch.object(ProjectKb, "obsidian_cli_search") as cli_search:
                result = kb.search("Demo", "project", limit=5)

            cli_search.assert_not_called()
            self.assertTrue(any(item["path"] == "Projects/Demo/_index.md" for item in result["results"]))

    def test_append_log_prefers_obsidian_cli_when_enabled_and_available_for_existing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            month = datetime.now().strftime("%Y-%m")
            log_path = root / "logs" / f"{month}.md"
            log_path.write_text(kb.log_note("Demo", month), encoding="utf-8")

            payload = {
                "title": "CLI append",
                "summary": "Appended through obsidian CLI.",
                "files": ["project_kb/core.py"],
                "commands": ["python -m unittest"],
                "result": "passed",
            }
            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "obsidian_cli_append") as cli_append:
                result = kb.append_log("Demo", payload)

            cli_append.assert_called_once()
            self.assertEqual(result["path"], f"Projects/Demo/logs/{month}.md")
            audit_path = root / ".vault-meta" / "audit.jsonl"
            self.assertTrue(audit_path.exists())

    def test_append_log_falls_back_to_filesystem_when_obsidian_cli_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            payload = {
                "title": "Filesystem append fallback",
                "summary": "Appended through filesystem fallback.",
                "files": ["project_kb/core.py"],
                "commands": ["python -m unittest"],
                "result": "passed",
            }
            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=""), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "obsidian executable not found")
            ), mock.patch.object(ProjectKb, "obsidian_cli_append") as cli_append:
                result = kb.append_log("Demo", payload)

            cli_append.assert_not_called()
            month = datetime.now().strftime("%Y-%m")
            log_path = root / "logs" / f"{month}.md"
            self.assertEqual(result["path"], f"Projects/Demo/logs/{month}.md")
            self.assertIn("Filesystem append fallback", log_path.read_text(encoding="utf-8"))

    def test_append_log_creates_new_monthly_log_via_obsidian_cli_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            payload = {
                "title": "CLI create monthly log",
                "summary": "Created through obsidian CLI.",
                "files": ["project_kb/core.py"],
                "commands": ["python -m unittest"],
                "result": "passed",
            }
            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "obsidian_cli_create_note") as cli_create:
                result = kb.append_log("Demo", payload)

            cli_create.assert_called_once()
            self.assertTrue(result["appended"])

    def test_append_log_creates_new_monthly_log_via_obsidian_rest_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "mcp_obsidian"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            payload = {
                "title": "REST create monthly log",
                "summary": "Created through obsidian REST.",
                "files": ["project_kb/core.py"],
                "commands": ["python -m unittest"],
                "result": "passed",
            }
            with mock.patch.object(ProjectKb, "obsidian_rest_enabled", return_value=True), mock.patch.object(
                ProjectKb, "obsidian_rest_create_note"
            ) as rest_create:
                result = kb.append_log("Demo", payload)

            rest_create.assert_called_once()
            self.assertTrue(result["appended"])

    def test_update_frontmatter_prefers_obsidian_cli_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "obsidian_cli_property_set") as cli_set:
                result = kb.update_project_status("Demo", "paused")

            cli_set.assert_called_once_with("Demo", "Projects/Demo/_index.md", "status", "paused", "text")
            self.assertEqual(result["status"], "paused")

    def test_update_frontmatter_falls_back_to_filesystem_when_obsidian_cli_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=""), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "obsidian executable not found")
            ), mock.patch.object(ProjectKb, "obsidian_cli_property_set") as cli_set:
                result = kb.update_project_status("Demo", "paused")

            cli_set.assert_not_called()
            self.assertEqual(result["status"], "paused")
            updated = kb.read_note(index_path)
            self.assertEqual(updated.frontmatter["status"], "paused")

    def test_create_decision_prefers_obsidian_cli_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "example.ts").write_text("export const demo = true;\n", encoding="utf-8")
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=r"C:\Program Files\Obsidian\obsidian.exe"), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(True, "obsidian help succeeded")
            ), mock.patch.object(ProjectKb, "obsidian_cli_create_note") as cli_create:
                result = kb.create_decision("Demo", "Use safe facade", source_paths=["src/example.ts"], commit="abc123")

            cli_create.assert_called_once()
            self.assertTrue(result["created"])
            self.assertTrue(result["path"].startswith("Projects/Demo/decisions/ADR-"))

    def test_create_decision_falls_back_to_filesystem_when_obsidian_cli_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "example.ts").write_text("export const demo = true;\n", encoding="utf-8")
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "cli"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "resolve_obsidian_cli_path", return_value=""), mock.patch.object(
                ProjectKb, "probe_obsidian_cli", return_value=(False, "obsidian executable not found")
            ), mock.patch.object(ProjectKb, "obsidian_cli_create_note") as cli_create:
                result = kb.create_decision("Demo", "Use safe facade", source_paths=["src/example.ts"], commit="abc123")

            cli_create.assert_not_called()
            self.assertTrue(result["created"])
            self.assertTrue((workspace / "vault" / result["path"]).exists())

    def test_read_prefers_obsidian_rest_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "mcp_obsidian"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            rest_payload = {
                "content": "# Demo\n\n## Purpose\n\nLoaded through obsidian REST.\n",
                "frontmatter": index_note.frontmatter,
            }
            with mock.patch.object(ProjectKb, "obsidian_rest_enabled", return_value=True), mock.patch.object(
                ProjectKb, "obsidian_rest_read", return_value=rest_payload
            ) as rest_read:
                result = kb.read("Projects/Demo/_index.md")

            rest_read.assert_called_once_with("Projects/Demo/_index.md", None)
            self.assertIn("Loaded through obsidian REST.", result["content"])

    def test_search_prefers_obsidian_rest_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "mcp_obsidian"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            rest_results = {"results": [{"path": "Projects/Demo/_index.md", "title": "Demo", "type": "project", "score": 1.0, "snippet": "REST search"}]}
            with mock.patch.object(ProjectKb, "obsidian_rest_enabled", return_value=True), mock.patch.object(
                ProjectKb, "obsidian_rest_search", return_value=rest_results
            ) as rest_search:
                result = kb.search("Demo", "demo", limit=5)

            rest_search.assert_called_once_with("demo", 5)
            self.assertEqual(result, rest_results)

    def test_update_frontmatter_prefers_obsidian_rest_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "mcp_obsidian"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "obsidian_rest_enabled", return_value=True), mock.patch.object(
                ProjectKb, "obsidian_rest_patch_frontmatter"
            ) as rest_patch:
                result = kb.update_project_status("Demo", "paused")

            rest_patch.assert_called_once_with("Projects/Demo/_index.md", "status", "paused")
            self.assertEqual(result["status"], "paused")

    def test_append_log_prefers_obsidian_rest_when_enabled_and_available_for_existing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "mcp_obsidian"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            month = datetime.now().strftime("%Y-%m")
            log_path = root / "logs" / f"{month}.md"
            log_path.write_text(kb.log_note("Demo", month), encoding="utf-8")

            payload = {
                "title": "REST append",
                "summary": "Appended through obsidian REST.",
                "files": ["project_kb/core.py"],
                "commands": ["python -m unittest"],
                "result": "passed",
            }
            with mock.patch.object(ProjectKb, "obsidian_rest_enabled", return_value=True), mock.patch.object(
                ProjectKb, "obsidian_rest_append"
            ) as rest_append:
                result = kb.append_log("Demo", payload)

            rest_append.assert_called_once()
            self.assertEqual(result["path"], f"Projects/Demo/logs/{month}.md")

    def test_create_decision_prefers_obsidian_rest_when_enabled_and_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "example.ts").write_text("export const demo = true;\n", encoding="utf-8")
            kb = ProjectKb(workspace / "vault")
            kb.init_project("Demo", str(repo))

            root = workspace / "vault" / "Projects" / "Demo"
            index_path = root / "_index.md"
            index_note = kb.read_note(index_path)
            index_note.frontmatter["transport"] = "mcp_obsidian"
            index_path.write_text(make_note(index_note.frontmatter, index_note.body), encoding="utf-8")

            with mock.patch.object(ProjectKb, "obsidian_rest_enabled", return_value=True), mock.patch.object(
                ProjectKb, "obsidian_rest_create_note"
            ) as rest_create:
                result = kb.create_decision("Demo", "Use safe facade", source_paths=["src/example.ts"], commit="abc123")

            rest_create.assert_called_once()
            self.assertTrue(result["created"])

    def test_obsidian_rest_read_requests_note_json_for_full_note(self):
        kb = ProjectKb("H:/vault")
        payload = {
            "path": "Projects/Demo/_index.md",
            "content": "# Demo",
            "frontmatter": {"type": "project"},
            "tags": [],
            "links": [],
            "backlinks": [],
            "stat": {"ctime": 0, "mtime": 0, "size": 1},
        }

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with mock.patch("project_kb.core.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with mock.patch.dict(os.environ, {"PROJECT_KB_OBSIDIAN_REST_URL": "http://127.0.0.1:27123", "PROJECT_KB_OBSIDIAN_REST_API_KEY": "test-key"}):
                result = kb.obsidian_rest_read("Projects/Demo/_index.md")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:27123/vault/Projects/Demo/_index.md")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(request.get_header("Accept"), "application/vnd.olrapi.note+json")
        self.assertEqual(result["content"], "# Demo")
        self.assertEqual(result["frontmatter"]["type"], "project")

    def test_obsidian_rest_endpoint_treats_authenticated_401_as_reachable(self):
        kb = ProjectKb("H:/vault")
        error = urllib.error.HTTPError(
            "https://127.0.0.1:27124/",
            401,
            "Unauthorized",
            {},
            None,
        )

        with mock.patch("project_kb.core.urllib.request.urlopen", side_effect=error) as urlopen:
            with mock.patch.dict(
                os.environ,
                {
                    "PROJECT_KB_OBSIDIAN_REST_URL": "https://127.0.0.1:27124/",
                    "PROJECT_KB_OBSIDIAN_REST_API_KEY": "test-key",
                },
            ):
                available, reason = kb.check_http_endpoint("https://127.0.0.1:27124/")

        request = urlopen.call_args.args[0]
        self.assertTrue(available)
        self.assertEqual(reason, "HTTP 401")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertIn("context", urlopen.call_args.kwargs)

    def test_obsidian_rest_https_only_disables_verification_for_loopback(self):
        kb = ProjectKb("H:/vault")

        self.assertIsNotNone(kb.obsidian_rest_ssl_context("https://127.0.0.1:27124/"))
        self.assertIsNotNone(kb.obsidian_rest_ssl_context("https://localhost:27124/"))
        self.assertIsNone(kb.obsidian_rest_ssl_context("https://example.com/"))
        self.assertIsNone(kb.obsidian_rest_ssl_context("http://127.0.0.1:27123/"))

    def test_obsidian_cli_commands_use_resolved_executable_and_vault_name(self):
        kb = ProjectKb("H:/vault-root")
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        with mock.patch.object(
            ProjectKb,
            "resolve_obsidian_cli_path",
            return_value=r"D:\soft\Obsidian\Obsidian.com",
        ), mock.patch("project_kb.core.subprocess.run", return_value=completed) as run:
            kb.obsidian_cli_append("Demo", "Projects/Demo/logs/2026-06.md", "entry")

        command = run.call_args.args[0]
        self.assertEqual(command[0], r"D:\soft\Obsidian\Obsidian.com")
        self.assertEqual(command[1], "vault=vault-root")
        self.assertNotIn("vault=Demo", command)

    def test_obsidian_cli_property_set_uses_documented_type_parameter(self):
        kb = ProjectKb("H:/vault-root")
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        with mock.patch.object(
            ProjectKb,
            "resolve_obsidian_cli_path",
            return_value=r"D:\soft\Obsidian\Obsidian.com",
        ), mock.patch("project_kb.core.subprocess.run", return_value=completed) as run:
            kb.obsidian_cli_property_set("Demo", "Projects/Demo/_index.md", "status", "paused")

        command = run.call_args.args[0]
        self.assertIn("type=text", command)
        self.assertNotIn("text", command)

    def test_obsidian_rest_search_uses_simple_search_endpoint(self):
        kb = ProjectKb("H:/vault")
        payload = [
            {
                "filename": "Projects/Demo/_index.md",
                "score": 1.0,
                "matches": [{"context": "Demo context", "match": {"start": 0, "end": 4}}],
            }
        ]

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with mock.patch("project_kb.core.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with mock.patch.dict(os.environ, {"PROJECT_KB_OBSIDIAN_REST_URL": "http://127.0.0.1:27123", "PROJECT_KB_OBSIDIAN_REST_API_KEY": "test-key"}):
                result = kb.obsidian_rest_search("demo", 5)

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:27123/search/simple/?query=demo&contextLength=100",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(result["results"][0]["path"], "Projects/Demo/_index.md")
        self.assertEqual(result["results"][0]["snippet"], "Demo context")

    def test_obsidian_rest_patch_frontmatter_uses_patch_headers(self):
        kb = ProjectKb("H:/vault")

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b""

        with mock.patch("project_kb.core.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with mock.patch.dict(os.environ, {"PROJECT_KB_OBSIDIAN_REST_URL": "http://127.0.0.1:27123", "PROJECT_KB_OBSIDIAN_REST_API_KEY": "test-key"}):
                kb.obsidian_rest_patch_frontmatter("Projects/Demo/_index.md", "status", "paused")

        request = urlopen.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(request.full_url, "http://127.0.0.1:27123/vault/Projects/Demo/_index.md")
        self.assertEqual(request.get_method(), "PATCH")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(headers["target-type"], "frontmatter")
        self.assertEqual(headers["target"], "status")
        self.assertEqual(headers["operation"], "replace")
        self.assertEqual(headers["create-target-if-missing"], "true")
        self.assertEqual(request.data.decode("utf-8"), json.dumps("paused"))

    def test_obsidian_rest_append_uses_post_vault_endpoint(self):
        kb = ProjectKb("H:/vault")

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b""

        with mock.patch("project_kb.core.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with mock.patch.dict(os.environ, {"PROJECT_KB_OBSIDIAN_REST_URL": "http://127.0.0.1:27123", "PROJECT_KB_OBSIDIAN_REST_API_KEY": "test-key"}):
                kb.obsidian_rest_append("Projects/Demo/logs/2026-06.md", "\n\n## Entry")

        request = urlopen.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(request.full_url, "http://127.0.0.1:27123/vault/Projects/Demo/logs/2026-06.md")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(headers["content-type"], "text/markdown")
        self.assertEqual(request.data.decode("utf-8"), "\n\n## Entry")

    def test_obsidian_rest_create_note_uses_put_vault_endpoint(self):
        kb = ProjectKb("H:/vault")

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b""

        with mock.patch("project_kb.core.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with mock.patch.dict(os.environ, {"PROJECT_KB_OBSIDIAN_REST_URL": "http://127.0.0.1:27123", "PROJECT_KB_OBSIDIAN_REST_API_KEY": "test-key"}):
                kb.obsidian_rest_create_note("Projects/Demo/decisions/ADR-0002-safe-facade.md", "# ADR\n\n## Context\n")

        request = urlopen.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(request.full_url, "http://127.0.0.1:27123/vault/Projects/Demo/decisions/ADR-0002-safe-facade.md")
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(headers["content-type"], "text/markdown")
        self.assertEqual(request.data.decode("utf-8"), "# ADR\n\n## Context\n")

    def test_export_host_configs_writes_shared_mcp_manifest_and_host_snippets(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            exported = self.parse_json(self.run_kb(workspace, "export-host-configs", "--project", "Demo"))
            expected = {
                "Projects/Demo/.vault-meta/host-configs/mcp-server.json",
                "Projects/Demo/.vault-meta/host-configs/codex.md",
                "Projects/Demo/.vault-meta/host-configs/claude.md",
                "Projects/Demo/.vault-meta/host-configs/openclaw.md",
                "Projects/Demo/.vault-meta/host-configs/opencode.md",
                "Projects/Demo/.vault-meta/host-configs/generic.md",
            }
            self.assertEqual(set(exported["files"]), expected)

            manifest = json.loads((workspace / "vault" / "Projects/Demo/.vault-meta/host-configs/mcp-server.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["server"]["name"], "project-kb")
            self.assertTrue(manifest["server"]["command"].endswith("python"))
            self.assertTrue(manifest["server"]["args"][0].endswith("scripts/kb_mcp.py"))
            self.assertEqual(manifest["env"]["PROJECT_KB_VAULT"], str((workspace / "vault").resolve()))
            self.assertEqual(manifest["env"]["PROJECT_KB_PROJECT"], "Demo")

            codex_snippet = (workspace / "vault" / "Projects/Demo/.vault-meta/host-configs/codex.md").read_text(encoding="utf-8")
            self.assertIn("project-kb", codex_snippet)
            self.assertIn("scripts/kb_mcp.py", codex_snippet)
            self.assertIn("verify against the current host documentation", codex_snippet)
            opencode_snippet = (workspace / "vault" / "Projects/Demo/.vault-meta/host-configs/opencode.md").read_text(encoding="utf-8")
            self.assertIn("project-kb", opencode_snippet)
            self.assertIn("scripts/kb_mcp.py", opencode_snippet)
            self.assertIn("verify against the current host documentation", opencode_snippet)

    def test_export_views_writes_obsidian_canvas_and_base_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            repo = workspace / "repo"
            repo.mkdir()
            self.run_kb(workspace, "init-project", "--name", "Demo", "--repo", str(repo))

            exported = self.parse_json(self.run_kb(workspace, "export-views", "--project", "Demo"))
            expected = {
                "Projects/Demo/views/project-map.canvas",
                "Projects/Demo/views/project-notes.base",
            }
            self.assertEqual(set(exported["files"]), expected)

            canvas_path = workspace / "vault" / "Projects" / "Demo" / "views" / "project-map.canvas"
            canvas = json.loads(canvas_path.read_text(encoding="utf-8"))
            self.assertIn("nodes", canvas)
            self.assertIn("edges", canvas)
            self.assertTrue(any(node["type"] == "file" and node["file"] == "Projects/Demo/_index.md" for node in canvas["nodes"]))
            self.assertTrue(any(node["type"] == "file" and node["file"].endswith("modules/example.md") for node in canvas["nodes"]))
            self.assertTrue(any(node["type"] == "file" and node["file"].endswith("tasks/example-task.md") for node in canvas["nodes"]))
            self.assertTrue(any(edge["fromNode"] == "project-index" for edge in canvas["edges"]))

            base_path = workspace / "vault" / "Projects" / "Demo" / "views" / "project-notes.base"
            base_text = base_path.read_text(encoding="utf-8")
            self.assertIn('file.inFolder("Projects/Demo")', base_text)
            self.assertIn('not file.inFolder("Projects/Demo/.vault-meta")', base_text)
            self.assertIn("type: table", base_text)
            self.assertIn("type: cards", base_text)
            self.assertIn("Project notes", base_text)


if __name__ == "__main__":
    unittest.main()
