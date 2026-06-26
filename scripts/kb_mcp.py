#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_kb import ProjectKb  # noqa: E402


PROTOCOL_VERSION = "2025-06-18"


TOOLS: dict[str, dict[str, Any]] = {
    "kb.project_find": {
        "description": "Resolve a project knowledge root by repo path or project name.",
        "inputSchema": {
            "type": "object",
            "properties": {"repo_path": {"type": "string"}, "project": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "kb.search": {
        "description": "Search project notes with bounded results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                "filters": {
                    "type": "object",
                    "properties": {"types": {"type": "array", "items": {"type": "string"}}},
                    "additionalProperties": False,
                },
            },
            "required": ["project", "query"],
            "additionalProperties": False,
        },
    },
    "kb.retrieve": {
        "description": "Retrieve bounded BM25-ranked contextual chunks for a project query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["project", "query"],
            "additionalProperties": False,
        },
    },
    "kb.read": {
        "description": "Read a note or a named note section.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "section": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "kb.append_log": {
        "description": "Append a verified task log entry with lock and audit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
                "commands": {"type": "array", "items": {"type": "string"}},
                "source_paths": {"type": "array", "items": {"type": "string"}},
                "url": {"type": "string"},
                "urls": {"type": "array", "items": {"type": "string"}},
                "result": {"type": "string"},
                "commit": {"type": "string"},
                "repo": {"type": "string"},
                "branch": {"type": "string"},
                "follow_ups": {"type": "string"},
            },
            "required": ["project", "title", "summary", "result"],
            "anyOf": [
                {"required": ["commit"]},
                {"required": ["commands"]},
                {"required": ["files"]},
                {"required": ["source_paths"]},
                {"required": ["url"]},
                {"required": ["urls"]},
                {"required": ["repo"]},
            ],
            "additionalProperties": True,
        },
    },
    "kb.check_staleness": {
        "description": "Report notes whose verification commit is missing or differs.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}, "current_commit": {"type": "string"}},
            "required": ["project", "current_commit"],
            "additionalProperties": False,
        },
    },
    "kb.project_create": {
        "description": "Create a project knowledge layout from templates.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "repo": {"type": "string"}, "vault": {"type": "string"}},
            "required": ["name", "repo"],
            "additionalProperties": False,
        },
    },
    "kb.create_decision": {
        "description": "Create an ADR with source path or verification command provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "title": {"type": "string"},
                "status": {"type": "string"},
                "source_paths": {"type": "array", "items": {"type": "string"}},
                "verification_command": {"type": "string"},
                "commit": {"type": "string"},
                "context": {"type": "string"},
                "decision": {"type": "string"},
                "vault": {"type": "string"},
            },
            "required": ["project", "title"],
            "anyOf": [
                {"required": ["source_paths"]},
                {"required": ["verification_command"]},
            ],
            "additionalProperties": False,
        },
    },
    "kb.update_project_status": {
        "description": "Update a project's status field to an allowed value.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}, "status": {"type": "string"}, "vault": {"type": "string"}},
            "required": ["project", "status"],
            "additionalProperties": False,
        },
    },
    "kb.update_frontmatter_field": {
        "description": "Update one allowed frontmatter field on a note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "field": {"type": "string"},
                "value": {"type": "string"},
                "vault": {"type": "string"},
            },
            "required": ["path", "field", "value"],
            "additionalProperties": False,
        },
    },
    "kb.release_check": {
        "description": "Check Project KB release readiness gates without modifying notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "level": {"type": "string", "enum": ["engineering", "environment", "pilot", "full"]},
                "commit": {"type": "string"},
                "require_artifacts": {"type": "boolean"},
                "vault": {"type": "string"},
            },
            "required": ["project"],
            "additionalProperties": False,
        },
    },
}


def json_text(data: Any) -> list[dict[str, str]]:
    return [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    kb = ProjectKb(args.pop("vault", None))
    if name == "kb.project_find":
        data = kb.project_find(repo_path=args.get("repo_path"), project=args.get("project"))
    elif name == "kb.search":
        filters = args.get("filters") or {}
        data = kb.search(args["project"], args["query"], args.get("limit", 5), filters.get("types"))
    elif name == "kb.retrieve":
        data = kb.retrieve(args["project"], args["query"], args.get("limit", 5))
    elif name == "kb.read":
        data = kb.read(args["path"], args.get("section"))
    elif name == "kb.append_log":
        project = args.pop("project")
        data = kb.append_log(project, args, actor="mcp")
    elif name == "kb.check_staleness":
        data = kb.stale(args["project"], args["current_commit"])
    elif name == "kb.project_create":
        data = kb.init_project(args["name"], args["repo"])
    elif name == "kb.create_decision":
        data = kb.create_decision(
            args["project"],
            args["title"],
            status=args.get("status", "proposed"),
            source_paths=args.get("source_paths") or [],
            verification_command=args.get("verification_command"),
            commit=args.get("commit"),
            context=args.get("context"),
            decision=args.get("decision"),
            actor="mcp",
        )
    elif name == "kb.update_project_status":
        data = kb.update_project_status(args["project"], args["status"], actor="mcp")
    elif name == "kb.update_frontmatter_field":
        data = kb.update_frontmatter_field(args["path"], args["field"], args["value"], actor="mcp")
    elif name == "kb.release_check":
        data = kb.release_check(
            args["project"],
            args.get("level", "engineering"),
            commit=args.get("commit"),
            require_artifacts=bool(args.get("require_artifacts")),
        )
    else:
        raise ValueError(f"unknown tool: {name}")
    return {"content": json_text(data), "isError": False}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    try:
        if method == "initialize":
            return response(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "project-kb", "version": "0.1.0"},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return response(
                request_id,
                {"tools": [{"name": name, **meta} for name, meta in TOOLS.items()]},
            )
        if method == "tools/call":
            params = message.get("params") or {}
            return response(request_id, call_tool(params["name"], dict(params.get("arguments") or {})))
        return response(request_id, error={"code": -32601, "message": f"method not found: {method}"})
    except Exception as exc:
        return response(request_id, error={"code": -32000, "message": str(exc)})


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            result = handle(message)
        except Exception as exc:
            result = response(None, error={"code": -32700, "message": str(exc)})
        if result is not None:
            print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
