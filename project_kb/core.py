from __future__ import annotations

import json
import math
import os
import re
import ssl
import subprocess
import shutil
import time
import uuid
import urllib.error
import urllib.request
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
VALID_TYPES = {"project", "hot", "context", "architecture", "glossary", "pitfall", "decision", "module", "task", "log", "source"}
VALID_STATUSES = {"active", "paused", "archived", "proposed", "accepted", "superseded", "rejected"}
PROJECT_STATUSES = {"active", "paused", "archived"}
DECISION_STATUSES = {"proposed", "accepted", "superseded", "rejected"}
STALE_TRACKED_TYPES = {"project", "context", "architecture", "glossary", "pitfall", "decision", "module", "task", "source"}
ALLOWED_FRONTMATTER_UPDATES = {
    "status",
    "confidence",
    "verified_commit",
    "last_verified_commit",
    "last_verified_at",
    "transport",
    "tags",
}
GENERATED_NOISE_MARKERS = [
    "node_modules/",
    ".vite/",
    "__pycache__/",
    ".pytest_cache/",
    "dist/",
    "build/",
]
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
]
REPO_WIDE_RELEASE_EVIDENCE_FILES = {
    "public_claims_gate": "public-claims.json",
    "clean_install_gate": "clean-install.json",
    "user_journey_gate": "user-journeys.json",
    "support_matrix_gate": "support-matrix.json",
}
FRONTMATTER_REQUIRED: dict[str, list[str]] = {
    "project": [
        "schema_version",
        "type",
        "project",
        "repo",
        "status",
        "agent_scope",
        "source_of_truth",
        "last_verified_commit",
        "last_verified_at",
        "transport",
        "tags",
    ],
    "hot": ["schema_version", "type", "project", "tags"],
    "context": ["schema_version", "type", "project", "source_paths", "verified_commit", "confidence", "tags"],
    "architecture": ["schema_version", "type", "project", "source_paths", "verified_commit", "confidence", "tags"],
    "glossary": ["schema_version", "type", "project", "source_paths", "verified_commit", "confidence", "tags"],
    "pitfall": ["schema_version", "type", "project", "source_paths", "verified_commit", "confidence", "tags"],
    "decision": ["schema_version", "type", "project", "status", "date", "source_paths", "verified_commit", "confidence", "tags"],
    "module": ["schema_version", "type", "project", "module", "source_paths", "verified_commit", "confidence", "tags"],
    "task": ["schema_version", "type", "project", "task_id", "status", "source_paths", "verified_commit", "confidence", "tags"],
    "log": ["schema_version", "type", "project", "period", "tags"],
    "source": ["schema_version", "type", "project", "source_paths", "verified_commit", "confidence", "tags"],
}
SECTIONS_REQUIRED: dict[str, list[str]] = {
    "project": [
        "Purpose",
        "Current State",
        "Important Modules",
        "Active Decisions",
        "Known Pitfalls",
        "Verification Commands",
        "Links",
    ],
    "decision": [
        "Context",
        "Decision",
        "Consequences",
        "Alternatives Considered",
        "Verification",
    ],
    "module": [
        "Responsibility",
        "Entry Points",
        "Key Files",
        "Data Flow",
        "Known Pitfalls",
        "Verification",
    ],
    "task": [
        "Status",
        "Repo",
        "Branch",
        "Commit",
        "Files",
        "Commands",
        "Result",
        "Follow-ups",
    ],
}


@dataclass
class Note:
    path: Path
    rel_path: str
    frontmatter: dict[str, Any]
    body: str
    raw: str


def normalize_rel(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "project"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return None
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.isdigit():
        return int(value)
    return value.strip('"').strip("'")


def parse_list_value(value: str) -> list[str]:
    value = value.strip()
    if value == "":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---", 4)
    if end == -1:
        return {}, raw
    front = raw[4:end].strip("\n")
    body = raw[end + 4 :].lstrip("\n")
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in front.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            if not isinstance(data.get(current_key), list):
                data[current_key] = []
            data[current_key].append(parse_scalar(line[4:]))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "":
            data[key] = None
        elif value == "[]":
            data[key] = []
        else:
            data[key] = parse_scalar(value)
    return data, body


def yaml_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace('"', '\\"')
    if any(char in escaped for char in [":", "#", "{", "}", "[", "]"]) or escaped == "":
        return f'"{escaped}"'
    return escaped


def dump_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {yaml_value(item)}")
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {yaml_value(value)}".rstrip())
    lines.append("---")
    return "\n".join(lines)


def make_note(frontmatter: dict[str, Any], body: str) -> str:
    return f"{dump_frontmatter(frontmatter)}\n{body.rstrip()}\n"


def replace_frontmatter(raw: str, frontmatter: dict[str, Any]) -> str:
    _, body = parse_frontmatter(raw)
    return f"{dump_frontmatter(frontmatter)}\n{body.rstrip()}\n"


def title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def section_from_body(body: str, section: str) -> str:
    pattern = re.compile(rf"^##+\s+{re.escape(section)}\s*$", re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##+\s+", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def tokenize(text: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9]+", text)]


class ProjectKb:
    def __init__(self, vault: Path | str | None = None):
        vault_path = vault or os.environ.get("PROJECT_KB_VAULT") or self.discover_repo_local_vault() or Path.cwd() / "vault"
        self.vault = Path(vault_path).expanduser().resolve()

    def discover_repo_local_vault(self) -> str | None:
        current = Path.cwd().resolve()
        for candidate in [current, *current.parents]:
            metadata = candidate / ".project-kb" / "project.json"
            if not metadata.exists():
                continue
            try:
                data = json.loads(metadata.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
            vault = data.get("vault")
            if vault:
                return str(vault)
        return None

    def init_project(self, name: str, repo: str) -> dict[str, Any]:
        project = slugify(name)
        repo_path = Path(repo).expanduser().resolve()
        root = self.project_root(project)
        root.mkdir(parents=True, exist_ok=True)
        for child in ["decisions", "modules", "tasks", "logs", "sources", ".vault-meta/locks", ".vault-meta/bm25", ".vault-meta/chunks"]:
            (root / child).mkdir(parents=True, exist_ok=True)

        self.write_if_missing(root / "_index.md", self.project_index(project, repo_path))
        self.write_if_missing(root / "hot.md", self.hot_note(project))
        self.write_if_missing(root / "context.md", self.typed_note(project, "context", "Context", ["Current Context", "Sources"]))
        self.write_if_missing(root / "architecture.md", self.typed_note(project, "architecture", "Architecture", ["Overview", "Boundaries", "Verification"]))
        self.write_if_missing(root / "glossary.md", self.typed_note(project, "glossary", "Glossary", ["Terms"]))
        self.write_if_missing(root / "pitfalls.md", self.typed_note(project, "pitfall", "Pitfalls", ["Known Pitfalls", "Verification"]))
        self.write_if_missing(root / "modules" / "example.md", self.module_note(project, "Example"))
        self.write_if_missing(root / "decisions" / "ADR-0001-example.md", self.adr_note(project))
        self.write_if_missing(root / "tasks" / "example-task.md", self.task_note(project, "example-task", "Example Task"))
        self.write_if_missing(root / "sources" / "_index.md", self.typed_note(project, "source", "Sources", ["Source Notes"]))
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "project": project,
            "repo": str(repo_path),
            "created_at": now_iso(),
            "adapter_surface": ["cli", "mcp-facade-compatible"],
        }
        self.write_if_missing(root / ".manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        transport = {
            "preferred": "filesystem",
            "fallback_chain": ["cli", "mcp_obsidian", "filesystem"],
            "available": {
                "cli": {
                    "available": False,
                    "path": "",
                    "reason": "obsidian executable not found during init-project",
                },
                "mcp_obsidian": {
                    "available": False,
                    "url": os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/"),
                    "checked": False,
                    "reason": "not probed during init-project",
                },
                "filesystem": {
                    "available": True,
                    "path": str(root),
                    "reason": "project root created during init-project",
                },
            },
            "evidence": {
                "obsidian_cli": {
                    "available": False,
                    "path": "",
                    "reason": "not probed during init-project",
                },
                "project_kb_cli": {
                    "available": True,
                    "path": str(Path(__file__).resolve().parents[1] / "scripts" / "kb.py"),
                    "reason": "bundled Project KB CLI script",
                },
                "obsidian_local_rest_api": {
                    "available": False,
                    "url": os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/"),
                    "checked": False,
                    "reason": "not probed during init-project",
                },
                "project_kb_mcp": {
                    "available": True,
                    "path": str(Path(__file__).resolve().parents[1] / "scripts" / "kb_mcp.py"),
                    "reason": "bundled stdio MCP facade",
                },
            },
            "last_checked_at": now_iso(),
        }
        self.write_if_missing(root / ".vault-meta" / "transport.json", json.dumps(transport, ensure_ascii=False, indent=2) + "\n")

        return {
            "project": project,
            "root": f"Projects/{project}",
            "index": f"Projects/{project}/_index.md",
            "repo": str(repo_path),
        }

    def create_decision(
        self,
        project: str,
        title: str,
        status: str = "proposed",
        source_paths: list[str] | None = None,
        verification_command: str | None = None,
        commit: str | None = None,
        context: str | None = None,
        decision: str | None = None,
        actor: str = "cli",
    ) -> dict[str, Any]:
        if status not in DECISION_STATUSES:
            raise ValueError(f"invalid decision status: {status}")
        source_paths = source_paths or []
        if not source_paths and not verification_command:
            raise ValueError("create-decision requires --source-path or --verification-command")
        payload = {
            "title": title,
            "source_paths": source_paths,
            "verification_command": verification_command or "",
            "context": context or "",
            "decision": decision or "",
            "commit": commit or "",
        }
        self.reject_secret_payload(payload)
        root = self.project_root(project)
        decisions = root / "decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        sequence_lock = decisions / ".sequence.md"
        with self.lock_file(sequence_lock):
            number = self.next_adr_number(decisions)
            slug = slugify(title).lower()
            path = decisions / f"ADR-{number:04d}-{slug}.md"
            frontmatter = {
                "schema_version": SCHEMA_VERSION,
                "type": "decision",
                "project": slugify(project),
                "status": status,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_paths": source_paths,
                "verified_commit": commit,
                "confidence": "medium",
                "tags": ["adr", "architecture", slugify(project).lower()],
            }
            body = f"""# ADR-{number:04d}: {title}

## Context

{context or "Record the confirmed context for this decision."}

## Decision

{decision or "Record the decision after it is confirmed."}

## Consequences

## Alternatives Considered

## Verification

- Commit: {commit or ""}
- Command: {verification_command or ""}
- Source Paths: {", ".join(source_paths)}
"""
            raw = make_note(frontmatter, body)
            validation_errors = self.validate_note_text(path, raw)
            repo_errors: list[dict[str, str]] = []
            repo_warnings: list[dict[str, str]] = []
            preview_note = Note(
                path=path,
                rel_path=normalize_rel(path.relative_to(self.vault)),
                frontmatter=frontmatter,
                body=body,
                raw=raw,
            )
            self.validate_repo_and_sources(preview_note, repo_errors, repo_warnings)
            validation_errors.extend(repo_errors)
            if validation_errors:
                detail = "; ".join(error["message"] for error in validation_errors)
                raise ValueError(f"target validation failed for {normalize_rel(path.relative_to(self.vault))}: {detail}")
            obsidian_cli_available, _ = self.probe_obsidian_cli()
            project_index = root / "_index.md"
            project_note = self.read_note(project_index) if project_index.exists() else None
            transport = str(project_note.frontmatter.get("transport") or "") if project_note else ""
            if transport == "mcp_obsidian" and self.obsidian_rest_enabled():
                try:
                    self.obsidian_rest_create_note(normalize_rel(path.relative_to(self.vault)), raw)
                    path.write_text(raw, encoding="utf-8")
                except Exception:
                    self.write_if_missing(path, raw)
            elif transport == "cli" and obsidian_cli_available:
                try:
                    self.obsidian_cli_create_note(project, normalize_rel(path.relative_to(self.vault)), body)
                    path.write_text(raw, encoding="utf-8")
                except Exception:
                    self.write_if_missing(path, raw)
            else:
                self.write_if_missing(path, raw)
            self.audit(project, actor, "create_decision", path, commit)
        return {"path": normalize_rel(path.relative_to(self.vault)), "created": True, "status": status}

    def update_project_status(self, project: str, status: str, actor: str = "cli") -> dict[str, Any]:
        if status not in PROJECT_STATUSES:
            raise ValueError(f"invalid project status: {status}")
        index = self.project_root(project) / "_index.md"
        updated = self.update_frontmatter_path(index, "status", status, actor, project)
        return {"path": updated["path"], "field": "status", "status": status}

    def update_frontmatter_field(self, path: str, field: str, value: str, actor: str = "cli") -> dict[str, Any]:
        if field not in ALLOWED_FRONTMATTER_UPDATES:
            raise ValueError(f"frontmatter field is not allowed for structured update: {field}")
        abs_path = self.resolve_note_path(path)
        note = self.read_note(abs_path)
        project = str(note.frontmatter.get("project") or abs_path.parents[1].name)
        typed_value: Any = parse_list_value(value) if field == "tags" else parse_scalar(value)
        if field == "status":
            note_type = note.frontmatter.get("type")
            allowed = PROJECT_STATUSES if note_type == "project" else DECISION_STATUSES
            if typed_value not in allowed:
                raise ValueError(f"invalid status for {note_type}: {typed_value}")
        return self.update_frontmatter_path(abs_path, field, typed_value, actor, project)

    def build_index(self, project: str) -> dict[str, Any]:
        notes = list(self.iter_notes(project))
        rows = []
        chunks = []
        doc_freq: dict[str, int] = {}
        for note in notes:
            title = title_from_body(note.body, Path(note.rel_path).stem)
            note_type = note.frontmatter.get("type") or "unknown"
            rows.append(f"- [{title}](../../{note.rel_path}) — `{note_type}`")
            for chunk in self.note_chunks(note):
                chunks.append(chunk)
                for term in chunk["term_freq"]:
                    doc_freq[term] = doc_freq.get(term, 0) + 1
        avgdl = round(sum(chunk["length"] for chunk in chunks) / len(chunks), 3) if chunks else 0.0
        root = self.project_root(project)
        bm25_dir = root / ".vault-meta" / "bm25"
        chunks_dir = root / ".vault-meta" / "chunks"
        bm25_dir.mkdir(parents=True, exist_ok=True)
        chunks_dir.mkdir(parents=True, exist_ok=True)
        index_path = bm25_dir / "index.json"
        chunks_path = chunks_dir / "index.json"
        summary_path = bm25_dir / "index.md"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "algorithm": "bm25",
            "k1": 1.5,
            "b": 0.75,
            "avgdl": avgdl,
            "chunk_count": len(chunks),
            "doc_freq": doc_freq,
            "chunks": chunks,
        }
        chunks_path.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "chunks": [
                        {
                            "chunk_id": chunk["chunk_id"],
                            "path": chunk["path"],
                            "title": chunk["title"],
                            "type": chunk["type"],
                            "heading": chunk["heading"],
                            "contextual_prefix": chunk["contextual_prefix"],
                            "text": chunk["text"],
                        }
                        for chunk in chunks
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary_path.write_text("# Project KB Index\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
        return {
            "path": normalize_rel(index_path.relative_to(self.vault)),
            "chunks_path": normalize_rel(chunks_path.relative_to(self.vault)),
            "notes": len(notes),
            "chunks": len(chunks),
            "algorithm": "bm25",
        }

    def retrieve(self, project: str, query: str, limit: int = 5) -> dict[str, Any]:
        results = self.retrieve_chunks(project, query, limit)
        notes = []
        for result in results:
            notes.append(
                {
                    "path": result["path"],
                    "title": result["title"],
                    "type": result["type"],
                    "heading": result["heading"],
                    "chunk_id": result["chunk_id"],
                    "contextual_prefix": result["contextual_prefix"],
                    "score": result["score"],
                    "snippet": result["snippet"],
                    "content": result["content"],
                }
            )
        return {"notes": notes}

    def retrieve_chunks(self, project: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        root = self.project_root(project)
        index_path = root / ".vault-meta" / "bm25" / "index.json"
        if not index_path.exists():
            self.build_index(project)
        index = json.loads(index_path.read_text(encoding="utf-8"))
        query_terms = tokenize(query)
        if not query_terms:
            return []
        chunks = index.get("chunks") or []
        doc_freq = index.get("doc_freq") or {}
        avgdl = float(index.get("avgdl") or 0.0) or 1.0
        chunk_count = int(index.get("chunk_count") or len(chunks) or 1)
        scored = []
        for chunk in chunks:
            score = self.bm25_score(query_terms, chunk, doc_freq, chunk_count, avgdl)
            if score <= 0:
                continue
            content = str(chunk.get("text") or "").strip()
            scored.append(
                {
                    "path": chunk["path"],
                    "title": chunk["title"],
                    "type": chunk["type"],
                    "heading": chunk["heading"],
                    "chunk_id": chunk["chunk_id"],
                    "contextual_prefix": chunk["contextual_prefix"],
                    "score": round(score, 3),
                    "snippet": self.snippet(content, query_terms),
                    "content": content,
                    "_matched_terms": sum(1 for term in set(query_terms) if term in chunk.get("term_freq", {})),
                }
            )
        scored.sort(key=lambda item: (-item["_matched_terms"], -item["score"], item["path"], item["chunk_id"]))
        bounded = scored[: max(1, min(limit, 5))]
        for item in bounded:
            item.pop("_matched_terms", None)
        return bounded

    def bm25_score(
        self,
        query_terms: list[str],
        chunk: dict[str, Any],
        doc_freq: dict[str, int],
        chunk_count: int,
        avgdl: float,
    ) -> float:
        k1 = 1.5
        b = 0.75
        length = max(int(chunk.get("length") or 0), 1)
        term_freq = chunk.get("term_freq") or {}
        score = 0.0
        for term in query_terms:
            freq = int(term_freq.get(term) or 0)
            if freq <= 0:
                continue
            df = int(doc_freq.get(term) or 0)
            idf = math.log(1 + (chunk_count - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * length / avgdl)
            score += idf * (freq * (k1 + 1)) / denom
        return score

    def note_chunks(self, note: Note) -> list[dict[str, Any]]:
        title = title_from_body(note.body, Path(note.rel_path).stem)
        note_type = note.frontmatter.get("type") or "unknown"
        chunks = []
        heading = title
        lines: list[str] = []
        index = 0

        def flush() -> None:
            nonlocal index, lines
            text = "\n".join(lines).strip()
            lines = []
            if not text:
                return
            contextual_prefix = title if heading == title else f"{title} > {heading}"
            token_source = f"{contextual_prefix}\n{text}"
            terms = tokenize(token_source)
            term_freq: dict[str, int] = {}
            for term in terms:
                term_freq[term] = term_freq.get(term, 0) + 1
            chunks.append(
                {
                    "chunk_id": f"{note.rel_path}#chunk-{index}",
                    "path": note.rel_path,
                    "title": title,
                    "type": note_type,
                    "heading": heading,
                    "contextual_prefix": contextual_prefix,
                    "text": text,
                    "term_freq": term_freq,
                    "length": max(len(terms), 1),
                }
            )
            index += 1

        for line in note.body.splitlines():
            heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading_match:
                level = len(heading_match.group(1))
                name = heading_match.group(2).strip()
                if level == 1:
                    heading = title
                    continue
                flush()
                heading = name
                continue
            lines.append(line)
        flush()
        return chunks

    def lock_list(self, project: str) -> dict[str, Any]:
        locks = []
        lock_root = self.project_root(project) / ".vault-meta" / "locks"
        if lock_root.exists():
            for path in sorted(lock_root.glob("*.lock")):
                stale = time.time() - path.stat().st_mtime > 300
                metadata: dict[str, Any] = {}
                try:
                    metadata = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    metadata = {}
                item = {"path": normalize_rel(path.relative_to(self.vault)), "stale": stale}
                if "created_at" in metadata:
                    item["created_at"] = metadata["created_at"]
                if "target" in metadata:
                    item["target"] = metadata["target"]
                locks.append(item)
        return {"locks": locks}

    def export_adapter(self, agent: str, project: str) -> dict[str, Any]:
        agent = agent.lower()
        if agent not in {"codex", "claude", "openclaw", "opencode", "generic"}:
            raise ValueError(f"unsupported agent: {agent}")
        root = self.project_root(project)
        adapter_dir = root / ".vault-meta" / "adapters" / agent
        adapter_dir.mkdir(parents=True, exist_ok=True)
        filename = {
            "codex": "AGENTS.project-kb.md",
            "claude": "CLAUDE.project-kb.md",
            "openclaw": "OPENCLAW.project-kb.md",
            "opencode": "OPENCODE.project-kb.md",
            "generic": "GENERIC.project-kb.md",
        }[agent]
        path = adapter_dir / filename
        path.write_text(self.adapter_text(agent, project), encoding="utf-8")
        return {"path": normalize_rel(path.relative_to(self.vault)), "agent": agent, "project": project}

    def pilot_record(self, project: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.reject_secret_payload(payload)
        self.validate_pilot_event(project, payload)
        task_id = str(payload.get("task_id") or "")
        if task_id and any(str(item.get("task_id") or "") == task_id for item in self.read_pilot_events(project)):
            raise ValueError(f"pilot task already recorded: {task_id}")
        event = {
            "recorded_at": now_iso(),
            "event_type": str(payload.get("event_type") or "task"),
            "task_id": task_id,
            "title": str(payload.get("title") or ""),
            "status": str(payload.get("status") or "completed"),
            "host": str(payload.get("host") or ""),
            "category": str(payload.get("category") or ""),
            "searches": int(payload.get("searches") or 0),
            "notes_read": int(payload.get("notes_read") or 0),
            "write_backs": int(payload.get("write_backs") or 0),
            "stale_notes": int(payload.get("stale_notes") or 0),
            "effective_hit": bool(payload.get("effective_hit")),
            "false_positive": bool(payload.get("false_positive")),
            "stale_misguidance": bool(payload.get("stale_misguidance")),
            "injected_notes": int(payload.get("injected_notes") or 0),
            "context_tokens": int(payload.get("context_tokens") or 0),
            "write_back_accepted": bool(payload.get("write_back_accepted")),
            "destructive_write_incident": bool(payload.get("destructive_write_incident")),
            "lock_contention_count": int(payload.get("lock_contention_count") or 0),
            "validation_failures": int(payload.get("validation_failures") or 0),
            "path": str(payload.get("path") or ""),
            "notes": str(payload.get("notes") or ""),
            "evidence": payload.get("evidence") or [],
        }
        pilot_dir = self.project_root(project) / ".vault-meta" / "pilot"
        pilot_dir.mkdir(parents=True, exist_ok=True)
        path = pilot_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return {"path": normalize_rel(path.relative_to(self.vault)), "recorded": True}

    def validate_pilot_event(self, project: str, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("event_type") or "task")
        if event_type != "task":
            return

        plan_path = self.project_root(project) / ".vault-meta" / "pilot" / "plan.json"
        if not plan_path.exists():
            raise ValueError("pilot plan is required before recording task events")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        tasks = plan.get("tasks") or []
        planned_ids = {str(task.get("task_id") or "") for task in tasks}
        required_fields: set[str] = set()
        for task in tasks:
            if str(task.get("task_id") or "") == str(payload.get("task_id") or ""):
                required_fields = set(task.get("required_event_fields") or [])
                break

        task_id = str(payload.get("task_id") or "")
        if not task_id or task_id not in planned_ids:
            raise ValueError(f"pilot task_id is not in pilot plan: {task_id}")
        status = str(payload.get("status") or "completed")
        if status not in {"completed", "environment_blocked"}:
            raise ValueError(f"invalid pilot task status: {status}")

        missing = sorted(field for field in required_fields if field not in payload)
        if missing:
            raise ValueError(f"missing pilot event fields: {', '.join(missing)}")

        numeric_fields = [
            "searches",
            "notes_read",
            "write_backs",
            "stale_notes",
            "injected_notes",
            "context_tokens",
            "lock_contention_count",
            "validation_failures",
        ]
        for field in numeric_fields:
            try:
                value = int(payload.get(field))
            except (TypeError, ValueError):
                raise ValueError(f"pilot event field must be a non-negative integer: {field}") from None
            if value < 0:
                raise ValueError(f"pilot event field must be a non-negative integer: {field}")

    def compute_metrics(self, project: str) -> dict[str, Any]:
        events = self.read_pilot_events(project)
        task_events = [event for event in events if (event.get("event_type") or "task") == "task"]
        tasks = len(task_events)
        effective_hits = sum(1 for event in task_events if event.get("effective_hit"))
        false_positives = sum(1 for event in task_events if event.get("false_positive"))
        stale_misguidance = sum(1 for event in task_events if event.get("stale_misguidance"))
        write_backs = sum(int(event.get("write_backs") or 0) for event in task_events)
        accepted_write_backs = sum(1 for event in task_events if event.get("write_back_accepted"))
        destructive = sum(1 for event in task_events if event.get("destructive_write_incident"))
        lock_contention = sum(int(event.get("lock_contention_count") or 0) for event in events)
        validation_failures = sum(int(event.get("validation_failures") or 0) for event in task_events)
        injected_total = sum(int(event.get("injected_notes") or 0) for event in task_events)
        token_total = sum(int(event.get("context_tokens") or 0) for event in task_events)
        stale_total = sum(int(event.get("stale_notes") or 0) for event in task_events)
        result = {
            "project": project,
            "tasks": tasks,
            "kb_searches": sum(int(event.get("searches") or 0) for event in task_events),
            "note_reads": sum(int(event.get("notes_read") or 0) for event in task_events),
            "write_backs": write_backs,
            "stale_note_count": stale_total,
            "effective_retrieval_hit_rate": round(effective_hits / tasks, 3) if tasks else 0.0,
            "false_positive_retrieval_rate": round(false_positives / tasks, 3) if tasks else 0.0,
            "stale_note_misguidance_events": stale_misguidance,
            "average_injected_notes": round(injected_total / tasks, 3) if tasks else 0.0,
            "average_context_tokens": round(token_total / tasks, 3) if tasks else 0.0,
            "write_back_acceptance_rate": round(accepted_write_backs / write_backs, 3) if write_backs else 0.0,
            "validation_failures": validation_failures,
            "lock_contention_count": lock_contention,
            "destructive_write_incidents": destructive,
        }
        result["thresholds"] = {
            "effective_retrieval_hit_rate": {
                "target": 0.6,
                "actual": result["effective_retrieval_hit_rate"],
                "passed": result["effective_retrieval_hit_rate"] >= 0.6,
            },
            "stale_misguidance": {
                "target": "<= 1",
                "actual": stale_misguidance,
                "passed": stale_misguidance <= 1,
            },
            "average_injected_notes": {
                "target": "<= 5",
                "actual": result["average_injected_notes"],
                "passed": result["average_injected_notes"] <= 5,
            },
            "write_back_provenance": {
                "target": "100%",
                "actual": result["write_back_acceptance_rate"],
                "passed": write_backs == 0 or result["write_back_acceptance_rate"] == 1.0,
            },
            "validation_failures": {
                "target": 0,
                "actual": validation_failures,
                "passed": validation_failures == 0,
            },
            "lock_contention_count": {
                "target": 0,
                "actual": lock_contention,
                "passed": lock_contention == 0,
            },
            "destructive_write_incidents": {
                "target": 0,
                "actual": destructive,
                "passed": destructive == 0,
            },
        }
        return result

    def metrics(self, project: str) -> dict[str, Any]:
        result = self.compute_metrics(project)
        metrics_path = self.project_root(project) / ".vault-meta" / "pilot" / "metrics.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    def pilot_plan(self, project: str) -> dict[str, Any]:
        project = slugify(project)
        root = self.project_root(project)
        pilot_dir = root / ".vault-meta" / "pilot"
        pilot_dir.mkdir(parents=True, exist_ok=True)
        specs = [
            ("task-001", "architecture", "Codex", "Resolve project context and use KB notes on an architecture question."),
            ("task-002", "implementation", "Codex", "Use KB retrieval while making a small implementation change."),
            ("task-003", "verification", "Codex", "Use KB to select and run the right verification commands."),
            ("task-004", "documentation", "Codex", "Use KB context to update a project note or checked-in doc after verification."),
            ("task-005", "architecture", "Claude Code", "Repeat an architecture lookup through the Claude Code adapter path."),
            ("task-006", "implementation", "Claude Code", "Use shared KB context during a bounded Claude Code implementation task."),
            ("task-007", "verification", "OpenCode", "Use the OpenCode adapter path to run a verification-oriented KB workflow."),
            ("task-008", "documentation", "OpenCode", "Record a verified write-back through the OpenCode-facing workflow."),
            ("task-009", "architecture", "OpenClaw", "Route an OpenClaw-hosted session to the shared KB for a context lookup."),
            ("task-010", "verification", "Codex", "Run final pilot metrics review and stale-note check after prior tasks."),
        ]
        tasks = []
        event_dir = pilot_dir / "events"
        event_dir.mkdir(parents=True, exist_ok=True)
        for task_id, category, host, title in specs:
            event_rel_path = f"Projects/{project}/.vault-meta/pilot/events/{task_id}.json"
            event_template = {
                "task_id": task_id,
                "title": title,
                "status": "planned",
                "host": host,
                "category": category,
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
                "notes": "Record actual KB search count, note reads, write-backs, and verification evidence after this real task is complete.",
            }
            (event_dir / f"{task_id}.json").write_text(
                json.dumps(event_template, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tasks.append(
                {
                    "task_id": task_id,
                    "category": category,
                    "host": host,
                    "title": title,
                    "event_file": event_rel_path,
                    "required_event_fields": [
                        "task_id",
                        "title",
                        "searches",
                        "notes_read",
                        "write_backs",
                        "stale_notes",
                        "effective_hit",
                        "false_positive",
                        "stale_misguidance",
                        "injected_notes",
                        "context_tokens",
                        "write_back_accepted",
                        "destructive_write_incident",
                        "lock_contention_count",
                        "validation_failures",
                    ],
                }
            )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project": project,
            "created_at": now_iso(),
            "task_count": len(tasks),
            "selection_rules": [
                "cover architecture/module understanding, implementation, and verification/documentation work",
                "cover at least two agent hosts; blocked hosts must be recorded as environment_blocked in the task evidence",
                "record searches before note reads and keep injected notes <= 5 per task",
                "write-backs require provenance from commands, files, commit, source path, URL, or repo",
                "record stale_misguidance=true for any note that misleads the current-code decision",
            ],
            "record_command_template": f"python scripts/kb.py pilot record --project {project} --from-file <event-file>",
            "metrics_command": f"python scripts/kb.py metrics --project {project}",
            "release_check_command": f"python scripts/kb.py release check --project {project} --level pilot",
            "tasks": tasks,
        }
        plan_path = pilot_dir / "plan.json"
        plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {
            "project": project,
            "path": normalize_rel(plan_path.relative_to(self.vault)),
            "task_count": len(tasks),
            "selection_rules": payload["selection_rules"],
            "record_command_template": payload["record_command_template"],
            "metrics_command": payload["metrics_command"],
            "release_check_command": payload["release_check_command"],
            "tasks": tasks,
        }

    def pilot_status(self, project: str) -> dict[str, Any]:
        project = slugify(project)
        root = self.project_root(project)
        plan_path = root / ".vault-meta" / "pilot" / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else self.pilot_plan(project)
        events = [event for event in self.read_pilot_events(project) if (event.get("event_type") or "task") == "task"]
        recorded_by_id = {str(event.get("task_id") or ""): event for event in events}
        tasks = []
        for item in plan.get("tasks", []):
            task_id = str(item.get("task_id") or "")
            recorded = recorded_by_id.get(task_id)
            tasks.append(
                {
                    "task_id": task_id,
                    "title": item.get("title") or "",
                    "host": item.get("host") or "",
                    "category": item.get("category") or "",
                    "event_file": item.get("event_file") or "",
                    "status": "recorded" if recorded else "planned",
                    "recorded_at": recorded.get("recorded_at", "") if recorded else "",
                }
            )
        recorded_count = sum(1 for item in tasks if item["status"] == "recorded")
        return {
            "project": project,
            "plan_path": normalize_rel(plan_path.relative_to(self.vault)),
            "planned": len(tasks),
            "recorded": recorded_count,
            "missing": len(tasks) - recorded_count,
            "tasks": tasks,
            "metrics": self.compute_metrics(project),
        }

    def install_repo_adapters(self, project: str, repo: str) -> dict[str, Any]:
        repo_path = Path(repo).expanduser().resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"repo path does not exist: {repo}")
        kb_dir = repo_path / ".project-kb"
        files = []
        project_info = {
            "schema_version": SCHEMA_VERSION,
            "project": project,
            "repo": str(repo_path),
            "vault": str(self.vault),
            "project_path": f"Projects/{slugify(project)}",
            "mcp_server": "python scripts/kb_mcp.py",
            "cli": "python scripts/kb.py",
        }
        project_json = kb_dir / "project.json"
        project_json.parent.mkdir(parents=True, exist_ok=True)
        project_json.write_text(json.dumps(project_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append(normalize_rel(project_json.relative_to(repo_path)))
        names = {
            "codex": "AGENTS.project-kb.md",
            "claude": "CLAUDE.project-kb.md",
            "openclaw": "OPENCLAW.project-kb.md",
            "opencode": "OPENCODE.project-kb.md",
            "generic": "GENERIC.project-kb.md",
        }
        for agent, filename in names.items():
            path = kb_dir / "adapters" / agent / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.adapter_text(agent, project), encoding="utf-8")
            files.append(normalize_rel(path.relative_to(repo_path)))
        host_config_dir = kb_dir / "host-configs"
        host_config_dir.mkdir(parents=True, exist_ok=True)
        host_configs = {
            "codex.config.toml": self.repo_codex_config(project),
            "claude.mcp.json": self.repo_claude_mcp_config(project),
            "openclaw.mcp.json5": self.repo_openclaw_mcp_config(project),
            "opencode.md": self.host_config_text("opencode", self.repo_host_manifest(project)),
            "README.md": self.repo_host_config_readme(project),
        }
        for filename, content in host_configs.items():
            path = host_config_dir / filename
            path.write_text(content, encoding="utf-8")
            files.append(normalize_rel(path.relative_to(repo_path)))
        return {"repo": str(repo_path), "files": files}

    def export_host_configs(self, project: str) -> dict[str, Any]:
        root = self.project_root(project)
        config_dir = root / ".vault-meta" / "host-configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        python_command = Path(os.environ.get("PYTHON", "")).name or "python"
        mcp_script = Path(__file__).resolve().parents[1] / "scripts" / "kb_mcp.py"
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "project": project,
            "server": {
                "name": "project-kb",
                "command": python_command,
                "args": [normalize_rel(mcp_script)],
                "transport": "stdio",
            },
            "env": {
                "PROJECT_KB_VAULT": str(self.vault),
                "PROJECT_KB_PROJECT": slugify(project),
            },
            "safe_tools": [
                "kb.project_find",
                "kb.search",
                "kb.retrieve",
                "kb.read",
                "kb.append_log",
                "kb.check_staleness",
                "kb.project_create",
                "kb.create_decision",
                "kb.update_project_status",
                "kb.update_frontmatter_field",
            ],
            "dangerous_tools_exposed": [],
        }
        files = []
        manifest_path = config_dir / "mcp-server.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append(normalize_rel(manifest_path.relative_to(self.vault)))
        for host in ["codex", "claude", "openclaw", "opencode", "generic"]:
            path = config_dir / f"{host}.md"
            path.write_text(self.host_config_text(host, manifest), encoding="utf-8")
            files.append(normalize_rel(path.relative_to(self.vault)))
        return {"project": project, "files": files}

    def export_views(self, project: str) -> dict[str, Any]:
        root = self.project_root(project)
        views_dir = root / "views"
        views_dir.mkdir(parents=True, exist_ok=True)
        canvas_path = views_dir / "project-map.canvas"
        base_path = views_dir / "project-notes.base"
        canvas_path.write_text(
            json.dumps(self.project_canvas(project), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        base_path.write_text(self.project_base(project), encoding="utf-8")
        return {
            "project": project,
            "files": [
                normalize_rel(canvas_path.relative_to(self.vault)),
                normalize_rel(base_path.relative_to(self.vault)),
            ],
        }

    def release_artifact_check(self, project: str) -> dict[str, Any]:
        root = self.project_root(project)
        project_note = self.read_note(root / "_index.md")
        repo = Path(str(project_note.frontmatter.get("repo") or "")).expanduser()
        missing: list[str] = []
        mismatches: list[str] = []
        expected_repo_artifacts = [
            ".project-kb/project.json",
            ".project-kb/host-configs/codex.config.toml",
            ".project-kb/host-configs/claude.mcp.json",
            ".project-kb/host-configs/openclaw.mcp.json5",
            ".project-kb/host-configs/opencode.md",
            ".project-kb/host-configs/README.md",
        ]
        for rel_path in expected_repo_artifacts:
            if not (repo / rel_path).exists():
                missing.append(rel_path)
        project_json = repo / ".project-kb" / "project.json"
        if project_json.exists():
            try:
                data = json.loads(project_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                mismatches.append(f".project-kb/project.json is invalid JSON: {exc}")
            else:
                if data.get("project") != project:
                    mismatches.append(".project-kb/project.json project mismatch")
                if Path(str(data.get("vault") or "")).expanduser().resolve() != self.vault.resolve():
                    mismatches.append(".project-kb/project.json vault mismatch")
                if Path(str(data.get("repo") or "")).expanduser().resolve() != repo.resolve():
                    mismatches.append(".project-kb/project.json repo mismatch")
                if data.get("project_path") != f"Projects/{slugify(project)}":
                    mismatches.append(".project-kb/project.json project_path mismatch")
        host_manifest = root / ".vault-meta" / "host-configs" / "mcp-server.json"
        if not host_manifest.exists():
            missing.append(f"Projects/{slugify(project)}/.vault-meta/host-configs/mcp-server.json")
        else:
            try:
                data = json.loads(host_manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                mismatches.append(f"{normalize_rel(host_manifest.relative_to(self.vault))} is invalid JSON: {exc}")
            else:
                args = data.get("server", {}).get("args") or []
                if not args or not str(args[0]).replace("\\", "/").endswith("scripts/kb_mcp.py"):
                    mismatches.append("host MCP manifest does not point to scripts/kb_mcp.py")
                env = data.get("env", {})
                if env.get("PROJECT_KB_VAULT") != str(self.vault):
                    mismatches.append("host MCP manifest PROJECT_KB_VAULT mismatch")
                if env.get("PROJECT_KB_PROJECT") != slugify(project):
                    mismatches.append("host MCP manifest PROJECT_KB_PROJECT mismatch")
        passed = not missing and not mismatches
        return {"passed": passed, "missing": missing, "mismatches": mismatches}

    def repo_wide_release_evidence_check(self, project: str) -> dict[str, Any]:
        root = self.project_root(project)
        evidence_dir = root / ".vault-meta" / "release" / "repo-wide"
        required = {
            "public_claims_gate": {
                "path": evidence_dir / REPO_WIDE_RELEASE_EVIDENCE_FILES["public_claims_gate"],
                "evidence_required": [
                    "docs/project-kb/release-plan-cn.md",
                    "README.md",
                    "README.en.md",
                    "deployment guide",
                    "adapter docs",
                ],
            },
            "clean_install_gate": {
                "path": evidence_dir / REPO_WIDE_RELEASE_EVIDENCE_FILES["clean_install_gate"],
                "evidence_required": [
                    "fresh clone command log",
                    "setup script result",
                    "vault creation/open proof",
                    "doctor output",
                ],
            },
            "user_journey_gate": {
                "path": evidence_dir / REPO_WIDE_RELEASE_EVIDENCE_FILES["user_journey_gate"],
                "evidence_required": [
                    "ingest journey",
                    "query journey",
                    "lint journey",
                    "social ingest journey or not-in-release decision",
                ],
            },
            "support_matrix_gate": {
                "path": evidence_dir / REPO_WIDE_RELEASE_EVIDENCE_FILES["support_matrix_gate"],
                "evidence_required": [
                    "host matrix",
                    "OS matrix",
                    "transport matrix",
                    "Obsidian surface matrix",
                ],
            },
        }
        checks: list[dict[str, Any]] = []
        for name, spec in required.items():
            path = spec["path"]
            detail = {
                "path": normalize_rel(path.relative_to(self.vault)),
                "evidence_required": spec["evidence_required"],
            }
            if not path.exists():
                checks.append({"name": name, "passed": False, "actual": "missing", "detail": detail})
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                detail["error"] = str(exc)
                checks.append({"name": name, "passed": False, "actual": "invalid", "detail": detail})
                continue
            passed = bool(payload.get("passed"))
            detail["evidence"] = payload
            checks.append({"name": name, "passed": passed, "actual": "passed" if passed else "not passed", "detail": detail})
        return {
            "project": project,
            "target_release": "repo-wide-end-user-release",
            "evidence_dir": normalize_rel(evidence_dir.relative_to(self.vault)),
            "checks": checks,
            "passed": all(item["passed"] for item in checks),
        }

    def release_evidence_record(self, project: str, gate: str, payload: dict[str, Any]) -> dict[str, Any]:
        if gate not in REPO_WIDE_RELEASE_EVIDENCE_FILES:
            allowed = ", ".join(sorted(REPO_WIDE_RELEASE_EVIDENCE_FILES))
            raise ValueError(f"unsupported repo-wide evidence gate: {gate}; expected one of {allowed}")
        self.reject_secret_payload(payload)
        observable_fields = ["commands", "reviewed_files", "journeys", "matrix", "notes", "artifacts", "screenshots"]
        if payload.get("passed") is True and not any(payload.get(field) for field in observable_fields):
            raise ValueError("repo-wide evidence with passed=true requires observable evidence")
        root = self.project_root(project)
        evidence_dir = root / ".vault-meta" / "release" / "repo-wide"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / REPO_WIDE_RELEASE_EVIDENCE_FILES[gate]
        record = {
            "schema_version": SCHEMA_VERSION,
            "project": slugify(project),
            "gate": gate,
            "recorded_at": now_iso(),
            **payload,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {
            "project": slugify(project),
            "gate": gate,
            "path": normalize_rel(path.relative_to(self.vault)),
            "recorded": True,
        }

    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def release_public_claims_smoke(self, project: str) -> dict[str, Any]:
        repo_root = self.repo_root()
        reviewed_files = [
            "README.md",
            "README.en.md",
            "docs/project-kb/cli.md",
            "docs/project-kb/release-plan-cn.md",
        ]
        contents: dict[str, str] = {}
        missing_files = []
        for rel_path in reviewed_files:
            path = repo_root / rel_path
            if not path.exists():
                missing_files.append(rel_path)
                contents[rel_path] = ""
                continue
            contents[rel_path] = path.read_text(encoding="utf-8")

        corpus = "\n".join(contents.values()).lower()
        claims = [
            {
                "id": "release_status_scope",
                "status": "scoped" if "release status" in corpus and "project kb preview" in corpus else "missing",
                "evidence": self.matching_lines(contents, ["Release Status", "Project KB preview", "发布状态", "Project KB 技术预览"]),
            },
            {
                "id": "preview_vs_repo_wide",
                "status": "scoped" if "repo-wide" in corpus and "project-kb-full" in corpus else "missing",
                "evidence": self.matching_lines(contents, ["repo-wide", "project-kb-full", "仓库整体", "完整发布"]),
            },
            {
                "id": "live_limitations",
                "status": "limited"
                if all(term in corpus for term in ["not live", "obsidian cli", "local rest"])
                or all(term in corpus for term in ["未 live", "obsidian cli", "local rest"])
                else "missing",
                "evidence": self.matching_lines(contents, ["not live", "未 live", "Obsidian CLI", "Local REST", "blocked"]),
            },
            {
                "id": "draft_host_configs",
                "status": "limited" if "draft" in corpus and "do not auto-install" in corpus else "missing",
                "evidence": self.matching_lines(contents, ["draft", "do not auto-install", "repo-local drafts"]),
            },
        ]
        passed = not missing_files and all(item["status"] in {"scoped", "limited"} for item in claims)
        evidence = {
            "passed": passed,
            "reviewed_files": reviewed_files,
            "missing_files": missing_files,
            "claims": claims,
            "commands": ["scan README, README.en, CLI docs, and release plan for release-scope limitations"],
            "notes": "Public claims smoke checks that broad README claims are scoped by current release status and live-evidence limitations. It does not prove live user journeys.",
        }
        record = self.release_evidence_record(project, "public_claims_gate", evidence)
        return {
            "project": slugify(project),
            "gate": "public_claims_gate",
            "passed": passed,
            "evidence": evidence,
            "record": record,
        }

    def matching_lines(self, contents: dict[str, str], patterns: list[str]) -> list[str]:
        matches = []
        lowered_patterns = [pattern.lower() for pattern in patterns]
        for rel_path, text in contents.items():
            for index, line in enumerate(text.splitlines(), start=1):
                lower_line = line.lower()
                if any(pattern in lower_line for pattern in lowered_patterns):
                    matches.append(f"{rel_path}:{index}: {line.strip()}")
        return matches[:20]

    def release_clean_install_smoke(self, project: str) -> dict[str, Any]:
        repo_root = self.repo_root()
        template_dir = repo_root / "vault-template"
        if not template_dir.exists():
            raise FileNotFoundError("vault-template directory is missing")
        required_artifacts = [
            "AGENTS.md",
            "AI_CONFIG.md",
            "wiki/index.md",
            "wiki/log.md",
            "raw",
            "assets",
            ".opencode/skill/defuddle/SKILL.md",
            ".opencode/skill/obsidian-cli/SKILL.md",
            ".opencode/skill/obsidian-markdown/SKILL.md",
            ".opencode/skill/opencli-usage/SKILL.md",
            ".opencode/skill/smart-search/SKILL.md",
            ".opencode/skill/opencli-browser/SKILL.md",
            ".opencode/skill/opencli-autofix/SKILL.md",
            ".opencode/skill/opencli-explorer/SKILL.md",
            ".opencode/skill/opencli-oneshot/SKILL.md",
        ]
        install_scripts = ["setup.sh", "setup.ps1"]
        missing_install_scripts = [script for script in install_scripts if not (repo_root / script).exists()]
        reviewed_files = ["README.md", "README.en.md", "GUIDE_FOR_AI.md", "deployment-guide.md"]
        invalid_doc_paths = self.invalid_install_doc_paths(repo_root, reviewed_files)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "我的知识库"
            shutil.copytree(template_dir, target)
            missing = [artifact for artifact in required_artifacts if not (target / artifact).exists()]
            passed = not missing and not missing_install_scripts and not invalid_doc_paths
        evidence = {
            "passed": passed,
            "commands": [
                "copy vault-template to temporary vault",
                "verify required template artifacts",
                "verify documented install paths and setup scripts",
            ],
            "reviewed_files": reviewed_files,
            "artifacts": required_artifacts,
            "install_scripts": install_scripts,
            "missing": missing,
            "missing_install_scripts": missing_install_scripts,
            "invalid_doc_paths": invalid_doc_paths,
            "notes": "Dry-run clean install smoke copies vault-template into a temporary vault and verifies the files required by the public setup path. It does not install Node, OpenCode, OpenCLI, or modify a live Obsidian configuration.",
        }
        record = self.release_evidence_record(project, "clean_install_gate", evidence)
        return {
            "project": slugify(project),
            "gate": "clean_install_gate",
            "passed": passed,
            "evidence": evidence,
            "record": record,
        }

    def invalid_install_doc_paths(self, repo_root: Path, reviewed_files: list[str]) -> list[str]:
        invalid = []
        cd_pattern = re.compile(r"\bcd\s+([^\r\n`]+)")
        for rel_path in reviewed_files:
            path = repo_root / rel_path
            if not path.exists():
                invalid.append(f"missing reviewed install doc: {rel_path}")
                continue
            text = path.read_text(encoding="utf-8")
            for match in cd_pattern.finditer(text):
                raw_target = match.group(1).strip().strip('"').strip("'")
                raw_target = raw_target.split("&&", 1)[0].strip()
                raw_target = raw_target.replace("\\", "/")
                if "Obsidian-OpenCode-Knowledge/" in raw_target:
                    suffix = raw_target.split("Obsidian-OpenCode-Knowledge/", 1)[1].strip("/")
                elif raw_target.endswith("Obsidian-OpenCode-Knowledge"):
                    suffix = ""
                else:
                    continue
                if suffix and not (repo_root / suffix).exists():
                    invalid.append(f"{rel_path} references missing directory: {suffix}")
        return sorted(set(invalid))

    def release_user_journey_smoke(self, project: str) -> dict[str, Any]:
        repo_root = self.repo_root()
        template_dir = repo_root / "vault-template"
        agents = (template_dir / "AGENTS.md").read_text(encoding="utf-8")
        ai_config = (template_dir / "AI_CONFIG.md").read_text(encoding="utf-8")
        guide = (template_dir / "wiki" / "使用指南.md").read_text(encoding="utf-8")
        readme = (repo_root / "README.md").read_text(encoding="utf-8")
        journey_specs = [
            {
                "id": "ingest",
                "triggers": ["加到 wiki", "ingest 这个"],
                "required_text": ["raw/", "wiki/", "wiki/index.md", "wiki/log.md", "## Sources"],
                "verified_artifacts": ["raw/", "wiki/", "wiki/index.md", "wiki/log.md"],
            },
            {
                "id": "query",
                "triggers": ["我知道啥关于", "wiki 里有没有"],
                "required_text": ["wiki/index.md", "默认只在对话里答", "markdown 链接"],
                "verified_artifacts": ["wiki/index.md"],
            },
            {
                "id": "lint",
                "triggers": ["lint wiki", "体检"],
                "required_text": ["index_consistency", "broken_links", "wiki/log.md"],
                "verified_artifacts": ["wiki/index.md", "wiki/log.md"],
            },
            {
                "id": "social_ingest",
                "triggers": ["爬了这个", "收录这条"],
                "required_text": ["raw/social", "assets/", "social-ingest", "opencli"],
                "verified_artifacts": ["raw/social", "assets/", "wiki/log.md"],
            },
        ]
        corpus = "\n".join([agents, ai_config, guide, readme])
        journeys = []
        for spec in journey_specs:
            missing = [text for text in [*spec["triggers"], *spec["required_text"]] if text not in corpus]
            journeys.append(
                {
                    "id": spec["id"],
                    "passed": not missing,
                    "triggers": spec["triggers"],
                    "verified_artifacts": spec["verified_artifacts"],
                    "missing": missing,
                }
            )
        artifact_smoke = self.user_journey_artifact_smoke(template_dir)
        passed = all(item["passed"] for item in journeys) and not artifact_smoke["smoke_missing"]
        evidence = {
            "passed": passed,
            "commands": [
                "verify README, vault-template/AGENTS.md, AI_CONFIG.md, and wiki/使用指南.md user journey coverage",
                "copy vault-template and exercise minimal ingest/query/lint/social-ingest file artifacts",
            ],
            "journeys": journeys,
            "smoke_artifacts": artifact_smoke["smoke_artifacts"],
            "smoke_missing": artifact_smoke["smoke_missing"],
            "notes": "User journey smoke verifies that the published template documents define ingest, query, lint, and social ingest flows. It does not execute a live LLM or browser session.",
        }
        record = self.release_evidence_record(project, "user_journey_gate", evidence)
        return {
            "project": slugify(project),
            "gate": "user_journey_gate",
            "passed": passed,
            "evidence": evidence,
            "record": record,
        }

    def user_journey_artifact_smoke(self, template_dir: Path) -> dict[str, Any]:
        required_template_artifacts = [
            "raw/social",
            "wiki/log.md",
        ]
        smoke_artifacts = [
            "raw/release-smoke/source.md",
            "wiki/release-smoke-note.md",
            "raw/social/release-smoke-social.md",
            "wiki/log.md",
        ]
        template_missing = [artifact for artifact in required_template_artifacts if not (template_dir / artifact).exists()]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "我的知识库"
            shutil.copytree(template_dir, target)
            (target / "raw" / "release-smoke").mkdir(parents=True, exist_ok=True)
            (target / "raw" / "release-smoke" / "source.md").write_text(
                "# Release Smoke Source\n\nA small source item for ingest smoke.\n",
                encoding="utf-8",
            )
            (target / "wiki" / "release-smoke-note.md").write_text(
                "# Release Smoke Note\n\n## Sources\n\n- [[../raw/release-smoke/source|source]]\n",
                encoding="utf-8",
            )
            log_path = target / "wiki" / "log.md"
            if (target / "raw" / "social").is_dir():
                (target / "raw" / "social" / "release-smoke-social.md").write_text(
                    "# Release Smoke Social\n\nsource: release-smoke\n",
                    encoding="utf-8",
                )
            if log_path.exists():
                log_text = log_path.read_text(encoding="utf-8")
                log_path.write_text(
                    log_text.rstrip()
                    + "\n\n## release-smoke lint | 0 issues found, 0 auto-fixed\n\n"
                    + "- Checked wiki/release-smoke-note.md\n",
                    encoding="utf-8",
                )
            smoke_missing = template_missing + [artifact for artifact in smoke_artifacts if not (target / artifact).exists()]
        return {"smoke_artifacts": smoke_artifacts, "smoke_missing": smoke_missing}

    def release_support_matrix_smoke(self, project: str) -> dict[str, Any]:
        root = self.project_root(project)
        project_note = self.read_note(root / "_index.md")
        repo = Path(str(project_note.frontmatter.get("repo") or "")).expanduser()
        artifact_result = self.release_artifact_check(project)
        transport = self.transport_detect(project, persist=False)
        host_paths = {
            "Codex": [
                ".project-kb/adapters/codex/AGENTS.project-kb.md",
                ".project-kb/host-configs/codex.config.toml",
                f"Projects/{slugify(project)}/.vault-meta/host-configs/codex.md",
            ],
            "Claude Code": [
                ".project-kb/adapters/claude/CLAUDE.project-kb.md",
                ".project-kb/host-configs/claude.mcp.json",
                f"Projects/{slugify(project)}/.vault-meta/host-configs/claude.md",
            ],
            "OpenClaw": [
                ".project-kb/adapters/openclaw/OPENCLAW.project-kb.md",
                ".project-kb/host-configs/openclaw.mcp.json5",
                f"Projects/{slugify(project)}/.vault-meta/host-configs/openclaw.md",
            ],
            "OpenCode": [
                ".project-kb/adapters/opencode/OPENCODE.project-kb.md",
                ".project-kb/host-configs/opencode.md",
                f"Projects/{slugify(project)}/.vault-meta/host-configs/opencode.md",
            ],
        }

        def artifact_exists(rel_path: str) -> bool:
            if rel_path.startswith("Projects/"):
                return (self.vault / rel_path).exists()
            return (repo / rel_path).exists()

        def artifact_entry(rel_paths: list[str]) -> dict[str, Any]:
            missing = [rel_path for rel_path in rel_paths if not artifact_exists(rel_path)]
            return {
                "status": "repo-local verified" if not missing else "draft only",
                "artifacts": rel_paths,
                "missing": missing,
            }

        hosts = {name: artifact_entry(paths) for name, paths in host_paths.items()}
        markdown_paths = [f"Projects/{slugify(project)}/_index.md", f"Projects/{slugify(project)}/hot.md"]
        canvas_path = f"Projects/{slugify(project)}/views/project-map.canvas"
        base_path = f"Projects/{slugify(project)}/views/project-notes.base"
        obsidian_surfaces = {
            "Markdown notes": {
                "status": "repo-local verified" if all((self.vault / path).exists() for path in markdown_paths) else "blocked",
                "artifacts": markdown_paths,
            },
            "Canvas": {
                "status": "repo-local verified" if (self.vault / canvas_path).exists() else "draft only",
                "artifacts": [canvas_path],
                "notes": "Generated JSON Canvas file is structurally present; live Obsidian rendering is not verified by this smoke.",
            },
            "Base": {
                "status": "repo-local verified" if (self.vault / base_path).exists() else "draft only",
                "artifacts": [base_path],
                "notes": "Generated Obsidian Base file is structurally present; live Obsidian rendering is not verified by this smoke.",
            },
        }
        transports = {
            "filesystem": {
                "status": "repo-local verified" if transport["available"]["filesystem"]["available"] else "blocked",
                "detail": transport["available"]["filesystem"],
            },
            "Obsidian CLI": {
                "status": "live verified" if transport["available"]["cli"]["state"] == "ready" else "blocked",
                "detail": transport["available"]["cli"],
            },
            "Obsidian Local REST": {
                "status": "live verified" if transport["available"]["mcp_obsidian"]["available"] else "blocked",
                "detail": transport["available"]["mcp_obsidian"],
            },
        }
        matrix = {
            "hosts": hosts,
            "os": {
                "Windows": {
                    "status": "repo-local verified" if os.name == "nt" else "draft only",
                    "notes": "Current automated smoke ran on Windows." if os.name == "nt" else "Not verified in this run.",
                },
                "macOS": {
                    "status": "draft only",
                    "notes": "macOS shell scripts and docs are present, but this smoke did not run on macOS.",
                },
            },
            "transports": transports,
            "obsidian_surfaces": obsidian_surfaces,
        }
        artifacts = sorted(
            {
                rel_path
                for paths in host_paths.values()
                for rel_path in paths
                if artifact_exists(rel_path)
            }
            | {
                rel_path
                for rel_path in [*markdown_paths, canvas_path, base_path]
                if (self.vault / rel_path).exists()
            }
        )
        host_ready = all(item["status"] == "repo-local verified" for item in hosts.values())
        surface_ready = all(item["status"] == "repo-local verified" for item in obsidian_surfaces.values())
        passed = host_ready and surface_ready and not artifact_result["missing"] and not artifact_result["mismatches"]
        evidence = {
            "passed": passed,
            "commands": [
                "verify repo-local adapter artifacts",
                "verify vault host-config artifacts",
                "verify generated Markdown, Canvas, and Base artifacts",
                "read current transport availability without persisting transport metadata",
            ],
            "matrix": matrix,
            "artifacts": artifacts,
            "notes": "Support matrix smoke records repo-local coverage and current live transport status. It does not claim live host registration or live Obsidian Canvas/Base rendering.",
        }
        record = self.release_evidence_record(project, "support_matrix_gate", evidence)
        return {
            "project": slugify(project),
            "gate": "support_matrix_gate",
            "passed": passed,
            "evidence": evidence,
            "record": record,
        }

    def release_smoke_path(self, project: str, level: str) -> Path:
        return self.project_root(project) / ".vault-meta" / "release" / f"{level}-smoke.json"

    def read_release_smoke(self, project: str, level: str) -> dict[str, Any]:
        path = self.release_smoke_path(project, level)
        if not path.exists():
            return {"passed": False, "actual": "missing", "path": normalize_rel(path.relative_to(self.vault))}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "passed": False,
                "actual": "invalid",
                "path": normalize_rel(path.relative_to(self.vault)),
                "reason": str(exc),
            }
        return {
            "passed": bool(data.get("passed")),
            "actual": "passed" if data.get("passed") else "failed",
            "path": normalize_rel(path.relative_to(self.vault)),
            "detail": data,
        }

    def release_smoke(self, project: str, level: str = "environment") -> dict[str, Any]:
        if level != "environment":
            raise ValueError(f"unsupported release smoke level: {level}")
        root = self.project_root(project)
        smoke_path = self.release_smoke_path(project, level)
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        transport = self.transport_detect(project, persist=True)
        checks: list[dict[str, Any]] = []
        cli_ready = bool(transport["available"]["cli"]["available"])
        rest_ready = bool(transport["available"]["mcp_obsidian"]["available"])
        cli_path = str(transport["available"]["cli"].get("path") or "")
        rest_url = str(transport["available"]["mcp_obsidian"].get("url") or "")
        probe_note = root / ".vault-meta" / "release" / "environment-smoke-probe.md"
        probe_note.parent.mkdir(parents=True, exist_ok=True)
        if not probe_note.exists():
            probe_note.write_text("# Environment Smoke Probe\n", encoding="utf-8")
        nonce = uuid.uuid4().hex
        probe_content = (
            f"\n\n## {datetime.now().strftime('%Y-%m-%d')}: Environment transport smoke\n\n"
            f"- Nonce: {nonce}\n"
            "- Result: Local REST append smoke completed.\n"
        )
        checks.append({"name": "obsidian_cli_ready", "passed": cli_ready, "detail": transport["available"]["cli"]})
        checks.append({"name": "local_rest_ready", "passed": rest_ready, "detail": transport["available"]["mcp_obsidian"]})
        if cli_ready:
            try:
                self.obsidian_cli_read(project, f"Projects/{slugify(project)}/_index.md")
                checks.append({"name": "cli_read", "passed": True})
            except Exception as exc:
                checks.append({"name": "cli_read", "passed": False, "detail": str(exc)})
            try:
                result = self.obsidian_cli_search(project, project, limit=1)
                checks.append({"name": "cli_search", "passed": bool(result.get("results")), "detail": result})
            except Exception as exc:
                checks.append({"name": "cli_search", "passed": False, "detail": str(exc)})
        else:
            checks.append({"name": "cli_read", "passed": False, "detail": "Obsidian CLI unavailable"})
            checks.append({"name": "cli_search", "passed": False, "detail": "Obsidian CLI unavailable"})
        if rest_ready:
            try:
                self.obsidian_rest_append(normalize_rel(probe_note.relative_to(self.vault)), probe_content)
                checks.append({"name": "rest_append_probe", "passed": True, "path": normalize_rel(probe_note.relative_to(self.vault))})
            except Exception as exc:
                checks.append({"name": "rest_append_probe", "passed": False, "detail": str(exc)})
        else:
            checks.append({"name": "rest_append_probe", "passed": False, "detail": "Obsidian Local REST unavailable"})
        try:
            probe_text = probe_note.read_text(encoding="utf-8")
            checks.append({"name": "write_verify", "passed": nonce in probe_text, "path": normalize_rel(probe_note.relative_to(self.vault))})
        except Exception as exc:
            checks.append({"name": "write_verify", "passed": False, "detail": str(exc)})
        result = {
            "project": project,
            "release_level": level,
            "smoked_at": now_iso(),
            "cli_path": cli_path,
            "rest_url": rest_url,
            "probe_note_path": normalize_rel(probe_note.relative_to(self.vault)),
            "probe_nonce": nonce,
            "passed": all(item["passed"] for item in checks),
            "checks": checks,
            "transport": transport,
        }
        smoke_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    def project_find(self, repo_path: str | None = None, project: str | None = None) -> dict[str, Any]:
        for root in self.project_roots():
            index = root / "_index.md"
            if not index.exists():
                continue
            note = self.read_note(index)
            note_project = str(note.frontmatter.get("project") or root.name)
            note_repo = str(note.frontmatter.get("repo") or "")
            if project and note_project.lower() != project.lower():
                continue
            if repo_path:
                requested_path = Path(repo_path).expanduser().resolve()
                try:
                    stored_path = Path(note_repo).expanduser().resolve()
                except OSError:
                    stored_path = Path(note_repo)
                if requested_path != stored_path and stored_path not in requested_path.parents:
                    continue
            return {
                "project": note_project,
                "path": normalize_rel(index.relative_to(self.vault)),
                "status": note.frontmatter.get("status", "unknown"),
                "repo": note_repo,
                "hot": f"Projects/{root.name}/hot.md",
            }
        raise FileNotFoundError("project not found")

    def read_pilot_events(self, project: str) -> list[dict[str, Any]]:
        path = self.project_root(project) / ".vault-meta" / "pilot" / "events.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def check_http_endpoint(self, url: str) -> tuple[bool, str]:
        request = urllib.request.Request(url, method="GET")
        api_key = os.environ.get("PROJECT_KB_OBSIDIAN_REST_API_KEY", "")
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        try:
            with self.obsidian_rest_urlopen(request, timeout=0.5) as response:
                return 200 <= response.status < 500, f"HTTP {response.status}"
        except urllib.error.HTTPError as exc:
            if 200 <= exc.code < 500:
                return True, f"HTTP {exc.code}"
            return False, f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            return False, str(exc.reason)
        except Exception as exc:
            return False, str(exc)

    def obsidian_rest_ssl_context(self, url: str) -> ssl.SSLContext | None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() != "https":
            return None
        ca_cert = os.environ.get("PROJECT_KB_OBSIDIAN_REST_CA_CERT", "")
        if ca_cert:
            return ssl.create_default_context(cafile=ca_cert)
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
            return ssl._create_unverified_context()
        return None

    def obsidian_rest_urlopen(self, request: urllib.request.Request, timeout: float):
        context = self.obsidian_rest_ssl_context(request.full_url)
        if context is None:
            return urllib.request.urlopen(request, timeout=timeout)
        return urllib.request.urlopen(request, timeout=timeout, context=context)

    def obsidian_rest_enabled(self) -> bool:
        rest_url = os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/")
        available, _ = self.check_http_endpoint(rest_url)
        return available

    def obsidian_rest_read(self, path: str, section: str | None = None) -> dict[str, Any]:
        base = os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/").rstrip("/")
        api_key = os.environ.get("PROJECT_KB_OBSIDIAN_REST_API_KEY", "")
        encoded_path = urllib.parse.quote(path.replace("\\", "/"), safe="/")
        request = urllib.request.Request(f"{base}/vault/{encoded_path}", method="GET")
        request.add_header("Accept", "application/vnd.olrapi.note+json")
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        with self.obsidian_rest_urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"content": payload.get("content", ""), "frontmatter": payload.get("frontmatter", {})}

    def obsidian_rest_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        base = os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/").rstrip("/")
        api_key = os.environ.get("PROJECT_KB_OBSIDIAN_REST_API_KEY", "")
        encoded_query = urllib.parse.quote(query, safe="")
        request = urllib.request.Request(
            f"{base}/search/simple/?query={encoded_query}&contextLength=100",
            data=b"",
            method="POST",
        )
        request.add_header("Accept", "application/json")
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        with self.obsidian_rest_urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results = []
        for item in payload[: max(1, min(limit, 5))]:
            path = str(item.get("filename") or "")
            title = Path(path).stem
            note_type = "unknown"
            try:
                note = self.read_note(self.resolve_note_path(path))
                title = title_from_body(note.body, title)
                note_type = str(note.frontmatter.get("type") or "unknown")
            except Exception:
                pass
            snippet = ""
            matches = item.get("matches") or []
            if matches:
                snippet = str(matches[0].get("context") or "")
            results.append(
                {
                    "path": normalize_rel(path),
                    "title": title,
                    "type": note_type,
                    "score": float(item.get("score") or 0.0),
                    "snippet": snippet,
                }
            )
        return {"results": results}

    def obsidian_rest_patch_frontmatter(self, path: str, field: str, value: str) -> None:
        base = os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/").rstrip("/")
        api_key = os.environ.get("PROJECT_KB_OBSIDIAN_REST_API_KEY", "")
        encoded_path = urllib.parse.quote(path.replace("\\", "/"), safe="/")
        data = json.dumps(value).encode("utf-8")
        request = urllib.request.Request(f"{base}/vault/{encoded_path}", data=data, method="PATCH")
        request.add_header("Content-Type", "application/json")
        request.add_header("Target-Type", "frontmatter")
        request.add_header("Target", field)
        request.add_header("Operation", "replace")
        request.add_header("Create-Target-If-Missing", "true")
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        with self.obsidian_rest_urlopen(request, timeout=5):
            return None

    def obsidian_rest_append(self, path: str, content: str) -> None:
        base = os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/").rstrip("/")
        api_key = os.environ.get("PROJECT_KB_OBSIDIAN_REST_API_KEY", "")
        encoded_path = urllib.parse.quote(path.replace("\\", "/"), safe="/")
        request = urllib.request.Request(
            f"{base}/vault/{encoded_path}",
            data=content.encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "text/markdown")
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        with self.obsidian_rest_urlopen(request, timeout=5):
            return None

    def obsidian_rest_create_note(self, path: str, content: str) -> None:
        base = os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/").rstrip("/")
        api_key = os.environ.get("PROJECT_KB_OBSIDIAN_REST_API_KEY", "")
        encoded_path = urllib.parse.quote(path.replace("\\", "/"), safe="/")
        request = urllib.request.Request(
            f"{base}/vault/{encoded_path}",
            data=content.encode("utf-8"),
            method="PUT",
        )
        request.add_header("Content-Type", "text/markdown")
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        with self.obsidian_rest_urlopen(request, timeout=5):
            return None

    def resolve_obsidian_cli_path(self) -> str:
        if "PROJECT_KB_OBSIDIAN_CLI_PATH" in os.environ:
            configured = os.environ.get("PROJECT_KB_OBSIDIAN_CLI_PATH", "")
            return configured if configured and Path(configured).exists() else ""
        direct = shutil.which("obsidian")
        if direct:
            return direct
        candidates = [
            Path(r"D:\soft\Obsidian\Obsidian.com"),
            Path(r"D:\soft\Obsidian\Obsidian.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return ""

    def probe_obsidian_cli(self) -> tuple[bool, str]:
        cli_path = self.resolve_obsidian_cli_path()
        if not cli_path:
            return False, "obsidian executable not found"
        result = subprocess.run([cli_path, "--help"], text=True, capture_output=True, timeout=10, check=False)
        output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
        if "not enabled" in output.lower():
            return False, output
        if result.returncode == 0:
            return True, "obsidian help succeeded"
        return False, output or f"obsidian help failed with exit code {result.returncode}"

    def obsidian_cli_command(self, *args: str) -> list[str]:
        cli_path = self.resolve_obsidian_cli_path()
        if not cli_path:
            raise FileNotFoundError("obsidian executable not found")
        return [cli_path, f"vault={self.vault.name}", *args]

    def search(self, project: str, query: str, limit: int = 5, types: list[str] | None = None) -> dict[str, Any]:
        project_note = None
        index = self.project_root(project) / "_index.md"
        if index.exists():
            project_note = self.read_note(index)
        transport = str(project_note.frontmatter.get("transport") or "") if project_note else ""
        obsidian_cli_available, _ = self.probe_obsidian_cli()
        if transport == "mcp_obsidian" and self.obsidian_rest_enabled() and not types:
            try:
                return self.obsidian_rest_search(query, max(1, min(limit, 5)))
            except Exception:
                pass
        if transport == "cli" and obsidian_cli_available and not types:
            try:
                return self.obsidian_cli_search(project, query, max(1, min(limit, 5)), types)
            except Exception:
                pass
        terms = [term.lower() for term in re.findall(r"[\w.-]+", query) if term]
        results = []
        for note in self.iter_notes(project):
            note_type = note.frontmatter.get("type")
            if types and note_type not in types:
                continue
            path_text = note.rel_path.lower()
            title_text = title_from_body(note.body, Path(note.rel_path).stem).lower()
            body_text = note.body.lower()
            matched_terms = sum(1 for term in terms if term in path_text or term in title_text or term in body_text)
            score = sum(
                path_text.count(term) * 3 + title_text.count(term) * 4 + body_text.count(term)
                for term in terms
            )
            if score <= 0:
                continue
            snippet = self.snippet(note.body, terms)
            results.append(
                {
                    "path": note.rel_path,
                    "title": title_from_body(note.body, Path(note.rel_path).stem),
                    "type": note_type,
                    "score": round(score / max(len(terms), 1), 3),
                    "_matched_terms": matched_terms,
                    "snippet": snippet,
                }
            )
        results.sort(key=lambda item: (-item["_matched_terms"], -item["score"], item["path"]))
        bounded = results[: max(1, min(limit, 5))]
        for item in bounded:
            item.pop("_matched_terms", None)
        return {"results": bounded}

    def obsidian_cli_search(self, project: str, query: str, limit: int = 5, types: list[str] | None = None) -> dict[str, Any]:
        command = self.obsidian_cli_command("search", f"query={query}", f"limit={limit}")
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "obsidian search failed"
            raise RuntimeError(stderr)
        entries = []
        for line in result.stdout.splitlines():
            text = line.strip()
            if not text:
                continue
            path = text
            if not path.endswith(".md"):
                continue
            normalized = normalize_rel(path)
            title = Path(normalized).stem
            note_type = "unknown"
            try:
                note = self.read_note(self.resolve_note_path(normalized))
                title = title_from_body(note.body, title)
                note_type = str(note.frontmatter.get("type") or "unknown")
            except Exception:
                pass
            entries.append(
                {
                    "path": normalized,
                    "title": title,
                    "type": note_type,
                    "score": 1.0,
                    "snippet": f"Matched through obsidian CLI search: {query}",
                }
            )
        return {"results": entries[: max(1, min(limit, 5))]}

    def read(self, path: str, section: str | None = None) -> dict[str, Any]:
        abs_path = self.resolve_note_path(path)
        note = self.read_note(abs_path)
        transport = str(note.frontmatter.get("transport") or "")
        obsidian_cli_available, _ = self.probe_obsidian_cli()
        if transport == "mcp_obsidian" and self.obsidian_rest_enabled():
            try:
                rest_result = self.obsidian_rest_read(note.rel_path, section)
                content = section_from_body(rest_result["content"], section) if section else rest_result["content"].strip()
                if section and not content:
                    raise ValueError(f"section not found: {section}")
                return {"path": note.rel_path, "content": content, "frontmatter": rest_result["frontmatter"]}
            except Exception:
                pass
        if transport == "cli" and obsidian_cli_available:
            try:
                cli_result = self.obsidian_cli_read(str(note.frontmatter.get("project") or ""), note.rel_path)
                content = section_from_body(cli_result["content"], section) if section else cli_result["content"].strip()
                if section and not content:
                    raise ValueError(f"section not found: {section}")
                return {"path": note.rel_path, "content": content, "frontmatter": cli_result["frontmatter"]}
            except Exception:
                pass
        content = section_from_body(note.body, section) if section else note.body.strip()
        if section and not content:
            raise ValueError(f"section not found: {section}")
        return {"path": note.rel_path, "content": content, "frontmatter": note.frontmatter}

    def obsidian_cli_read(self, project: str, path: str) -> dict[str, Any]:
        command = self.obsidian_cli_command("read", f"path={path}")
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "obsidian read failed"
            raise RuntimeError(stderr)
        content = result.stdout.strip()
        note = self.read_note(self.resolve_note_path(path))
        return {"content": content, "frontmatter": note.frontmatter}

    def append_log(self, project: str, payload: dict[str, Any], actor: str = "cli") -> dict[str, Any]:
        self.reject_secret_payload(payload)
        self.require_log_provenance(payload)
        root = self.project_root(project)
        month = datetime.now().strftime("%Y-%m")
        log_path = root / "logs" / f"{month}.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        title = payload.get("title") or "Untitled Task"
        entry = self.format_log_entry(payload)
        project_index = root / "_index.md"
        project_note = self.read_note(project_index) if project_index.exists() else None
        transport = str(project_note.frontmatter.get("transport") or "") if project_note else ""
        obsidian_cli_available, _ = self.probe_obsidian_cli()
        with self.lock_file(log_path):
            log_exists = log_path.exists()
            if log_exists:
                current = log_path.read_text(encoding="utf-8")
            else:
                current = self.log_note(project, month)
            updated = current.rstrip() + "\n\n" + entry + "\n"
            validation_errors = self.validate_note_text(log_path, updated)
            if validation_errors:
                detail = "; ".join(error["message"] for error in validation_errors)
                raise ValueError(f"target validation failed for {normalize_rel(log_path.relative_to(self.vault))}: {detail}")
            if transport == "mcp_obsidian" and self.obsidian_rest_enabled() and log_exists:
                try:
                    self.obsidian_rest_append(normalize_rel(log_path.relative_to(self.vault)), "\n\n" + entry)
                    log_path.write_text(updated, encoding="utf-8")
                except Exception:
                    log_path.write_text(updated, encoding="utf-8")
            elif transport == "mcp_obsidian" and self.obsidian_rest_enabled():
                try:
                    self.obsidian_rest_create_note(normalize_rel(log_path.relative_to(self.vault)), updated)
                    log_path.write_text(updated, encoding="utf-8")
                except Exception:
                    log_path.write_text(updated, encoding="utf-8")
            elif transport == "cli" and obsidian_cli_available and log_exists:
                try:
                    self.obsidian_cli_append(project, normalize_rel(log_path.relative_to(self.vault)), "\n\n" + entry)
                    log_path.write_text(updated, encoding="utf-8")
                except Exception:
                    log_path.write_text(updated, encoding="utf-8")
            elif transport == "cli" and obsidian_cli_available:
                try:
                    self.obsidian_cli_create_note(project, normalize_rel(log_path.relative_to(self.vault)), updated)
                    log_path.write_text(updated, encoding="utf-8")
                except Exception:
                    log_path.write_text(updated, encoding="utf-8")
            else:
                log_path.write_text(updated, encoding="utf-8")
            self.audit(project, actor, "append_log", log_path, payload.get("commit"))
        return {"path": normalize_rel(log_path.relative_to(self.vault)), "appended": True}

    def obsidian_cli_append(self, project: str, path: str, content: str) -> None:
        command = self.obsidian_cli_command("append", f"path={path}", f"content={content}")
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "obsidian append failed"
            raise RuntimeError(stderr)

    def validate(self, project: str) -> dict[str, Any]:
        errors = []
        warnings = []
        root = self.project_root(project)
        if not root.exists():
            errors.append({"path": f"Projects/{project}", "message": "project root missing"})
            return {"project": project, "errors": errors, "warnings": warnings}
        for note in self.iter_notes(project):
            note_type = note.frontmatter.get("type")
            expected_type = self.expected_note_type(note.path)
            if contains_secret(note.raw):
                errors.append({"path": note.rel_path, "message": "secret-like content"})
            schema_version = note.frontmatter.get("schema_version")
            if schema_version is not None and schema_version != SCHEMA_VERSION:
                errors.append({"path": note.rel_path, "message": f"unsupported schema_version: {schema_version}"})
            if not note_type and expected_type:
                errors.append({"path": note.rel_path, "message": "missing required frontmatter field: type"})
            if note_type and note_type not in VALID_TYPES:
                errors.append({"path": note.rel_path, "message": f"invalid type: {note_type}"})
            if note_type and expected_type and note_type != expected_type:
                errors.append({"path": note.rel_path, "message": f"type does not match path: expected {expected_type}"})
            status = note.frontmatter.get("status")
            if status and status not in VALID_STATUSES:
                errors.append({"path": note.rel_path, "message": f"invalid status: {status}"})
            required_type = str(note_type or expected_type or "")
            for field in FRONTMATTER_REQUIRED.get(required_type, []):
                if field not in note.frontmatter:
                    errors.append({"path": note.rel_path, "message": f"missing required frontmatter field: {field}"})
            for section in SECTIONS_REQUIRED.get(required_type, []):
                if not self.has_section(note.body, section):
                    errors.append({"path": note.rel_path, "message": f"missing required section: {section}"})
            for target in self.find_wikilinks(note.body):
                if not self.wikilink_exists(note.path, target):
                    errors.append({"path": note.rel_path, "message": f"broken wikilink: {target}"})
            for marker in GENERATED_NOISE_MARKERS:
                if marker in note.raw:
                    errors.append({"path": note.rel_path, "message": f"generated-noise marker: {marker}"})
            self.validate_repo_and_sources(note, errors, warnings)
        self.validate_log_names(project, errors)
        return {"project": project, "errors": errors, "warnings": warnings}

    def validate_note_text(self, path: Path, raw: str) -> list[dict[str, str]]:
        frontmatter, body = parse_frontmatter(raw)
        rel_path = normalize_rel(path.relative_to(self.vault))
        note_type = frontmatter.get("type")
        expected_type = self.expected_note_type(path)
        errors: list[dict[str, str]] = []
        if contains_secret(raw):
            errors.append({"path": rel_path, "message": "secret-like content"})
        schema_version = frontmatter.get("schema_version")
        if schema_version is not None and schema_version != SCHEMA_VERSION:
            errors.append({"path": rel_path, "message": f"unsupported schema_version: {schema_version}"})
        if not note_type and expected_type:
            errors.append({"path": rel_path, "message": "missing required frontmatter field: type"})
        if note_type and note_type not in VALID_TYPES:
            errors.append({"path": rel_path, "message": f"invalid type: {note_type}"})
        if note_type and expected_type and note_type != expected_type:
            errors.append({"path": rel_path, "message": f"type does not match path: expected {expected_type}"})
        status = frontmatter.get("status")
        if status and status not in VALID_STATUSES:
            errors.append({"path": rel_path, "message": f"invalid status: {status}"})
        required_type = str(note_type or expected_type or "")
        for field in FRONTMATTER_REQUIRED.get(required_type, []):
            if field not in frontmatter:
                errors.append({"path": rel_path, "message": f"missing required frontmatter field: {field}"})
        for section in SECTIONS_REQUIRED.get(required_type, []):
            if not self.has_section(body, section):
                errors.append({"path": rel_path, "message": f"missing required section: {section}"})
        for target in self.find_wikilinks(body):
            if not self.wikilink_exists(path, target):
                errors.append({"path": rel_path, "message": f"broken wikilink: {target}"})
        for marker in GENERATED_NOISE_MARKERS:
            if marker in raw:
                errors.append({"path": rel_path, "message": f"generated-noise marker: {marker}"})
        return errors

    def status(self, project: str) -> dict[str, Any]:
        notes = list(self.iter_notes(project))
        validation = self.validate(project)
        index = self.project_root(project) / "_index.md"
        project_note = self.read_note(index) if index.exists() else None
        counts: dict[str, int] = {}
        for note in notes:
            note_type = str(note.frontmatter.get("type") or "unknown")
            counts[note_type] = counts.get(note_type, 0) + 1
        return {
            "project": project,
            "status": str(project_note.frontmatter.get("status") or "") if project_note else "",
            "path": normalize_rel(index.relative_to(self.vault)) if project_note else "",
            "vault": str(self.vault),
            "repo": str(project_note.frontmatter.get("repo") or "") if project_note else "",
            "hot": f"Projects/{slugify(project)}/hot.md",
            "transport": str(project_note.frontmatter.get("transport") or "") if project_note else "",
            "notes": len(notes),
            "types": counts,
            "errors": len(validation["errors"]),
            "warnings": len(validation["warnings"]),
        }

    def transport_detect(self, project: str, persist: bool = True) -> dict[str, Any]:
        root = self.project_root(project)
        project_kb_cli_path = Path(__file__).resolve().parents[1] / "scripts" / "kb.py"
        mcp_path = Path(__file__).resolve().parents[1] / "scripts" / "kb_mcp.py"
        obsidian_path = self.resolve_obsidian_cli_path()
        obsidian_cli_available, obsidian_cli_reason = self.probe_obsidian_cli()
        if obsidian_cli_available:
            obsidian_cli_state = "ready"
        elif obsidian_path:
            obsidian_cli_state = "disabled"
        else:
            obsidian_cli_state = "missing"
        rest_url = os.environ.get("PROJECT_KB_OBSIDIAN_REST_URL", "https://127.0.0.1:27124/")
        rest_available, rest_reason = self.check_http_endpoint(rest_url)
        filesystem_available = root.exists() and os.access(root, os.R_OK | os.W_OK)
        fallback_chain = ["cli", "mcp_obsidian", "filesystem"]
        available = {
            "cli": {
                "available": obsidian_cli_available,
                "state": obsidian_cli_state,
                "path": obsidian_path,
                "reason": obsidian_cli_reason,
            },
            "mcp_obsidian": {
                "available": rest_available,
                "url": rest_url,
                "checked": True,
                "reason": rest_reason,
            },
            "filesystem": {
                "available": filesystem_available,
                "path": str(root),
                "reason": "project root is readable and writable" if filesystem_available else "project root missing or not writable",
            },
        }
        preferred = next((name for name in fallback_chain if available[name]["available"]), "filesystem")
        result = {
            "preferred": preferred,
            "fallback_chain": fallback_chain,
            "available": available,
            "evidence": {
                "obsidian_cli": {
                    "available": obsidian_cli_available,
                    "state": obsidian_cli_state,
                    "path": obsidian_path,
                    "reason": obsidian_cli_reason,
                },
                "project_kb_cli": {
                    "available": project_kb_cli_path.exists(),
                    "path": str(project_kb_cli_path),
                    "reason": "bundled Project KB CLI script" if project_kb_cli_path.exists() else "scripts/kb.py missing",
                },
                "obsidian_local_rest_api": {
                    "available": rest_available,
                    "url": rest_url,
                    "checked": True,
                    "reason": rest_reason,
                },
                "project_kb_mcp": {
                    "available": mcp_path.exists(),
                    "path": str(mcp_path),
                    "reason": "bundled stdio MCP facade" if mcp_path.exists() else "scripts/kb_mcp.py missing",
                },
            },
            "last_checked_at": now_iso(),
        }
        if persist:
            meta = root / ".vault-meta" / "transport.json"
            meta.parent.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    def doctor(self, project: str, persist_transport: bool = False) -> dict[str, Any]:
        safe_tools = [
            "kb.project_find",
            "kb.search",
            "kb.retrieve",
            "kb.read",
            "kb.append_log",
            "kb.check_staleness",
            "kb.project_create",
            "kb.create_decision",
            "kb.update_project_status",
            "kb.update_frontmatter_field",
        ]
        checks = []
        validation = self.validate(project)
        checks.append({"name": "validate", "passed": not validation["errors"], "detail": validation})
        try:
            project_info = self.project_find(project=project)
            self.read(project_info["hot"])
            checks.append({"name": "read_note", "passed": True, "detail": project_info["hot"]})
        except Exception as exc:
            checks.append({"name": "read_note", "passed": False, "detail": str(exc)})
        try:
            result = self.search(project, "project", limit=1)
            checks.append({"name": "search_note", "passed": len(result["results"]) > 0, "detail": result})
        except Exception as exc:
            checks.append({"name": "search_note", "passed": False, "detail": str(exc)})
        unsafe = [tool for tool in safe_tools if any(word in tool for word in ["delete", "overwrite", "bulk"])]
        checks.append({"name": "safe_surface", "passed": not unsafe, "detail": {"unsafe": unsafe}})
        transport = self.transport_detect(project, persist=persist_transport)
        transport_ready = (
            transport["available"]["filesystem"]["available"]
            and transport["evidence"]["project_kb_cli"]["available"]
            and transport["evidence"]["project_kb_mcp"]["available"]
        )
        checks.append({"name": "transport", "passed": transport_ready, "detail": transport})
        status = "ready" if all(item["passed"] for item in checks) else "degraded"
        return {"project": project, "status": status, "checks": checks, "safe_tools": safe_tools}

    def release_check(
        self,
        project: str,
        level: str = "engineering",
        commit: str | None = None,
        require_artifacts: bool = False,
    ) -> dict[str, Any]:
        allowed = {"engineering", "environment", "pilot", "full", "repo-wide"}
        if level not in allowed:
            raise ValueError(f"unsupported release level: {level}")
        if level == "repo-wide":
            project_kb_full = self.release_check(project, "full", commit=commit, require_artifacts=require_artifacts)
            repo_wide = self.repo_wide_release_evidence_check(project)
            checks = [
                {
                    "name": "project_kb_full",
                    "passed": project_kb_full["status"] == "ready",
                    "required_for": ["repo-wide"],
                    "detail": project_kb_full,
                },
                *[
                    {
                        "name": item["name"],
                        "passed": item["passed"],
                        "required_for": ["repo-wide"],
                        "actual": item["actual"],
                        "detail": item["detail"],
                    }
                    for item in repo_wide["checks"]
                ],
            ]
            return {
                "project": project,
                "release_level": level,
                "target_release": "repo-wide-end-user-release",
                "status": "ready" if all(item["passed"] for item in checks) else "blocked",
                "checks": checks,
                "metrics": project_kb_full["metrics"],
            }
        if level == "full":
            engineering = self.release_check(project, "engineering", commit=commit, require_artifacts=require_artifacts)
            environment = self.release_check(project, "environment")
            pilot = self.release_check(project, "pilot")
            checks = [
                {"name": "engineering", "passed": engineering["status"] == "ready", "detail": engineering},
                {"name": "environment", "passed": environment["status"] == "ready", "detail": environment},
                {"name": "pilot", "passed": pilot["status"] == "ready", "detail": pilot},
            ]
            return {
                "project": project,
                "release_level": level,
                "status": "ready" if all(item["passed"] for item in checks) else "blocked",
                "checks": checks,
                "metrics": pilot["metrics"],
            }
        doctor = self.doctor(project)
        transport = next(item["detail"] for item in doctor["checks"] if item["name"] == "transport")
        metrics = self.compute_metrics(project)
        unsafe_tools = [tool for tool in doctor["safe_tools"] if any(word in tool for word in ["delete", "overwrite", "bulk"])]
        checks: list[dict[str, Any]] = [
            {
                "name": "doctor",
                "passed": doctor["status"] == "ready",
                "required_for": ["engineering", "environment", "pilot"],
                "detail": doctor,
            },
            {
                "name": "dangerous_surface_absent",
                "passed": not unsafe_tools,
                "required_for": ["engineering", "environment", "pilot"],
                "detail": {"unsafe_tools": unsafe_tools},
            },
        ]
        if level == "engineering":
            stale_result = self.stale(project, commit) if commit else {"stale": []}
            checks.append(
                {
                    "name": "stale_notes",
                    "passed": not stale_result["stale"],
                    "required_for": ["engineering"],
                    "actual": len(stale_result["stale"]) if commit else "not checked",
                    "detail": stale_result,
                }
            )
            artifact_result = self.release_artifact_check(project) if require_artifacts else {
                "passed": True,
                "missing": [],
                "mismatches": [],
                "reason": "not required for this check",
            }
            checks.append(
                {
                    "name": "release_artifacts",
                    "passed": bool(artifact_result["passed"]),
                    "required_for": ["engineering"],
                    "missing": artifact_result["missing"],
                    "mismatches": artifact_result["mismatches"],
                    "detail": artifact_result,
                }
            )
            checks.append(
                {
                    "name": "pilot_not_required",
                    "passed": True,
                    "required_for": ["engineering"],
                    "detail": "10-task pilot is a product validation gate, not a v0.1 engineering gate",
                }
            )
        if level == "environment":
            smoke = self.read_release_smoke(project, "environment")
            checks.extend(
                [
                    {
                        "name": "obsidian_cli_ready",
                        "passed": bool(transport["available"]["cli"]["available"]),
                        "required_for": ["environment", "pilot"],
                        "actual": transport["available"]["cli"]["state"],
                        "detail": transport["available"]["cli"],
                    },
                    {
                        "name": "local_rest_ready",
                        "passed": bool(transport["available"]["mcp_obsidian"]["available"]),
                        "required_for": ["environment", "pilot"],
                        "actual": transport["available"]["mcp_obsidian"]["reason"],
                        "detail": transport["available"]["mcp_obsidian"],
                    },
                    {
                        "name": "transport_smoke",
                        "passed": bool(smoke["passed"]),
                        "required_for": ["environment"],
                        "actual": smoke["actual"],
                        "detail": smoke,
                    },
                ]
            )
        if level == "pilot":
            threshold_failures = {
                name: detail for name, detail in metrics["thresholds"].items() if not detail["passed"]
            }
            checks.extend(
                [
                    {
                        "name": "ten_task_pilot",
                        "passed": metrics["tasks"] >= 10,
                        "required_for": ["pilot"],
                        "target": 10,
                        "actual": metrics["tasks"],
                    },
                    {
                        "name": "pilot_thresholds",
                        "passed": not threshold_failures,
                        "required_for": ["pilot"],
                        "detail": metrics["thresholds"],
                    },
                ]
            )
        status = "ready" if all(item["passed"] for item in checks) else "blocked"
        return {
            "project": project,
            "release_level": level,
            "status": status,
            "checks": checks,
            "metrics": metrics if level == "pilot" else None,
        }

    def release_diagnose(self, project: str, level: str = "environment") -> dict[str, Any]:
        if level != "environment":
            raise ValueError(f"unsupported release diagnose level: {level}")
        check = self.release_check(project, level)
        local_rest_plugin = self.obsidian_local_rest_plugin_status()
        raw_blocked = [item for item in check["checks"] if not item["passed"]]
        blocked = []
        for item in raw_blocked:
            name = item["name"]
            detail = item.get("detail") or {}
            if name == "obsidian_cli_ready":
                blocked.append(
                    {
                        "name": name,
                        "state": str(detail.get("state") or "missing"),
                        "expected": "ready",
                        "observed": str(detail.get("reason") or item.get("actual") or ""),
                        "path": str(detail.get("path") or ""),
                    }
                )
            elif name == "local_rest_ready":
                observed = str(detail.get("reason") or item.get("actual") or "")
                blocked.append(
                    {
                        "name": name,
                        "state": "unreachable" if not detail.get("available") else "ready",
                        "expected": "reachable",
                        "observed": observed,
                        "url": str(detail.get("url") or ""),
                        "plugin": local_rest_plugin,
                    }
                )
            elif name == "transport_smoke":
                blocked.append(
                    {
                        "name": name,
                        "state": str(item.get("actual") or "unknown"),
                        "expected": "passed",
                        "observed": str((detail.get("reason") if isinstance(detail, dict) else "") or "environment smoke evidence not passed"),
                        "path": str(detail.get("path") or ""),
                    }
                )
            else:
                blocked.append(
                    {
                        "name": name,
                        "state": "failed",
                        "expected": "passed",
                        "observed": json.dumps(item.get("detail"), ensure_ascii=False),
                    }
                )
        remediation: list[dict[str, str]] = []
        blocked_names = {item["name"] for item in blocked}
        cli_detail = next((item for item in blocked if item["name"] == "obsidian_cli_ready"), {})
        if "obsidian_cli_ready" in blocked_names:
            state = str(cli_detail.get("state") or "missing")
            if state == "disabled":
                remediation.append(
                    {
                        "id": "enable_obsidian_cli",
                        "action": "Open Obsidian Settings > General > Advanced and enable Command line interface, then rerun the verification commands.",
                        "verify_command": "obsidian --help",
                    }
                )
            else:
                remediation.append(
                    {
                        "id": "install_or_expose_obsidian_cli",
                        "action": "Install Obsidian CLI or add the Obsidian executable to PATH so `obsidian --help` works.",
                        "verify_command": "obsidian --help",
                    }
                )
        if "local_rest_ready" in blocked_names:
            plugin_missing = not local_rest_plugin.get("installed")
            plugin_disabled = local_rest_plugin.get("installed") and not local_rest_plugin.get("enabled")
            if plugin_missing:
                action = "Install the Obsidian Local REST API plugin in the current open vault, enable it, configure its API key if required, and confirm the endpoint is reachable."
            elif plugin_disabled:
                action = "Enable the Obsidian Local REST API plugin in the current open vault, configure its API key if required, and confirm the endpoint is reachable."
            else:
                action = "Install and enable the Obsidian Local REST API plugin, configure its API key if required, and confirm the endpoint is reachable."
            remediation.append(
                {
                    "id": "enable_obsidian_local_rest",
                    "action": action,
                    "verify_command": "Invoke-WebRequest -UseBasicParsing https://127.0.0.1:27124/ -SkipCertificateCheck -TimeoutSec 3",
                }
            )
        if "transport_smoke" in blocked_names:
            remediation.append(
                {
                    "id": "run_environment_smoke",
                    "action": "After Obsidian CLI and Local REST are ready, run the environment smoke command to record read/search/write evidence.",
                    "verify_command": f"python scripts/kb.py release smoke --project {project} --level environment",
                }
            )
        if blocked:
            summary_bits = ", ".join(item["name"] for item in blocked)
            summary = f"v0.2-beta blocked: {summary_bits}."
        else:
            summary = "v0.2-beta ready: Obsidian CLI, Local REST, and environment smoke are verified."
        return {
            "project": project,
            "release_level": level,
            "target_version": "v0.2-beta",
            "status": check["status"],
            "summary": summary,
            "blocked_checks": blocked,
            "remediation": remediation,
            "verification_commands": [
                f"python scripts/kb.py release smoke --project {project} --level environment",
                f"python scripts/kb.py release check --project {project} --level environment",
                f"python scripts/kb.py release check --project {project} --level full",
            ],
            "check": check,
        }

    def obsidian_local_rest_plugin_status(self) -> dict[str, Any]:
        plugin_id = "obsidian-local-rest-api"
        status: dict[str, Any] = {
            "id": plugin_id,
            "app_config_path": "",
            "open_vault": "",
            "community_plugins_path": "",
            "plugins_dir": "",
            "installed": False,
            "enabled": False,
            "installed_plugins": [],
            "enabled_plugins": [],
            "reason": "Obsidian app config not found",
        }
        appdata = os.environ.get("APPDATA")
        if not appdata:
            status["reason"] = "APPDATA is not set"
            return status
        config_path = Path(appdata) / "obsidian" / "obsidian.json"
        status["app_config_path"] = str(config_path)
        if not config_path.exists():
            return status
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            status["reason"] = f"Obsidian app config unreadable: {exc}"
            return status
        vaults = config.get("vaults") if isinstance(config, dict) else {}
        open_vault = ""
        if isinstance(vaults, dict):
            for vault in vaults.values():
                if isinstance(vault, dict) and vault.get("open") and vault.get("path"):
                    open_vault = str(vault["path"])
                    break
            if not open_vault:
                for vault in vaults.values():
                    if isinstance(vault, dict) and vault.get("path"):
                        open_vault = str(vault["path"])
                        break
        if not open_vault:
            status["reason"] = "No Obsidian vault path found in app config"
            return status
        vault_path = Path(open_vault).expanduser()
        plugins_dir = vault_path / ".obsidian" / "plugins"
        community_plugins_path = vault_path / ".obsidian" / "community-plugins.json"
        status["open_vault"] = str(vault_path)
        status["plugins_dir"] = str(plugins_dir)
        status["community_plugins_path"] = str(community_plugins_path)
        if plugins_dir.exists():
            try:
                status["installed_plugins"] = sorted(child.name for child in plugins_dir.iterdir() if child.is_dir())
            except OSError:
                status["installed_plugins"] = []
        if community_plugins_path.exists():
            try:
                enabled_plugins = json.loads(community_plugins_path.read_text(encoding="utf-8"))
                if isinstance(enabled_plugins, list):
                    status["enabled_plugins"] = [str(item) for item in enabled_plugins]
            except (OSError, json.JSONDecodeError):
                status["enabled_plugins"] = []
        status["installed"] = plugin_id in status["installed_plugins"]
        status["enabled"] = plugin_id in status["enabled_plugins"]
        if status["installed"] and status["enabled"]:
            status["reason"] = "Local REST plugin is installed and enabled in the current open vault"
        elif status["installed"]:
            status["reason"] = "Local REST plugin is installed but not enabled in the current open vault"
        else:
            status["reason"] = "Local REST plugin is not installed in the current open vault"
        return status

    def release_report(
        self,
        project: str,
        commit: str | None = None,
        require_artifacts: bool = False,
    ) -> dict[str, Any]:
        engineering = self.release_check(project, "engineering", commit=commit, require_artifacts=require_artifacts)
        environment = self.release_check(project, "environment")
        pilot = self.release_check(project, "pilot")
        full = self.release_check(project, "full", commit=commit, require_artifacts=require_artifacts)
        repo_wide = self.release_check(project, "repo-wide", commit=commit, require_artifacts=require_artifacts)
        environment_diagnosis = self.release_diagnose(project, "environment")

        gates = {
            "engineering": engineering,
            "environment": environment,
            "pilot": pilot,
            "full": full,
            "repo-wide": repo_wide,
        }
        versions = {
            "v0.1-preview": {"gate": "engineering", "status": engineering["status"]},
            "v0.2-beta": {
                "gate": "environment",
                "status": "ready" if engineering["status"] == "ready" and environment["status"] == "ready" else "blocked",
            },
            "v0.3-pilot": {
                "gate": "pilot",
                "status": "ready"
                if engineering["status"] == "ready" and environment["status"] == "ready" and pilot["status"] == "ready"
                else "blocked",
            },
            "full": {"gate": "full", "status": full["status"]},
        }
        highest_ready_version = "none"
        for version in ["v0.1-preview", "v0.2-beta", "v0.3-pilot", "full"]:
            if versions[version]["status"] == "ready":
                highest_ready_version = version
            else:
                break
        report_status = "ready" if full["status"] == "ready" and repo_wide["status"] == "ready" else "blocked"

        blocked_gates = [name for name, payload in gates.items() if payload["status"] != "ready"]
        blockers: list[dict[str, Any]] = []
        for gate_name in ["engineering", "environment", "pilot", "repo-wide"]:
            for check in gates[gate_name]["checks"]:
                if check.get("passed"):
                    continue
                blocker = {
                    "gate": gate_name,
                    "check": check["name"],
                    "actual": check.get("actual"),
                    "required_for": check.get("required_for", []),
                }
                if "target" in check:
                    blocker["target"] = check["target"]
                if "missing" in check:
                    blocker["missing"] = check["missing"]
                blockers.append(blocker)

        next_actions = []
        if engineering["status"] != "ready":
            next_actions.append(
                {
                    "id": "restore_engineering_gate",
                    "gate": "engineering",
                    "action": "Fix blocked engineering release checks, then rerun the strict engineering release gate.",
                    "verify_command": f"python scripts/kb.py release check --project {project} --level engineering",
                }
            )
        for step in environment_diagnosis["remediation"]:
            action = dict(step)
            action["gate"] = "environment"
            next_actions.append(action)
        if pilot["status"] != "ready":
            next_actions.append(
                {
                    "id": "run_ten_task_pilot",
                    "gate": "pilot",
                    "action": "Run at least 10 real Project KB tasks, record each pilot event, and verify all pilot thresholds.",
                    "verify_command": f"python scripts/kb.py release check --project {project} --level pilot",
                }
            )
        if repo_wide["status"] != "ready":
            repo_wide_steps = [
                (
                    "run_public_claims_smoke",
                    "Run the public claims smoke to ensure README and Project KB docs scope release claims to current evidence.",
                    f"python scripts/kb.py release evidence public-claims-smoke --project {project}",
                ),
                (
                    "run_clean_install_smoke",
                    "Run the clean install smoke to verify template artifacts, documented install paths, and root setup scripts.",
                    f"python scripts/kb.py release evidence clean-install-smoke --project {project}",
                ),
                (
                    "run_user_journey_smoke",
                    "Run the user journey smoke to verify ingest, query, lint, and social ingest template coverage.",
                    f"python scripts/kb.py release evidence user-journey-smoke --project {project}",
                ),
                (
                    "run_support_matrix_smoke",
                    "Run the support matrix smoke to record host, OS, transport, and Obsidian surface coverage.",
                    f"python scripts/kb.py release evidence support-matrix-smoke --project {project}",
                ),
                (
                    "collect_repo_wide_release_evidence",
                    "Collect public claims, clean install, user journey, and support matrix evidence before claiming a repo-wide end-user release.",
                    f"python scripts/kb.py release check --project {project} --level repo-wide",
                ),
            ]
            for action_id, action_text, verify_command in repo_wide_steps:
                next_actions.append(
                    {
                        "id": action_id,
                        "gate": "repo-wide",
                        "action": action_text,
                        "verify_command": verify_command,
                    }
                )

        verification_commands = [
            "python -m unittest tests.test_project_kb -v",
            f"python scripts/kb.py release check --project {project} --level engineering",
            f"python scripts/kb.py release diagnose --project {project} --level environment",
            f"python scripts/kb.py release smoke --project {project} --level environment",
            f"python scripts/kb.py release check --project {project} --level pilot",
            f"python scripts/kb.py release check --project {project} --level full",
            f"python scripts/kb.py release check --project {project} --level repo-wide",
        ]

        return {
            "project": project,
            "target_version": "repo-wide-end-user-release",
            "project_kb_status": full["status"],
            "status": report_status,
            "highest_ready_version": highest_ready_version,
            "versions": versions,
            "repo_wide": {
                "target_release": "repo-wide-end-user-release",
                "status": repo_wide["status"],
            },
            "blocked_gates": blocked_gates,
            "blockers": blockers,
            "next_actions": next_actions,
            "verification_commands": verification_commands,
            "gates": gates,
            "environment_diagnosis": environment_diagnosis,
            "metrics": pilot["metrics"],
        }

    def stale(self, project: str, current_commit: str) -> dict[str, Any]:
        stale = []
        for note in self.iter_notes(project):
            note_type = note.frontmatter.get("type")
            if note_type not in STALE_TRACKED_TYPES:
                continue
            verified = note.frontmatter.get("verified_commit") or note.frontmatter.get("last_verified_commit")
            if not verified:
                stale.append({"path": note.rel_path, "reason": "verified_commit missing"})
            elif current_commit and verified != current_commit:
                stale.append({"path": note.rel_path, "reason": f"verified_commit differs from {current_commit}"})
        return {"stale": stale}

    def project_root(self, project: str) -> Path:
        return self.vault / "Projects" / slugify(project)

    def update_frontmatter_path(self, path: Path, field: str, value: Any, actor: str, project: str) -> dict[str, Any]:
        note = self.read_note(path)
        note.frontmatter[field] = value
        raw = replace_frontmatter(note.raw, note.frontmatter)
        if contains_secret(raw):
            raise ValueError("refusing to write secret-like content")
        validation_errors = self.validate_note_text(path, raw)
        repo_errors: list[dict[str, str]] = []
        repo_warnings: list[dict[str, str]] = []
        preview_note = Note(
            path=path,
            rel_path=normalize_rel(path.relative_to(self.vault)),
            frontmatter=note.frontmatter,
            body=parse_frontmatter(raw)[1],
            raw=raw,
        )
        self.validate_repo_and_sources(preview_note, repo_errors, repo_warnings)
        validation_errors.extend(repo_errors)
        if validation_errors:
            detail = "; ".join(error["message"] for error in validation_errors)
            raise ValueError(f"target validation failed for {normalize_rel(path.relative_to(self.vault))}: {detail}")
        obsidian_cli_available, _ = self.probe_obsidian_cli()
        transport = str(note.frontmatter.get("transport") or "")
        with self.lock_file(path):
            if transport == "mcp_obsidian" and self.obsidian_rest_enabled():
                try:
                    encoded_value = ",".join(str(item) for item in value) if isinstance(value, list) else str(value)
                    self.obsidian_rest_patch_frontmatter(normalize_rel(path.relative_to(self.vault)), field, encoded_value)
                    path.write_text(raw, encoding="utf-8")
                except Exception:
                    path.write_text(raw, encoding="utf-8")
            elif transport == "cli" and obsidian_cli_available:
                try:
                    property_type = "list" if isinstance(value, list) else "text"
                    encoded_value = ",".join(str(item) for item in value) if isinstance(value, list) else str(value)
                    self.obsidian_cli_property_set(project, normalize_rel(path.relative_to(self.vault)), field, encoded_value, property_type)
                    path.write_text(raw, encoding="utf-8")
                except Exception:
                    path.write_text(raw, encoding="utf-8")
            else:
                path.write_text(raw, encoding="utf-8")
            self.audit(project, actor, f"update_frontmatter:{field}", path, str(note.frontmatter.get("verified_commit") or ""))
        return {"path": normalize_rel(path.relative_to(self.vault)), "field": field, "value": value}

    def obsidian_cli_property_set(self, project: str, path: str, name: str, value: str, property_type: str = "text") -> None:
        command = self.obsidian_cli_command(
            "property:set",
            f"name={name}",
            f"value={value}",
            f"path={path}",
            f"type={property_type}",
        )
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "obsidian property:set failed"
            raise RuntimeError(stderr)

    def obsidian_cli_create_note(self, project: str, path: str, content: str) -> None:
        note_path = Path(path)
        name = note_path.stem
        command = self.obsidian_cli_command(
            "create",
            f"name={name}",
            f"path={path}",
            f"content={content}",
            "overwrite",
        )
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "obsidian create failed"
            raise RuntimeError(stderr)

    def next_adr_number(self, decisions: Path) -> int:
        highest = 0
        for path in decisions.glob("ADR-*.md"):
            match = re.match(r"ADR-(\d{4})-", path.name)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def project_roots(self) -> list[Path]:
        projects = self.vault / "Projects"
        if not projects.exists():
            return []
        return [path for path in projects.iterdir() if path.is_dir()]

    def iter_notes(self, project: str):
        root = self.project_root(project)
        for path in sorted(root.rglob("*.md")):
            if ".vault-meta" in path.parts:
                continue
            yield self.read_note(path)

    def read_note(self, path: Path) -> Note:
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(raw)
        rel = normalize_rel(path.relative_to(self.vault))
        return Note(path=path, rel_path=rel, frontmatter=frontmatter, body=body, raw=raw)

    def find_wikilinks(self, body: str) -> list[str]:
        links = []
        for match in re.finditer(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]", body):
            links.append(match.group(1).strip())
        return links

    def has_section(self, body: str, section: str) -> bool:
        return bool(re.search(rf"^##+\s+{re.escape(section)}\s*$", body, re.MULTILINE))

    def expected_note_type(self, path: Path) -> str | None:
        try:
            rel = path.relative_to(self.vault)
        except ValueError:
            return None
        if len(rel.parts) < 3 or rel.parts[0] != "Projects":
            return None
        name = rel.name
        if name == "_index.md" and len(rel.parts) == 3:
            return "project"
        if len(rel.parts) == 3:
            return {
                "hot.md": "hot",
                "context.md": "context",
                "architecture.md": "architecture",
                "glossary.md": "glossary",
                "pitfalls.md": "pitfall",
            }.get(name)
        if len(rel.parts) >= 4:
            return {
                "decisions": "decision",
                "modules": "module",
                "tasks": "task",
                "logs": "log",
                "sources": "source",
            }.get(rel.parts[2])
        return None

    def wikilink_exists(self, source_path: Path, target: str) -> bool:
        project_root = self.project_root(source_path.relative_to(self.vault).parts[1])
        candidates = [
            project_root / f"{target}.md",
            source_path.parent / f"{target}.md",
        ]
        if Path(target).suffix == ".md":
            candidates.extend([project_root / target, source_path.parent / target])
        for candidate in candidates:
            if candidate.exists():
                return True
        target_name = Path(target).name
        return any(path.stem == target_name for path in project_root.rglob("*.md"))

    def resolve_note_path(self, path: str) -> Path:
        candidate = (self.vault / path).resolve()
        try:
            rel = candidate.relative_to(self.vault)
        except ValueError as exc:
            raise ValueError("path must stay inside vault") from exc
        if not candidate.exists():
            raise FileNotFoundError(path)
        if candidate.suffix != ".md" or len(rel.parts) < 3 or rel.parts[0] != "Projects" or any(part.startswith(".") for part in rel.parts[2:]):
            raise ValueError("read only supports Project KB Markdown notes")
        return candidate

    def write_if_missing(self, path: Path, content: str) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def project_index(self, project: str, repo: Path) -> str:
        return make_note(
            {
                "schema_version": SCHEMA_VERSION,
                "type": "project",
                "project": project,
                "repo": str(repo),
                "status": "active",
                "agent_scope": ["codex", "claude", "openclaw"],
                "source_of_truth": "repo",
                "last_verified_commit": None,
                "last_verified_at": None,
                "transport": "auto",
                "tags": ["project", project.lower()],
            },
            f"""# {project}

## Purpose

Describe why this project exists.

## Current State

No verified project summary has been written yet.

## Important Modules

- [[modules/example|Example]]

## Active Decisions

- [[decisions/ADR-0001-example|ADR-0001: Example]]

## Known Pitfalls

- Treat current code and verification output as implementation truth when notes conflict.

## Verification Commands

- `python scripts/kb.py validate --project {project}`

## Links

- Repo: `{repo}`
""",
        )

    def hot_note(self, project: str) -> str:
        return make_note(
            {
                "schema_version": SCHEMA_VERSION,
                "type": "hot",
                "project": project,
                "updated_at": None,
                "tags": ["hot", project.lower()],
            },
            f"""# {project} Hot Cache

## Current Focus

- No active focus recorded.

## Recent Context

- Created by `kb init-project`.

## Open Questions

- Confirm write-back policy before enabling routine append logs.
""",
        )

    def typed_note(self, project: str, note_type: str, title: str, sections: list[str]) -> str:
        body = f"# {title}\n\n" + "\n\n".join(f"## {section}\n\n" for section in sections)
        return make_note(
            {
                "schema_version": SCHEMA_VERSION,
                "type": note_type,
                "project": project,
                "source_paths": [],
                "verified_commit": None,
                "confidence": "medium",
                "tags": [note_type, project.lower()],
            },
            body,
        )

    def module_note(self, project: str, module: str) -> str:
        return make_note(
            {
                "schema_version": SCHEMA_VERSION,
                "type": "module",
                "project": project,
                "module": module,
                "source_paths": [],
                "verified_commit": None,
                "confidence": "medium",
                "tags": ["module", project.lower()],
            },
            f"""# {module}

## Responsibility

Describe this module's responsibility.

## Entry Points

## Key Files

## Data Flow

## Known Pitfalls

## Verification
""",
        )

    def adr_note(self, project: str) -> str:
        return make_note(
            {
                "schema_version": SCHEMA_VERSION,
                "type": "decision",
                "project": project,
                "status": "proposed",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_paths": [],
                "verified_commit": None,
                "confidence": "medium",
                "tags": ["adr", "architecture", project.lower()],
            },
            """# ADR-0001: Example

## Context

Record the confirmed context for this decision.

## Decision

Record the decision after it is confirmed.

## Consequences

## Alternatives Considered

## Verification
""",
        )

    def task_note(self, project: str, task_id: str, title: str) -> str:
        return make_note(
            {
                "schema_version": SCHEMA_VERSION,
                "type": "task",
                "project": project,
                "task_id": task_id,
                "status": "proposed",
                "source_paths": [],
                "verified_commit": None,
                "confidence": "medium",
                "tags": ["task", project.lower()],
            },
            f"""# {title}

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
        )

    def log_note(self, project: str, period: str) -> str:
        return make_note(
            {
                "schema_version": SCHEMA_VERSION,
                "type": "log",
                "project": project,
                "period": period,
                "tags": ["log", project.lower()],
            },
            f"# {project} Task Log {period}\n",
        )

    def snippet(self, body: str, terms: list[str]) -> str:
        clean = re.sub(r"\s+", " ", body).strip()
        lower = clean.lower()
        positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
        start = max(min(positions) - 80, 0) if positions else 0
        return clean[start : start + 220]

    def validate_repo_and_sources(self, note: Note, errors: list[dict[str, str]], warnings: list[dict[str, str]]) -> None:
        note_type = note.frontmatter.get("type")
        if note_type == "project":
            repo = note.frontmatter.get("repo")
            if repo and not Path(str(repo)).exists():
                errors.append({"path": note.rel_path, "message": f"repo path does not exist: {repo}"})
        source_paths = note.frontmatter.get("source_paths")
        if not source_paths:
            return
        try:
            project_info = self.project_find(project=str(note.frontmatter.get("project")))
            repo = Path(project_info["repo"])
        except Exception:
            return
        for source in source_paths:
            if source and not (repo / str(source)).exists():
                errors.append({"path": note.rel_path, "message": f"source path does not exist: {source}"})

    def validate_log_names(self, project: str, errors: list[dict[str, str]]) -> None:
        logs = self.project_root(project) / "logs"
        if not logs.exists():
            return
        for path in logs.glob("*.md"):
            if not re.fullmatch(r"\d{4}-\d{2}\.md", path.name):
                errors.append({"path": normalize_rel(path.relative_to(self.vault)), "message": "log filename must be YYYY-MM.md"})

    def format_log_entry(self, payload: dict[str, Any]) -> str:
        date = datetime.now().strftime("%Y-%m-%d")
        title = payload.get("title") or "Untitled Task"
        files = payload.get("files") or []
        commands = payload.get("commands") or []
        source_paths = payload.get("source_paths") or []
        urls = payload.get("urls") or []
        if payload.get("url"):
            urls = [*urls, payload.get("url")] if isinstance(urls, list) else [urls, payload.get("url")]
        lines = [
            f"## {date}: {title}",
            "",
            f"- Status: {payload.get('status') or payload.get('result') or 'recorded'}",
            f"- Repo: {payload.get('repo') or ''}",
            f"- Branch: {payload.get('branch') or ''}",
            f"- Commit: {payload.get('commit') or ''}",
            f"- Files: {', '.join(files) if isinstance(files, list) else files}",
            f"- Commands: {'; '.join(commands) if isinstance(commands, list) else commands}",
            f"- Source Paths: {', '.join(source_paths) if isinstance(source_paths, list) else source_paths}",
            f"- URLs: {', '.join(str(url) for url in urls) if isinstance(urls, list) else urls}",
            f"- Result: {payload.get('summary') or payload.get('result') or ''}",
            f"- Follow-ups: {payload.get('follow_ups') or payload.get('follow-ups') or ''}",
        ]
        return "\n".join(lines)

    def reject_secret_payload(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        if contains_secret(raw):
            raise ValueError("refusing to write secret-like content")

    def require_log_provenance(self, payload: dict[str, Any]) -> None:
        fields = ["commit", "commands", "files", "source_paths", "url", "urls", "repo"]
        for field in fields:
            value = payload.get(field)
            if isinstance(value, list) and any(str(item).strip() for item in value):
                return
            if isinstance(value, str) and value.strip():
                return
            if value and not isinstance(value, (list, str)):
                return
        raise ValueError("append-log requires provenance: include commit, commands, files, source_paths, url, urls, or repo")

    @contextmanager
    def lock_file(self, target: Path):
        project_root = self.project_root_for_path(target)
        locks = project_root / ".vault-meta" / "locks"
        locks.mkdir(parents=True, exist_ok=True)
        lock = locks / f"{self.lock_name(target)}.lock"
        deadline = time.time() + 10
        contention_recorded = False
        while True:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps({"target": str(target), "created_at": now_iso()}))
                break
            except FileExistsError:
                if not contention_recorded:
                    self.record_lock_contention(target)
                    contention_recorded = True
                if time.time() > deadline:
                    raise TimeoutError(f"lock timeout: {lock}")
                if time.time() - lock.stat().st_mtime > 300:
                    lock.unlink(missing_ok=True)
                    continue
                time.sleep(0.05)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    def lock_name(self, target: Path) -> str:
        project_root = self.project_root_for_path(target)
        try:
            rel = target.relative_to(project_root)
        except ValueError:
            rel = Path(target.name)
        return "__".join(rel.parts)

    def project_root_for_path(self, target: Path) -> Path:
        rel = target.resolve().relative_to(self.vault)
        if len(rel.parts) < 2 or rel.parts[0] != "Projects":
            raise ValueError("path must be inside a project root")
        return self.vault / "Projects" / rel.parts[1]

    def audit(self, project: str, actor: str, operation: str, path: Path, commit: str | None) -> None:
        audit_path = self.project_root(project) / ".vault-meta" / "audit.jsonl"
        source = "mcp" if actor == "mcp" else "cli"
        entry = {
            "time": now_iso(),
            "actor": actor,
            "operation": operation,
            "path": normalize_rel(path.relative_to(self.vault)),
            "source": source,
            "commit": commit or "",
        }
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def record_lock_contention(self, target: Path) -> None:
        project_root = self.project_root_for_path(target)
        pilot_dir = project_root / ".vault-meta" / "pilot"
        pilot_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "recorded_at": now_iso(),
            "event_type": "lock_contention",
            "lock_contention_count": 1,
            "path": normalize_rel(target.relative_to(self.vault)),
        }
        with (pilot_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def adapter_text(self, agent: str, project: str) -> str:
        if agent == "codex":
            heading = "## Project Knowledge"
        elif agent == "claude":
            heading = "## Project KB"
        elif agent == "openclaw":
            heading = "# Project KB for OpenClaw"
        elif agent == "opencode":
            heading = "# Project KB for OpenCode"
        else:
            heading = "# Project KB Generic CLI Adapter"
        return f"""{heading}

- Resolve this project with `kb.project_find` or `python scripts/kb.py project-find --project {project}`.
- Read `Projects/{project}/hot.md` when long-running context matters.
- Search task-relevant notes with a limit of 5.
- Treat current code, tests, and command output as implementation truth.
- Append task logs only after verification.
- Do not expose delete, full-note overwrite, batch move, batch rename, or vault-wide rewrite.

## Access Disclosure

- Network access: none by default for filesystem-backed CLI/MCP use; optional host or Obsidian Local REST transports may use localhost or user-configured endpoints.
- Vault-external files: reads the configured source repository only when resolving repo paths, validating `source_paths`, or when the human/agent separately inspects source files.
- Remote LLM API: none in Project KB CLI/MCP; any model calls come from the surrounding agent host, not this adapter.
- Telemetry: none emitted by Project KB CLI/MCP.
- Paid services: none required by Project KB CLI/MCP.
"""

    def host_config_text(self, host: str, manifest: dict[str, Any]) -> str:
        title = {
            "codex": "Codex MCP Host Snippet",
            "claude": "Claude Code MCP Host Snippet",
            "openclaw": "OpenClaw MCP Host Snippet",
            "opencode": "OpenCode MCP Host Snippet",
            "generic": "Generic MCP Host Snippet",
        }[host]
        command = manifest["server"]["command"]
        args = " ".join(f'"{arg}"' for arg in manifest["server"]["args"])
        vault = manifest["env"]["PROJECT_KB_VAULT"]
        return f"""# {title}

This snippet is an auditable Project KB registration aid. Before pasting it into a host config, verify against the current host documentation.

Shared MCP server:

```json
{json.dumps(manifest, ensure_ascii=False, indent=2)}
```

Equivalent command:

```powershell
$env:PROJECT_KB_VAULT="{vault}"
{command} {args}
```

Safety boundary:

- The server name is `project-kb`.
- The server command points to `scripts/kb_mcp.py`.
- Exposed tools are project-level facade tools only.
- Delete, overwrite, bulk move, bulk rename, and vault-wide rewrite tools are not exposed.
"""

    def repo_mcp_script(self) -> str:
        return normalize_rel(Path(__file__).resolve().parents[1] / "scripts" / "kb_mcp.py")

    def repo_host_manifest(self, project: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "project": slugify(project),
            "server": {
                "name": "project-kb",
                "command": "python",
                "args": [self.repo_mcp_script()],
                "transport": "stdio",
            },
            "env": {
                "PROJECT_KB_VAULT": str(self.vault),
                "PROJECT_KB_PROJECT": slugify(project),
            },
        }

    def repo_codex_config(self, project: str) -> str:
        return f"""# Project KB MCP draft for Codex.
# Review against the current Codex config documentation before copying.

[mcp_servers.project-kb]
command = "python"
args = ["{self.repo_mcp_script()}"]
startup_timeout_sec = 30

[mcp_servers.project-kb.env]
PROJECT_KB_VAULT = "{normalize_rel(self.vault)}"
PROJECT_KB_PROJECT = "{slugify(project)}"
"""

    def repo_claude_mcp_config(self, project: str) -> str:
        payload = {
            "description": "Project KB MCP draft for Claude Code. Review against current Claude Code MCP docs before copying.",
            "mcpServers": {
                "project-kb": {
                    "command": "python",
                    "args": [self.repo_mcp_script()],
                    "env": {
                        "PROJECT_KB_VAULT": str(self.vault),
                        "PROJECT_KB_PROJECT": slugify(project),
                    },
                }
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    def repo_openclaw_mcp_config(self, project: str) -> str:
        payload = {
            "description": "Project KB MCP draft for OpenClaw. Register or route this external MCP facade according to your OpenClaw config.",
            "mcpServers": {
                "project-kb": {
                    "transport": "stdio",
                    "command": "python",
                    "args": [self.repo_mcp_script()],
                    "env": {
                        "PROJECT_KB_VAULT": str(self.vault),
                        "PROJECT_KB_PROJECT": slugify(project),
                    },
                }
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    def repo_host_config_readme(self, project: str) -> str:
        project = slugify(project)
        return f"""# Project KB Host Config Drafts

These files are draft MCP registration snippets. They do not auto-install anything and should be reviewed against the current host documentation before use.

Files:

- `codex.config.toml`: draft `[mcp_servers.project-kb]` block for Codex.
- `claude.mcp.json`: draft MCP server object for Claude Code-style JSON config.
- `openclaw.mcp.json5`: draft external MCP server object for OpenClaw routing.
- `opencode.md`: draft MCP registration snippet for OpenCode.

Safety boundary:

- Server command: `python {self.repo_mcp_script()}`
- Vault: `{normalize_rel(self.vault)}`
- Project: `{project}`
- Exposes only the Project KB facade tools.
- Does not expose delete, full-note overwrite, batch move, batch rename, or vault-wide rewrite.
"""

    def project_canvas(self, project: str) -> dict[str, Any]:
        project = slugify(project)
        notes = list(self.iter_notes(project))
        nodes = [
            {
                "id": "project-index",
                "type": "file",
                "file": f"Projects/{project}/_index.md",
                "x": 0,
                "y": 0,
                "width": 400,
                "height": 240,
            },
            {
                "id": "hot",
                "type": "file",
                "file": f"Projects/{project}/hot.md",
                "x": 480,
                "y": 0,
                "width": 360,
                "height": 200,
            },
        ]
        edges = [
            {"id": "project-to-hot", "fromNode": "project-index", "toNode": "hot"},
        ]
        buckets = [
            ("architecture", lambda note: note.rel_path.endswith("/architecture.md")),
            ("pitfalls", lambda note: note.rel_path.endswith("/pitfalls.md")),
            ("modules", lambda note: "/modules/" in note.rel_path),
            ("decisions", lambda note: "/decisions/" in note.rel_path),
            ("tasks", lambda note: "/tasks/" in note.rel_path),
            ("sources", lambda note: "/sources/" in note.rel_path),
        ]
        y_by_bucket = {
            "architecture": 280,
            "pitfalls": 280,
            "modules": 560,
            "decisions": 560,
            "tasks": 840,
            "sources": 1120,
        }
        x_by_bucket = {
            "architecture": 0,
            "pitfalls": 480,
            "modules": 0,
            "decisions": 480,
            "tasks": 0,
            "sources": 240,
        }
        counts = {name: 0 for name, _ in buckets}
        for note in notes:
            if note.rel_path.endswith(("_index.md", "/hot.md")):
                continue
            bucket_name = ""
            for name, predicate in buckets:
                if predicate(note):
                    bucket_name = name
                    break
            if not bucket_name:
                continue
            count = counts[bucket_name]
            counts[bucket_name] += 1
            node_id = f"{bucket_name}-{count}"
            nodes.append(
                {
                    "id": node_id,
                    "type": "file",
                    "file": note.rel_path,
                    "x": x_by_bucket[bucket_name] + (count % 2) * 220,
                    "y": y_by_bucket[bucket_name] + (count // 2) * 180,
                    "width": 360,
                    "height": 180,
                }
            )
            edges.append({"id": f"project-to-{node_id}", "fromNode": "project-index", "toNode": node_id})
        return {"nodes": nodes, "edges": edges}

    def project_base(self, project: str) -> str:
        project = slugify(project)
        return f"""filters:
  and:
    - file.inFolder("Projects/{project}")
    - not file.inFolder("Projects/{project}/.vault-meta")
    - file.ext == "md"
views:
  - type: table
    name: Project notes
    order:
      - file.name
      - type
      - status
      - confidence
      - verified_commit
  - type: cards
    name: Project map
    image: file
    title: file.name
properties:
  type:
    displayName: Type
  status:
    displayName: Status
  confidence:
    displayName: Confidence
  verified_commit:
    displayName: Verified Commit
"""
