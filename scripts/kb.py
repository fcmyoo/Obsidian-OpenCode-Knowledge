#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_kb import ProjectKb  # noqa: E402


def emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def load_payload(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {"title": Path(path).stem, "summary": text}
    if not isinstance(data, dict):
        raise ValueError("--from-file must contain a JSON object or Markdown text")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kb",
        description="Project KB CLI for filesystem-backed Obsidian vaults.",
    )
    parser.add_argument("--vault", help="Vault root. Defaults to PROJECT_KB_VAULT or ./vault.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-project", help="Create a project knowledge layout.")
    init.add_argument("--name", required=True)
    init.add_argument("--repo", required=True)

    find = sub.add_parser("project-find", help="Resolve a project by repo path or name.")
    find.add_argument("--repo")
    find.add_argument("--project")

    validate = sub.add_parser("validate", help="Validate a project knowledge layout.")
    validate.add_argument("--project", required=True)

    doctor = sub.add_parser("doctor", help="Run Project KB environment and safety checks.")
    doctor.add_argument("--project", required=True)

    status = sub.add_parser("status", help="Summarize a project knowledge layout.")
    status.add_argument("--project", required=True)

    transport = sub.add_parser("transport", help="Transport maintenance commands.")
    transport_sub = transport.add_subparsers(dest="transport_command", required=True)
    detect = transport_sub.add_parser("detect", help="Detect available transports.")
    detect.add_argument("--project", required=True)

    search = sub.add_parser("search", help="Search project notes with bounded results.")
    search.add_argument("--project", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--type", dest="types", action="append", help="Filter by note type. Repeatable.")

    read = sub.add_parser("read", help="Read a note or a note section.")
    read.add_argument("--path", required=True)
    read.add_argument("--section")

    append = sub.add_parser("append-log", help="Append a verified task log entry.")
    append.add_argument("--project", required=True)
    append.add_argument("--from-file", required=True)
    append.add_argument("--actor", default="cli")

    stale = sub.add_parser("stale", help="Report notes whose verification commit is missing or old.")
    stale.add_argument("--project", required=True)
    stale.add_argument("--commit", required=True)

    create_decision = sub.add_parser("create-decision", help="Create an ADR with provenance.")
    create_decision.add_argument("--project", required=True)
    create_decision.add_argument("--title", required=True)
    create_decision.add_argument("--status", default="proposed")
    create_decision.add_argument("--source-path", dest="source_paths", action="append", default=[])
    create_decision.add_argument("--verification-command")
    create_decision.add_argument("--commit")
    create_decision.add_argument("--context")
    create_decision.add_argument("--decision")

    update_status = sub.add_parser("update-project-status", help="Update the project status field.")
    update_status.add_argument("--project", required=True)
    update_status.add_argument("--status", required=True)

    update_field = sub.add_parser("update-frontmatter-field", help="Update one allowed frontmatter field.")
    update_field.add_argument("--path", required=True)
    update_field.add_argument("--field", required=True)
    update_field.add_argument("--value", required=True)

    index = sub.add_parser("index", help="Build a simple local note index.")
    index.add_argument("--project", required=True)

    retrieve = sub.add_parser("retrieve", help="Search and read bounded notes.")
    retrieve.add_argument("--project", required=True)
    retrieve.add_argument("--query", required=True)
    retrieve.add_argument("--limit", type=int, default=5)

    lock = sub.add_parser("lock", help="Lock maintenance commands.")
    lock_sub = lock.add_subparsers(dest="lock_command", required=True)
    lock_list = lock_sub.add_parser("list", help="List active locks.")
    lock_list.add_argument("--project", required=True)

    export_adapter = sub.add_parser("export-adapter", help="Export thin agent adapter guidance.")
    export_adapter.add_argument("--agent", required=True, choices=["codex", "claude", "openclaw", "opencode", "generic"])
    export_adapter.add_argument("--project", required=True)

    pilot = sub.add_parser("pilot", help="Pilot task event commands.")
    pilot_sub = pilot.add_subparsers(dest="pilot_command", required=True)
    pilot_plan = pilot_sub.add_parser("plan", help="Write a 10-task pilot plan template.")
    pilot_plan.add_argument("--project", required=True)
    pilot_record = pilot_sub.add_parser("record", help="Record one pilot task metrics event.")
    pilot_record.add_argument("--project", required=True)
    pilot_record.add_argument("--from-file", required=True)
    pilot_status = pilot_sub.add_parser("status", help="Summarize pilot plan and recorded task progress.")
    pilot_status.add_argument("--project", required=True)

    metrics = sub.add_parser("metrics", help="Summarize pilot and retrieval metrics.")
    metrics.add_argument("--project", required=True)

    release = sub.add_parser("release", help="Release gate commands.")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    release_check = release_sub.add_parser("check", help="Check release readiness gates.")
    release_check.add_argument("--project", required=True)
    release_check.add_argument("--level", choices=["engineering", "environment", "pilot", "full", "repo-wide"], default="engineering")
    release_check.add_argument("--commit", help="Require tracked notes to match this commit.")
    release_check.add_argument("--require-artifacts", action="store_true", help="Require repo and vault release artifacts.")
    release_smoke = release_sub.add_parser("smoke", help="Run release readiness smoke checks.")
    release_smoke.add_argument("--project", required=True)
    release_smoke.add_argument("--level", choices=["environment"], default="environment")
    release_diagnose = release_sub.add_parser("diagnose", help="Explain blocked release gates with remediation steps.")
    release_diagnose.add_argument("--project", required=True)
    release_diagnose.add_argument("--level", choices=["environment"], default="environment")
    release_evidence = release_sub.add_parser("evidence", help="Repo-wide release evidence commands.")
    release_evidence_sub = release_evidence.add_subparsers(dest="release_evidence_command", required=True)
    release_evidence_record = release_evidence_sub.add_parser("record", help="Record one repo-wide release evidence artifact.")
    release_evidence_record.add_argument("--project", required=True)
    release_evidence_record.add_argument(
        "--gate",
        required=True,
        choices=["public_claims_gate", "clean_install_gate", "user_journey_gate", "support_matrix_gate"],
    )
    release_evidence_record.add_argument("--from-file", required=True)
    release_public_claims_smoke = release_evidence_sub.add_parser(
        "public-claims-smoke",
        help="Verify public README claims are scoped to current release evidence.",
    )
    release_public_claims_smoke.add_argument("--project", required=True)
    release_clean_install_smoke = release_evidence_sub.add_parser(
        "clean-install-smoke",
        help="Dry-run vault-template install and record clean install evidence.",
    )
    release_clean_install_smoke.add_argument("--project", required=True)
    release_user_journey_smoke = release_evidence_sub.add_parser(
        "user-journey-smoke",
        help="Verify published template user journeys and record evidence.",
    )
    release_user_journey_smoke.add_argument("--project", required=True)
    release_support_matrix_smoke = release_evidence_sub.add_parser(
        "support-matrix-smoke",
        help="Verify repo-wide support matrix artifacts and record evidence.",
    )
    release_support_matrix_smoke.add_argument("--project", required=True)
    release_report = release_sub.add_parser("report", help="Summarize cumulative release readiness and next actions.")
    release_report.add_argument("--project", required=True)
    release_report.add_argument("--commit", help="Require tracked notes to match this commit for engineering.")
    release_report.add_argument("--require-artifacts", action="store_true", help="Require repo and vault release artifacts for engineering.")

    install_repo_adapters = sub.add_parser("install-repo-adapters", help="Write repo-local .project-kb adapter files.")
    install_repo_adapters.add_argument("--project", required=True)
    install_repo_adapters.add_argument("--repo", required=True)

    export_host_configs = sub.add_parser("export-host-configs", help="Export auditable MCP host config snippets.")
    export_host_configs.add_argument("--project", required=True)

    export_views = sub.add_parser("export-views", help="Export Obsidian Canvas/Base project views.")
    export_views.add_argument("--project", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    kb = ProjectKb(args.vault)
    try:
        if args.command == "init-project":
            emit(kb.init_project(args.name, args.repo))
        elif args.command == "project-find":
            emit(kb.project_find(repo_path=args.repo, project=args.project))
        elif args.command == "validate":
            result = kb.validate(args.project)
            emit(result)
            return 1 if result["errors"] else 0
        elif args.command == "doctor":
            result = kb.doctor(args.project)
            emit(result)
            return 0 if result["status"] == "ready" else 1
        elif args.command == "status":
            emit(kb.status(args.project))
        elif args.command == "transport" and args.transport_command == "detect":
            emit(kb.transport_detect(args.project))
        elif args.command == "search":
            emit(kb.search(args.project, args.query, args.limit, args.types))
        elif args.command == "read":
            emit(kb.read(args.path, args.section))
        elif args.command == "append-log":
            emit(kb.append_log(args.project, load_payload(args.from_file), actor=args.actor))
        elif args.command == "stale":
            emit(kb.stale(args.project, args.commit))
        elif args.command == "create-decision":
            emit(
                kb.create_decision(
                    args.project,
                    args.title,
                    status=args.status,
                    source_paths=args.source_paths,
                    verification_command=args.verification_command,
                    commit=args.commit,
                    context=args.context,
                    decision=args.decision,
                )
            )
        elif args.command == "update-project-status":
            emit(kb.update_project_status(args.project, args.status))
        elif args.command == "update-frontmatter-field":
            emit(kb.update_frontmatter_field(args.path, args.field, args.value))
        elif args.command == "index":
            emit(kb.build_index(args.project))
        elif args.command == "retrieve":
            emit(kb.retrieve(args.project, args.query, args.limit))
        elif args.command == "lock" and args.lock_command == "list":
            emit(kb.lock_list(args.project))
        elif args.command == "export-adapter":
            emit(kb.export_adapter(args.agent, args.project))
        elif args.command == "pilot" and args.pilot_command == "plan":
            emit(kb.pilot_plan(args.project))
        elif args.command == "pilot" and args.pilot_command == "record":
            emit(kb.pilot_record(args.project, load_payload(args.from_file)))
        elif args.command == "pilot" and args.pilot_command == "status":
            emit(kb.pilot_status(args.project))
        elif args.command == "metrics":
            emit(kb.metrics(args.project))
        elif args.command == "release" and args.release_command == "check":
            result = kb.release_check(args.project, args.level, commit=args.commit, require_artifacts=args.require_artifacts)
            emit(result)
            return 0 if result["status"] == "ready" else 1
        elif args.command == "release" and args.release_command == "smoke":
            result = kb.release_smoke(args.project, args.level)
            emit(result)
            return 0 if result["passed"] else 1
        elif args.command == "release" and args.release_command == "diagnose":
            emit(kb.release_diagnose(args.project, args.level))
        elif args.command == "release" and args.release_command == "evidence" and args.release_evidence_command == "record":
            emit(kb.release_evidence_record(args.project, args.gate, load_payload(args.from_file)))
        elif args.command == "release" and args.release_command == "evidence" and args.release_evidence_command == "public-claims-smoke":
            result = kb.release_public_claims_smoke(args.project)
            emit(result)
            return 0 if result["passed"] else 1
        elif args.command == "release" and args.release_command == "evidence" and args.release_evidence_command == "clean-install-smoke":
            result = kb.release_clean_install_smoke(args.project)
            emit(result)
            return 0 if result["passed"] else 1
        elif args.command == "release" and args.release_command == "evidence" and args.release_evidence_command == "user-journey-smoke":
            result = kb.release_user_journey_smoke(args.project)
            emit(result)
            return 0 if result["passed"] else 1
        elif args.command == "release" and args.release_command == "evidence" and args.release_evidence_command == "support-matrix-smoke":
            result = kb.release_support_matrix_smoke(args.project)
            emit(result)
            return 0 if result["passed"] else 1
        elif args.command == "release" and args.release_command == "report":
            result = kb.release_report(args.project, commit=args.commit, require_artifacts=args.require_artifacts)
            emit(result)
            return 0 if result["status"] == "ready" else 1
        elif args.command == "install-repo-adapters":
            emit(kb.install_repo_adapters(args.project, args.repo))
        elif args.command == "export-host-configs":
            emit(kb.export_host_configs(args.project))
        elif args.command == "export-views":
            emit(kb.export_views(args.project))
        else:
            parser.error("unsupported command")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
