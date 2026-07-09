#!/usr/bin/env python3
"""Collect auditable git evidence for the code-archaeology skill.

The script intentionally stops at evidence collection and lightweight ranking.
It does not explain why a module evolved; the calling agent must read the
recommended diffs and write evidence-backed conclusions.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tokenize
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.2"
FIELD_SEP = "\x1f"
SHA_RE = re.compile(r"^[0-9a-f]{40}(?:\s|$)")
AST_DIFF_SCHEMA_VERSION = "ast-diff.0.1"
REMOTE_CONTEXT_SCHEMA_VERSION = "remote-context.0.1"
DEFAULT_AST_MAX_FILES = 5
DEFAULT_AST_MAX_BLOB_BYTES = 200_000
GENERATED_PARTS = {
    "dist",
    "build",
    "coverage",
    "vendor",
    "vendors",
    "node_modules",
    "generated",
    "__generated__",
}
LOCKFILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
}
BOT_PATTERNS = ("bot", "dependabot", "renovate", "github-actions")


@dataclass
class GitRunner:
    repo: Path
    commands_run: list[str] = field(default_factory=list)

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = ["git", *args]
        self.commands_run.append(format_command(command))
        result = subprocess.run(
            command,
            cwd=self.repo,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if check and result.returncode != 0:
            raise GitError(result.stderr.strip() or result.stdout.strip() or "git command failed")
        return result

    def git_bytes(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        command = ["git", *args]
        self.commands_run.append(format_command(command))
        result = subprocess.run(
            command,
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if check and result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            stdout = result.stdout.decode("utf-8", errors="replace").strip()
            raise GitError(stderr or stdout or "git command failed")
        return result


class GitError(RuntimeError):
    pass


def format_command(command: list[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def shell_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./\\-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def posix_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def email_hash(email: str) -> str | None:
    email = email.strip().lower()
    if not email:
        return None
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]


def parse_bool(raw: str) -> bool:
    return raw.strip().lower() == "true"


def normalize_target(raw_target: str, repo_root: Path) -> str:
    raw = raw_target.replace("\\", "/").strip()
    if not raw:
        return raw
    candidate = Path(raw_target)
    if candidate.is_absolute():
        try:
            return posix_path(candidate.resolve().relative_to(repo_root))
        except ValueError:
            return posix_path(raw)
    if raw.startswith("./"):
        raw = raw[2:]
    return posix_path(raw)


def parse_z_lines(raw: str) -> list[str]:
    if not raw:
        return []
    return [item for item in raw.split("\0") if item]


def get_repo_info(repo_arg: str) -> tuple[GitRunner, dict[str, Any]]:
    repo = Path(repo_arg).resolve()
    runner = GitRunner(repo=repo)
    inside = runner.git("rev-parse", "--is-inside-work-tree", check=False)
    if inside.returncode != 0 or inside.stdout.strip().lower() != "true":
        raise GitError(f"not a git work tree: {repo}")

    root_raw = runner.git("rev-parse", "--show-toplevel").stdout.strip()
    root = resolve_git_root(root_raw, repo)
    runner.repo = root
    is_shallow = parse_bool(runner.git("rev-parse", "--is-shallow-repository").stdout)
    is_bare = parse_bool(runner.git("rev-parse", "--is-bare-repository").stdout)
    head = runner.git("rev-parse", "HEAD").stdout.strip()
    branch_result = runner.git("rev-parse", "--abbrev-ref", "HEAD", check=False)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    if branch == "HEAD":
        branch = None
    git_version = runner.git("--version").stdout.strip()
    status = runner.git("status", "--short", "--branch").stdout.splitlines()
    head_meta = runner.git(
        "log",
        "-1",
        f"--format=%H{FIELD_SEP}%aI{FIELD_SEP}%cI{FIELD_SEP}%an{FIELD_SEP}%ae{FIELD_SEP}%s",
    ).stdout.strip()

    return runner, {
        "root": str(root),
        "head": head,
        "branch": branch,
        "is_shallow": is_shallow,
        "is_bare": is_bare,
        "history_complete": not is_shallow,
        "git_version": git_version,
        "status": status,
        "head_commit": split_head_meta(head_meta),
    }


def resolve_git_root(root_raw: str, fallback: Path) -> Path:
    cleaned = root_raw.strip().strip('"')
    candidates = [
        Path(cleaned),
        Path(cleaned.replace("/", os.sep)),
        fallback,
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_dir():
            return resolved
    return fallback


def split_head_meta(raw: str) -> dict[str, Any]:
    parts = raw.split(FIELD_SEP)
    if len(parts) < 6:
        return {}
    return {
        "sha": parts[0],
        "author_date": parts[1],
        "committer_date": parts[2],
        "author": {"name": parts[3], "email_hash": email_hash(parts[4])},
        "subject": parts[5],
    }


def list_tracked_files(runner: GitRunner) -> list[str]:
    result = runner.git("ls-files", "-z")
    return sorted(posix_path(item) for item in parse_z_lines(result.stdout))


def resolve_target(runner: GitRunner, raw_target: str, files: list[str]) -> dict[str, Any]:
    repo_root = runner.repo
    target = normalize_target(raw_target, repo_root)
    ambiguities: list[str] = []
    normalized_paths: list[str] = []
    target_type = "symbol"

    if has_glob(target):
        matches = sorted(path for path in files if fnmatch.fnmatch(path, target))
        target_type = "glob" if matches else "ambiguous"
        normalized_paths = matches
        if not matches:
            ambiguities.append(f"No tracked files matched glob {target!r}.")
    elif target in files:
        target_type = "file"
        normalized_paths = [target]
    else:
        prefix = target.rstrip("/") + "/"
        directory_matches = [path for path in files if path.startswith(prefix)]
        if directory_matches:
            target_type = "directory"
            normalized_paths = [target.rstrip("/")]
        elif (repo_root / target).is_dir():
            target_type = "directory"
            normalized_paths = [target.rstrip("/")]
            ambiguities.append("Directory exists in the working tree but has no tracked files.")
        else:
            basename_matches = [
                path
                for path in files
                if Path(path).name == target or Path(path).stem == target or target in Path(path).parts
            ]
            if len(basename_matches) == 1:
                target_type = "module"
                normalized_paths = basename_matches
            elif len(basename_matches) > 1:
                target_type = "module"
                normalized_paths = basename_matches[:50]
                if len(basename_matches) > 50:
                    ambiguities.append(
                        f"Module-like target matched {len(basename_matches)} paths; truncated to 50."
                    )
                else:
                    ambiguities.append(f"Module-like target matched {len(basename_matches)} paths.")
            else:
                history_hits = commits_for_paths(runner, [target], max_commits=1, follow=False, rev_range=None)
                if history_hits:
                    target_type = "file"
                    normalized_paths = [target]
                    ambiguities.append("Target is not present at HEAD but exists in history.")
                else:
                    target_type = "symbol"
                    grep_hits = git_grep(runner, target)
                    normalized_paths = sorted({hit.split(":", 1)[0] for hit in grep_hits})[:50]
                    if not normalized_paths:
                        ambiguities.append("Target did not resolve to a tracked path or grep hit.")
                    elif len(normalized_paths) > 1:
                        ambiguities.append(f"Symbol search matched {len(normalized_paths)} files.")

    pathspecs = normalized_paths if target_type != "directory" else [normalized_paths[0]]
    return {
        "raw_target": raw_target,
        "normalized_target": target,
        "target_type": target_type,
        "normalized_paths": normalized_paths,
        "pathspecs": pathspecs,
        "ambiguities": ambiguities,
    }


def has_glob(value: str) -> bool:
    return any(char in value for char in "*?[")


def git_grep(runner: GitRunner, needle: str) -> list[str]:
    if not needle:
        return []
    result = runner.git("grep", "-n", "--", needle, check=False)
    if result.returncode not in (0, 1):
        return []
    return result.stdout.splitlines()


def commits_for_paths(
    runner: GitRunner,
    pathspecs: list[str],
    max_commits: int,
    follow: bool,
    rev_range: str | None,
    since: str | None = None,
    until: str | None = None,
    include_merges: bool = True,
) -> list[str]:
    args = ["log", f"--max-count={max_commits}", "--format=%H", "--date=iso-strict"]
    if follow:
        args.append("--follow")
    if not include_merges:
        args.append("--no-merges")
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if rev_range:
        args.append(rev_range)
    args.append("--")
    args.extend(pathspecs)
    result = runner.git(*args, check=False)
    if result.returncode != 0:
        return []
    return unique_preserve_order(line.strip() for line in result.stdout.splitlines() if line.strip())


def commits_for_symbol(
    runner: GitRunner,
    symbol: str,
    max_commits: int,
    rev_range: str | None,
    since: str | None,
    until: str | None,
    include_merges: bool,
) -> list[str]:
    if not symbol:
        return []
    args = ["log", "--all", f"--max-count={max_commits}", "--format=%H", "--pickaxe-all", f"-S{symbol}"]
    if not include_merges:
        args.append("--no-merges")
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if rev_range:
        args.append(rev_range)
    result = runner.git(*args, check=False)
    if result.returncode != 0:
        return []
    return unique_preserve_order(line.strip() for line in result.stdout.splitlines() if line.strip())


def unique_preserve_order(values: list[str] | Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def collect_commits(
    runner: GitRunner,
    query: dict[str, Any],
    max_commits: int,
    rev_range: str | None,
    since: str | None,
    until: str | None,
    include_merges: bool,
) -> list[str]:
    target_type = query["target_type"]
    pathspecs = query["pathspecs"]
    follow = target_type == "file" and len(pathspecs) == 1
    if pathspecs:
        shas = commits_for_paths(
            runner,
            pathspecs,
            max_commits=max_commits,
            follow=follow,
            rev_range=rev_range,
            since=since,
            until=until,
            include_merges=include_merges,
        )
        if shas:
            return shas
    if target_type in {"symbol", "module", "ambiguous"}:
        return commits_for_symbol(
            runner,
            query["normalized_target"],
            max_commits=max_commits,
            rev_range=rev_range,
            since=since,
            until=until,
            include_merges=include_merges,
        )
    return []


def parse_commit_metadata(runner: GitRunner, sha: str) -> dict[str, Any]:
    fmt = FIELD_SEP.join(["%H", "%P", "%aI", "%an", "%ae", "%cI", "%cn", "%ce", "%s", "%B"])
    raw = runner.git("show", "-s", f"--format={fmt}", sha).stdout
    parts = raw.split(FIELD_SEP, 9)
    while len(parts) < 10:
        parts.append("")
    body = parts[9].strip()
    parents = [parent for parent in parts[1].split() if parent]
    return {
        "sha": parts[0].strip(),
        "parents": parents,
        "is_merge": len(parents) > 1,
        "author": {"name": parts[3].strip(), "email_hash": email_hash(parts[4])},
        "author_date": parts[2].strip(),
        "committer": {"name": parts[6].strip(), "email_hash": email_hash(parts[7])},
        "committer_date": parts[5].strip(),
        "subject": parts[8].strip(),
        "body_excerpt": first_non_subject_lines(body, parts[8].strip()),
    }


def first_non_subject_lines(body: str, subject: str) -> str:
    lines = [line.strip() for line in body.splitlines()]
    if lines and lines[0] == subject:
        lines = lines[1:]
    lines = [line for line in lines if line]
    return "\n".join(lines[:5])


ISSUE_REF_RE = re.compile(r"(?<![\w/])(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#(?P<number>\d+)\b")
REMOTE_ARTIFACT_URL_RE = re.compile(
    r"https?://(?P<host>[^/\s]+)/(?P<slug>[^/\s]+/[^/\s]+)/(?P<kind>issues|pull|pulls|merge_requests)/(?P<number>\d+)"
)
RATIONALE_RE = re.compile(
    r"(?i)\b(reason|rationale|because|so that|why|motivation)\b|因为|由于|以便|为了|原因"
)


def build_recorded_context(commit: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join(part for part in [commit.get("subject"), commit.get("body_excerpt")] if part)
    return {
        "issue_references": extract_issue_references(text),
        "explicit_rationales": extract_explicit_rationales(text),
        "caveat": "These are recorded references and stated reasons only; they are not hidden motivation or causality proof.",
    }


def extract_issue_references(text: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()

    for match in REMOTE_ARTIFACT_URL_RE.finditer(text or ""):
        kind = match.group("kind")
        normalized_kind = "pull_request" if kind in {"pull", "pulls", "merge_requests"} else "issue"
        raw = match.group(0)
        key = (match.group("number"), normalized_kind, match.group("slug"))
        if key in seen:
            continue
        refs.append(
            {
                "raw": raw,
                "number": match.group("number"),
                "kind": normalized_kind,
                "repository": match.group("slug"),
                "link_method": "explicit_url",
                "confidence": 0.9,
            }
        )
        seen.add(key)

    for match in ISSUE_REF_RE.finditer(text or ""):
        raw = match.group(0)
        number = match.group("number")
        repository = match.group("repo")
        key = (number, "issue_or_pr", repository)
        if key in seen:
            continue
        prefix = text[max(0, match.start() - 24) : match.start()].lower()
        confidence = 0.8 if re.search(r"\b(fix(?:es|ed)?|close[sd]?|resolve[sd]?|ref(?:s)?|see)\s*$", prefix) else 0.6
        refs.append(
            {
                "raw": raw,
                "number": number,
                "kind": "issue_or_pr",
                "repository": repository,
                "link_method": "commit_text_reference",
                "confidence": confidence,
            }
        )
        seen.add(key)
    return refs


def extract_explicit_rationales(text: str) -> list[dict[str, Any]]:
    rationales: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or not RATIONALE_RE.search(line):
            continue
        rationales.append(
            {
                "text": truncate_text(line, 240),
                "statement_type": "stated_rationale",
                "source": "commit_text",
                "caveat": "This is what the record says, not a private motive inference.",
            }
        )
    return rationales[:5]


def truncate_text(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def parse_name_status(output: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            if len(parts) >= 3:
                changes.append(
                    {
                        "status": status[0],
                        "similarity": parse_similarity(status),
                        "old_path": posix_path(parts[1]),
                        "path": posix_path(parts[2]),
                    }
                )
        elif len(parts) >= 2:
            changes.append(
                {
                    "status": status[0],
                    "similarity": None,
                    "old_path": None,
                    "path": posix_path(parts[1]),
                }
            )
    return changes


def parse_similarity(status: str) -> int | None:
    digits = "".join(char for char in status[1:] if char.isdigit())
    return int(digits) if digits else None


def parse_numstat(output: str) -> dict[str, Any]:
    files = 0
    added = 0
    deleted = 0
    binary = 0
    per_file: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        files += 1
        add_raw, del_raw, path_raw = parts[0], parts[1], parts[-1]
        if add_raw == "-" or del_raw == "-":
            binary += 1
            add = 0
            delete = 0
        else:
            add = int(add_raw)
            delete = int(del_raw)
        added += add
        deleted += delete
        per_file.append({"path": posix_path(path_raw), "added": add, "deleted": delete})
    return {"files": files, "added": added, "deleted": deleted, "binary_files": binary, "per_file": per_file}


def collect_change_details(
    runner: GitRunner, sha: str, pathspecs: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    args_suffix = ["--", *pathspecs] if pathspecs else []
    name_status = runner.git("show", "--name-status", "--format=", "-M", "-C", sha, *args_suffix, check=False)
    numstat = runner.git("show", "--numstat", "--format=", "-M", "-C", sha, *args_suffix, check=False)
    changes = parse_name_status(name_status.stdout if name_status.returncode == 0 else "")
    if pathspecs:
        full_name_status = runner.git("show", "--name-status", "--format=", "-M", "-C", sha, check=False)
        if full_name_status.returncode == 0:
            full_changes = [
                change for change in parse_name_status(full_name_status.stdout) if change_matches_pathspec(change, pathspecs)
            ]
            changes = merge_changes(changes, full_changes)
    stats = parse_numstat(numstat.stdout if numstat.returncode == 0 else "")
    changed_paths = sorted({change["path"] for change in changes if change.get("path")})
    if not changed_paths:
        changed_paths = sorted({item["path"] for item in stats["per_file"]})
    return changes, stats, changed_paths


def merge_changes(primary: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for change in [*primary, *extra]:
        key = (
            change.get("status"),
            change.get("old_path"),
            change.get("path"),
            change.get("similarity"),
        )
        if key in seen:
            continue
        merged.append(change)
        seen.add(key)
    return merged


def change_matches_pathspec(change: dict[str, Any], pathspecs: list[str]) -> bool:
    paths = [change.get("path"), change.get("old_path")]
    return any(path and path_matches_any(path, pathspecs) for path in paths)


def path_matches_any(path: str, pathspecs: list[str]) -> bool:
    for spec in pathspecs:
        clean = spec.rstrip("/")
        if has_glob(clean) and fnmatch.fnmatch(path, clean):
            return True
        if path == clean or path.startswith(clean + "/"):
            return True
    return False


def detect_semantic_language(path: str | None) -> str:
    if not path:
        return "unknown"
    suffix = Path(path).suffix.lower()
    if suffix in {".py", ".pyi"}:
        return "python"
    return "unsupported"


def collect_semantic_diffs(
    runner: GitRunner,
    commit: dict[str, Any],
    changes: list[dict[str, Any]],
    max_files: int,
    max_blob_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    flags: set[str] = set()
    files_analyzed = 0
    files_skipped = 0

    if commit.get("is_merge"):
        for change in changes[:max_files]:
            path = change.get("path") or change.get("old_path")
            diffs.append(
                {
                    "path": path,
                    "old_path": change.get("old_path"),
                    "status": change.get("status"),
                    "language": detect_semantic_language(path),
                    "result": "skipped",
                    "reason": "merge_commit_not_supported",
                }
            )
            files_skipped += 1
        return diffs, {"files_analyzed": files_analyzed, "files_skipped": files_skipped, "flags": ["merge_skipped"]}

    truncated = len(changes) > max_files
    for change in changes[:max_files]:
        diff = collect_one_semantic_diff(runner, commit, change, max_blob_bytes)
        diffs.append(diff)
        if diff.get("result") == "ok":
            files_analyzed += 1
            flags.update(diff.get("flags", []))
        else:
            files_skipped += 1
            reason = diff.get("reason") or diff.get("result")
            if reason:
                flags.add(str(reason))
    if truncated:
        flags.add("file_limit_reached")
    if any(flag not in {"ast_noop", "docstring_changed", "unsupported_language"} for flag in flags):
        if any(diff.get("summary", {}).get("semantic_changed") for diff in diffs):
            flags.add("semantic_change")
    return diffs, {"files_analyzed": files_analyzed, "files_skipped": files_skipped, "flags": sorted(flags)}


def collect_one_semantic_diff(
    runner: GitRunner,
    commit: dict[str, Any],
    change: dict[str, Any],
    max_blob_bytes: int,
) -> dict[str, Any]:
    path = change.get("path")
    old_path = change.get("old_path")
    status = change.get("status")
    language = detect_semantic_language(path or old_path)
    base = {
        "path": path,
        "old_path": old_path,
        "status": status,
        "language": language,
    }
    if language != "python":
        return {**base, "result": "skipped", "reason": "unsupported_language"}

    parent = commit.get("parents", [None])[0] if commit.get("parents") else None
    sha = commit["sha"]
    old_ref: str | None = None
    new_ref: str | None = None
    if status != "A" and parent:
        old_ref = f"{parent}:{old_path or path}"
    if status != "D" and path:
        new_ref = f"{sha}:{path}"
    base["old_ref"] = old_ref
    base["new_ref"] = new_ref

    old_source, old_error = read_python_blob(runner, old_ref, max_blob_bytes) if old_ref else (None, None)
    new_source, new_error = read_python_blob(runner, new_ref, max_blob_bytes) if new_ref else (None, None)
    if old_error or new_error:
        return {
            **base,
            "result": "skipped",
            "reason": old_error or new_error,
        }

    old_index, old_parse_error = build_python_ast_index(old_source, "old") if old_source is not None else (empty_ast_index(), None)
    new_index, new_parse_error = build_python_ast_index(new_source, "new") if new_source is not None else (empty_ast_index(), None)
    if old_parse_error or new_parse_error:
        return {
            **base,
            "result": "parse_error",
            "reason": old_parse_error or new_parse_error,
        }

    summary, flags = diff_python_ast_indexes(old_index, new_index)
    return {
        **base,
        "result": "ok",
        "summary": summary,
        "flags": flags,
    }


def read_python_blob(
    runner: GitRunner,
    ref: str | None,
    max_blob_bytes: int,
) -> tuple[str | None, str | None]:
    if not ref:
        return None, None
    size_result = runner.git("cat-file", "-s", ref, check=False)
    if size_result.returncode != 0:
        return None, "blob_unavailable"
    try:
        size = int(size_result.stdout.strip())
    except ValueError:
        return None, "blob_size_unknown"
    if size > max_blob_bytes:
        return None, "blob_too_large"
    blob = runner.git_bytes("show", ref, check=False)
    if blob.returncode != 0:
        return None, "blob_unavailable"
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(blob.stdout).readline)
        return blob.stdout.decode(encoding), None
    except (SyntaxError, UnicodeDecodeError, LookupError):
        try:
            return blob.stdout.decode("utf-8"), None
        except UnicodeDecodeError:
            return None, "decode_error"


def empty_ast_index() -> dict[str, Any]:
    return {"imports": set(), "symbols": {}}


def build_python_ast_index(source: str, side: str) -> tuple[dict[str, Any], str | None]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return empty_ast_index(), f"{side}_parse_error:{exc.msg}"

    index = empty_ast_index()
    visit_python_body(tree.body, "", index)
    return index, None


def visit_python_body(body: list[ast.stmt], prefix: str, index: dict[str, Any]) -> None:
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            index["imports"].add(format_import_node(node))
        elif isinstance(node, ast.ClassDef):
            qualname = join_qualname(prefix, node.name)
            index["symbols"][qualname] = class_symbol_info(node, qualname)
            visit_python_body(node.body, qualname, index)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = join_qualname(prefix, node.name)
            index["symbols"][qualname] = function_symbol_info(node, qualname)
            visit_python_body(node.body, qualname, index)


def join_qualname(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def format_import_node(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.Import):
        names = ", ".join(format_alias(alias) for alias in node.names)
        return f"import {names}"
    module = "." * node.level + (node.module or "")
    names = ", ".join(format_alias(alias) for alias in node.names)
    return f"from {module} import {names}"


def format_alias(alias: ast.alias) -> str:
    return f"{alias.name} as {alias.asname}" if alias.asname else alias.name


def function_symbol_info(node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> dict[str, Any]:
    body = strip_docstring(node.body)
    return {
        "kind": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
        "qualname": qualname,
        "signature_hash": ast_digest([node.args, node.returns]),
        "decorators_hash": ast_digest(node.decorator_list),
        "body_hash": ast_digest(body),
        "docstring_hash": text_digest(ast.get_docstring(node, clean=False)),
    }


def class_symbol_info(node: ast.ClassDef, qualname: str) -> dict[str, Any]:
    body_without_doc = strip_docstring(node.body)
    non_definition_body = [
        item for item in body_without_doc if not isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    child_names = [
        child.name
        for child in node.body
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return {
        "kind": "class",
        "qualname": qualname,
        "signature_hash": ast_digest([node.bases, node.keywords, child_names]),
        "decorators_hash": ast_digest(node.decorator_list),
        "body_hash": ast_digest(non_definition_body),
        "docstring_hash": text_digest(ast.get_docstring(node, clean=False)),
    }


def strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return body[1:]
    return body


def ast_digest(value: Any) -> str:
    if isinstance(value, list):
        dumped = "[" + ",".join(ast.dump(item, include_attributes=False) if isinstance(item, ast.AST) else repr(item) for item in value) + "]"
    elif isinstance(value, ast.AST):
        dumped = ast.dump(value, include_attributes=False)
    else:
        dumped = repr(value)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:12]


def text_digest(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def diff_python_ast_indexes(old_index: dict[str, Any], new_index: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    old_imports = set(old_index["imports"])
    new_imports = set(new_index["imports"])
    old_symbols: dict[str, dict[str, Any]] = old_index["symbols"]
    new_symbols: dict[str, dict[str, Any]] = new_index["symbols"]
    added_names = sorted(set(new_symbols) - set(old_symbols))
    removed_names = sorted(set(old_symbols) - set(new_symbols))
    common_names = sorted(set(old_symbols) & set(new_symbols))

    symbols_added = [public_symbol(new_symbols[name]) for name in added_names]
    symbols_removed = [public_symbol(old_symbols[name]) for name in removed_names]
    symbols_modified: list[dict[str, Any]] = []
    flags: set[str] = set()

    for name in common_names:
        old = old_symbols[name]
        new = new_symbols[name]
        item = {
            "kind": new["kind"],
            "qualname": name,
            "signature_changed": old["signature_hash"] != new["signature_hash"],
            "body_changed": old["body_hash"] != new["body_hash"],
            "decorators_changed": old["decorators_hash"] != new["decorators_hash"],
            "docstring_changed": old["docstring_hash"] != new["docstring_hash"],
        }
        if any(item[key] for key in ("signature_changed", "body_changed", "decorators_changed", "docstring_changed")):
            symbols_modified.append(item)
            if item["signature_changed"]:
                flags.add("signature_changed")
            if item["body_changed"]:
                flags.add("function_body_changed" if item["kind"] in {"function", "async_function"} else "class_body_changed")
            if item["decorators_changed"]:
                flags.add("decorator_changed")
            if item["docstring_changed"]:
                flags.add("docstring_changed")

    imports_added = sorted(new_imports - old_imports)
    imports_removed = sorted(old_imports - new_imports)
    if imports_added or imports_removed:
        flags.add("import_changed")
    if symbols_added:
        flags.add("symbol_added")
    if symbols_removed:
        flags.add("symbol_removed")

    semantic_modified = [
        item
        for item in symbols_modified
        if item["signature_changed"] or item["body_changed"] or item["decorators_changed"]
    ]
    semantic_changed = bool(imports_added or imports_removed or symbols_added or symbols_removed or semantic_modified)
    if not semantic_changed:
        flags.add("ast_noop" if not symbols_modified else "docstring_only")

    summary = {
        "semantic_changed": semantic_changed,
        "imports_added": imports_added,
        "imports_removed": imports_removed,
        "symbols_added": symbols_added,
        "symbols_removed": symbols_removed,
        "symbols_modified": symbols_modified,
        "symbols_unchanged_count": len(common_names) - len(symbols_modified),
    }
    return summary, sorted(flags)


def public_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    return {"kind": symbol["kind"], "qualname": symbol["qualname"]}


def collect_blame_survival(runner: GitRunner, query: dict[str, Any], files: list[str]) -> Counter:
    candidates: list[str] = []
    target_type = query["target_type"]
    paths = query["normalized_paths"]
    if target_type == "file":
        candidates = [path for path in paths if path in files]
    elif target_type in {"directory", "glob", "module", "symbol"}:
        for path in files:
            if any(path == base or path.startswith(base.rstrip("/") + "/") for base in paths):
                candidates.append(path)
        if not candidates:
            candidates = [path for path in paths if path in files]
    candidates = [path for path in candidates if not is_probably_generated(path)][:25]

    counts: Counter = Counter()
    for path in candidates:
        result = runner.git("blame", "-w", "-M", "-C", "--line-porcelain", "--", path, check=False)
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            if SHA_RE.match(line):
                sha = line.split()[0]
                counts[sha] += 1
    return counts


def is_probably_generated(path: str) -> bool:
    parts = set(Path(path).parts)
    name = Path(path).name
    if parts & GENERATED_PARTS:
        return True
    if name in LOCKFILE_NAMES:
        return True
    if path.endswith((".min.js", ".generated.ts", ".generated.js", ".pb.go")):
        return True
    return False


def classify_flags(commit: dict[str, Any], changes: list[dict[str, Any]], stats: dict[str, Any]) -> list[str]:
    flags: set[str] = set()
    statuses = {change["status"] for change in changes}
    subject = (commit.get("subject") or "").lower()
    body = (commit.get("body_excerpt") or "").lower()
    text = subject + "\n" + body
    changed_paths = [change.get("path", "") for change in changes]

    if "A" in statuses:
        flags.add("birth")
    if "D" in statuses:
        flags.add("delete")
    if "R" in statuses:
        flags.add("rename")
        flags.add("move")
    if "C" in statuses:
        flags.add("copy")
    if commit.get("is_merge"):
        flags.add("merge")
    if "revert" in text:
        flags.add("revert")
    if re.search(r"\b(fix|bug|bugfix|regression|hotfix|harden)\b", text):
        flags.add("bugfix")
    if re.search(r"\b(refactor|rewrite|cleanup|extract|split|simplify)\b", text):
        flags.add("refactor")
    if re.search(r"\b(migrate|migration|upgrade|port|move)\b", text):
        flags.add("migration")
    if re.search(r"\b(security|auth|permission|xss|csrf|cve)\b", text):
        flags.add("security")
    if re.search(r"\b(perf|performance|optimi[sz]e|latency|cache)\b", text):
        flags.add("perf")
    if any("/test/" in path or "/tests/" in path or Path(path).name.startswith("test_") for path in changed_paths):
        flags.add("test")
    if changed_paths and all(is_probably_generated(path) for path in changed_paths):
        flags.add("generated")
    if stats["files"] and stats["files"] >= 20 and (stats["added"] + stats["deleted"]) > 1000:
        flags.add("large-crosscut")
    if looks_format_only(subject, stats):
        flags.add("formatting")
    if is_bot_identity(commit):
        flags.add("bot")
    return sorted(flags)


def looks_format_only(subject: str, stats: dict[str, Any]) -> bool:
    subject = subject.lower()
    if re.search(r"\b(format|lint|prettier|black|gofmt|rustfmt|whitespace)\b", subject):
        return True
    return stats["files"] >= 10 and stats["added"] + stats["deleted"] >= 500 and "test" not in subject


def is_bot_identity(commit: dict[str, Any]) -> bool:
    author = commit.get("author") or {}
    name = (author.get("name") or "").lower()
    return any(pattern in name for pattern in BOT_PATTERNS)


def score_commit(
    commit: dict[str, Any],
    query: dict[str, Any],
    stats: dict[str, Any],
    flags: list[str],
    blame_lines: int,
    max_blame_lines: int,
    author_frequency: Counter,
    index: int,
    total: int,
) -> dict[str, Any]:
    factors: list[dict[str, Any]] = []
    score = 0.0

    target_type = query["target_type"]
    if target_type == "file":
        add_factor(factors, "target_relevance", 25, "Commit touched the exact file target.")
    elif target_type in {"directory", "glob"}:
        add_factor(factors, "target_relevance", 20, "Commit touched files inside the requested path scope.")
    elif target_type == "module":
        add_factor(factors, "target_relevance", 16, "Commit matched module-like paths.")
    elif target_type == "symbol":
        add_factor(factors, "target_relevance", 12, "Commit matched symbol/pickaxe evidence.")
    else:
        add_factor(factors, "target_relevance", 8, "Commit matched an ambiguous target.")

    lifecycle_flags = set(flags) & {"birth", "delete", "rename", "move", "copy"}
    if lifecycle_flags:
        add_factor(factors, "lifecycle_event", 20, f"Lifecycle signal: {', '.join(sorted(lifecycle_flags))}.")
    elif "revert" in flags:
        add_factor(factors, "lifecycle_event", 12, "Revert can mark a historical turn even when it removes code.")

    structural_flags = set(flags) & {"refactor", "migration", "security", "perf", "bugfix"}
    if structural_flags:
        points = min(15, 6 + 3 * len(structural_flags))
        add_factor(factors, "behavior_or_structure", points, f"Intent signal: {', '.join(sorted(structural_flags))}.")

    churn = stats["added"] + stats["deleted"]
    if churn:
        points = min(10, round(math.log1p(churn) * 2.0, 2))
        add_factor(factors, "diff_churn", points, f"{stats['added']} additions and {stats['deleted']} deletions.")

    intent_count = len(set(flags) & {"bugfix", "refactor", "migration", "security", "perf", "revert"})
    if intent_count:
        add_factor(factors, "message_intent", min(10, intent_count * 2.5), "Commit message/body contains intent keywords.")

    if max_blame_lines and blame_lines:
        points = round(10 * blame_lines / max_blame_lines, 2)
        add_factor(factors, "current_survival", points, f"{blame_lines} current blame lines still point at this commit.")

    if total and (index < 3 or index >= total - 3):
        add_factor(factors, "time_boundary", 5, "Commit sits near the start or end of the collected history window.")

    author_key = person_key(commit.get("author") or {})
    if author_frequency[author_key] >= 3:
        add_factor(factors, "people_signal", 5, "Author repeatedly touched the target scope.")

    score = sum(float(item["points"]) for item in factors)
    penalties: list[dict[str, Any]] = []
    if "generated" in flags:
        add_penalty(penalties, "generated_or_vendor", -25, "All changed target files look generated, vendored, or lock-only.")
    if "formatting" in flags:
        add_penalty(penalties, "formatting_noise", -15, "Commit looks formatting-oriented.")
    if "large-crosscut" in flags and target_type == "file":
        add_penalty(penalties, "broad_crosscut", -8, "Large cross-cutting change; target may be incidental.")
    if "bot" in flags and not (set(flags) & {"migration", "security"}):
        add_penalty(penalties, "bot_noise", -8, "Bot author without a strong migration/security signal.")
    score += sum(float(item["points"]) for item in penalties)
    score = max(0.0, min(100.0, round(score, 2)))

    confidence = 0.65
    if lifecycle_flags or blame_lines:
        confidence += 0.15
    if "generated" in flags or "formatting" in flags:
        confidence -= 0.15
    if commit.get("is_merge"):
        confidence -= 0.05
    confidence = max(0.1, min(0.95, round(confidence, 2)))

    return {
        "score": score,
        "confidence": confidence,
        "factors": factors + penalties,
    }


def add_factor(factors: list[dict[str, Any]], name: str, points: float, reason: str) -> None:
    factors.append({"name": name, "points": points, "reason": reason})


def add_penalty(factors: list[dict[str, Any]], name: str, points: float, reason: str) -> None:
    factors.append({"name": name, "points": points, "reason": reason})


def person_key(person: dict[str, Any]) -> str:
    name = person.get("name") or "unknown"
    hashed = person.get("email_hash")
    return f"{name} <{hashed}>" if hashed else name


def build_agent_review(commit: dict[str, Any], query: dict[str, Any], score: float, flags: list[str]) -> dict[str, Any]:
    pathspecs = query["pathspecs"]
    sha = commit["sha"]
    important_flags = set(flags) & {
        "birth",
        "rename",
        "move",
        "delete",
        "refactor",
        "migration",
        "security",
        "perf",
        "revert",
        "merge",
    }
    required = score >= 35 or bool(important_flags)
    if score >= 60 or important_flags & {"rename", "move", "migration", "security", "revert"}:
        priority = "high"
    elif required:
        priority = "medium"
    else:
        priority = "low"

    commands = []
    suffix = " -- " + " ".join(shell_quote(path) for path in pathspecs) if pathspecs else ""
    commands.append(f"git show --stat --summary -M -C {sha}{suffix}")
    if required:
        commands.append(f"git show --format=fuller --patch -M -C {sha}{suffix}")
    if commit.get("is_merge"):
        commands.append(f"git show -m --stat --summary -M -C {sha}{suffix}")

    reason = "Low-ranked background evidence."
    if important_flags:
        reason = f"Read because flags include {', '.join(sorted(important_flags))}."
    elif score >= 35:
        reason = "Read because importance score crosses the review threshold."
    return {"required": required, "priority": priority, "read_commands": commands, "reason": reason}


def build_path_lineage(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    for commit in commits:
        sha = commit["sha"]
        date = commit["author_date"]
        for change in commit.get("changes", []):
            status = change.get("status")
            path = change.get("path")
            old_path = change.get("old_path")
            if status == "R":
                change_type = "rename"
            elif status == "C":
                change_type = "copy"
            elif status == "A":
                change_type = "add"
            elif status == "D":
                change_type = "delete"
            elif status == "M":
                change_type = "modify"
            else:
                change_type = "modify"
            if change_type in {"modify"}:
                continue
            lineage.append(
                {
                    "current_path": path,
                    "previous_path": old_path,
                    "commit": sha,
                    "date": date,
                    "change_type": change_type,
                    "similarity": change.get("similarity"),
                    "confidence": lineage_confidence(change_type, change.get("similarity")),
                }
            )
    return lineage


def lineage_confidence(change_type: str, similarity: int | None) -> float:
    if change_type == "rename" and similarity is not None:
        return round(min(0.95, max(0.55, similarity / 100)), 2)
    if change_type in {"add", "delete"}:
        return 0.85
    if change_type == "copy":
        return 0.65
    return 0.5


def build_people(commits: list[dict[str, Any]], blame_counts: Counter) -> list[dict[str, Any]]:
    people: dict[str, dict[str, Any]] = {}
    for commit in commits:
        key = person_key(commit["author"])
        entry = people.setdefault(
            key,
            {
                "identity": key,
                "first_touch": commit["author_date"],
                "last_touch": commit["author_date"],
                "commit_count": 0,
                "weighted_importance": 0.0,
                "current_blame_lines": 0,
            },
        )
        entry["commit_count"] += 1
        entry["weighted_importance"] += commit["importance"]["score"]
        entry["first_touch"] = min(entry["first_touch"], commit["author_date"])
        entry["last_touch"] = max(entry["last_touch"], commit["author_date"])
    sha_to_author = {commit["sha"]: person_key(commit["author"]) for commit in commits}
    for sha, count in blame_counts.items():
        key = sha_to_author.get(sha)
        if key and key in people:
            people[key]["current_blame_lines"] += count
    for entry in people.values():
        entry["weighted_importance"] = round(entry["weighted_importance"], 2)
    return sorted(
        people.values(),
        key=lambda item: (item["weighted_importance"], item["current_blame_lines"], item["commit_count"]),
        reverse=True,
    )


def build_maintenance_signals(people: list[dict[str, Any]]) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    for person in people[:10]:
        roles: list[str] = []
        if person["commit_count"] > 0:
            roles.append("author_activity")
        if person["weighted_importance"] >= 50:
            roles.append("high_weight_local_history")
        if person["current_blame_lines"] > 0:
            roles.append("current_survivorship")
        signals.append(
            {
                "identity": person["identity"],
                "evidence_roles": roles,
                "metrics": {
                    "commit_count": person["commit_count"],
                    "weighted_importance": person["weighted_importance"],
                    "current_blame_lines": person["current_blame_lines"],
                },
                "caveat": "Activity, review, and blame signals are not ownership proof or performance judgment.",
            }
        )
    return {
        "caveat": "Use as maintenance evidence only. Do not infer private motivation, team politics, blame, or individual performance.",
        "people": signals,
    }


def collect_external_evidence(
    runner: GitRunner,
    commits: list[dict[str, Any]],
    query: dict[str, Any],
    mode: str,
    remote_limit: int,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": REMOTE_CONTEXT_SCHEMA_VERSION,
        "enabled": mode != "off",
        "provider": None,
        "repository": None,
        "remote_url": None,
        "fetched_at": None,
        "warnings": [],
        "artifacts": [],
        "recorded_rationales": [],
        "collaboration_signals": [],
        "caveat": "Remote evidence is opt-in and supports recorded collaboration facts only; it is not motivation, politics, or performance evidence.",
    }
    if mode == "off":
        return base

    remote = get_origin_remote(runner)
    if not remote:
        base["warnings"].append("No origin remote was found; remote evidence skipped.")
        return base
    base["remote_url"] = redact_remote_url(remote)
    provider = parse_remote_provider(remote)
    if not provider:
        base["warnings"].append("Origin remote is not recognized as GitHub or GitLab; remote evidence skipped.")
        return base
    if mode != "auto" and mode != provider["provider"]:
        base["warnings"].append(f"Requested provider {mode!r} does not match origin remote provider {provider['provider']!r}.")
        return base

    base["provider"] = provider["provider"]
    base["repository"] = provider["slug"]
    base["fetched_at"] = datetime.now(timezone.utc).isoformat()

    if provider["provider"] == "github":
        enrich_github_evidence(base, provider, commits[:remote_limit], query)
    elif provider["provider"] == "gitlab":
        enrich_gitlab_evidence(base, provider, commits[:remote_limit], query)
    return base


def get_origin_remote(runner: GitRunner) -> str | None:
    result = runner.git("remote", "get-url", "origin", check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def redact_remote_url(remote: str) -> str:
    return re.sub(r"(https?://)[^/@\s]+@", r"\1redacted@", remote)


def parse_remote_provider(remote: str) -> dict[str, str] | None:
    github = parse_hosted_git_remote(remote, "github.com")
    if github:
        return {"provider": "github", "slug": github, "api_base": "https://api.github.com"}
    gitlab = parse_hosted_git_remote(remote, "gitlab.com")
    if gitlab:
        return {"provider": "gitlab", "slug": gitlab, "api_base": "https://gitlab.com/api/v4"}
    return None


def parse_hosted_git_remote(remote: str, host: str) -> str | None:
    ssh_match = re.match(rf"git@{re.escape(host)}:(?P<slug>.+?)(?:\.git)?$", remote)
    if ssh_match:
        return strip_git_suffix(ssh_match.group("slug"))
    parsed = urllib.parse.urlparse(remote)
    if parsed.hostname == host:
        return strip_git_suffix(parsed.path.strip("/"))
    return None


def strip_git_suffix(slug: str) -> str:
    return slug[:-4] if slug.endswith(".git") else slug


def enrich_github_evidence(
    external: dict[str, Any],
    provider: dict[str, str],
    commits: list[dict[str, Any]],
    query: dict[str, Any],
) -> None:
    slug = provider["slug"]
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "code-archaeology-skill",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    seen_artifacts: set[str] = set()
    issue_numbers: set[str] = set()

    for commit in commits:
        sha = commit["sha"]
        for ref in commit.get("recorded_context", {}).get("issue_references", []):
            if ref.get("number"):
                issue_numbers.add(str(ref["number"]))
        pr_url = f"{provider['api_base']}/repos/{slug}/commits/{sha}/pulls"
        prs = fetch_json(pr_url, headers, external["warnings"])
        if not isinstance(prs, list):
            continue
        for pr in prs:
            number = str(pr.get("number") or "")
            if not number:
                continue
            artifact_id = f"GH-PR-{number}"
            if artifact_id in seen_artifacts:
                continue
            seen_artifacts.add(artifact_id)
            body = pr.get("body") or ""
            title = pr.get("title") or ""
            artifact = {
                "id": artifact_id,
                "type": "pull_request",
                "url": pr.get("html_url"),
                "title": title,
                "state": pr.get("state"),
                "author": (pr.get("user") or {}).get("login"),
                "created_at": pr.get("created_at"),
                "merged_at": pr.get("merged_at"),
                "merge_commit_sha": pr.get("merge_commit_sha"),
                "related_commits": [sha],
                "related_paths": query.get("normalized_paths", []),
                "link_method": "commit_pull_requests_api",
                "link_confidence": 0.95,
                "referenced_issues": extract_issue_references("\n".join([title, body])),
                "limitations": [],
            }
            reviews = fetch_json(f"{provider['api_base']}/repos/{slug}/pulls/{number}/reviews", headers, external["warnings"])
            if isinstance(reviews, list):
                artifact["reviewers"] = compact_github_reviews(reviews)
            external["artifacts"].append(artifact)
            append_external_rationales(external, artifact_id, "\n".join([title, body]), artifact.get("author"), artifact.get("created_at"))

    for number in sorted(issue_numbers)[:20]:
        artifact_id = f"GH-ISSUE-{number}"
        if artifact_id in seen_artifacts:
            continue
        issue = fetch_json(f"{provider['api_base']}/repos/{slug}/issues/{number}", headers, external["warnings"])
        if not isinstance(issue, dict) or not issue.get("number"):
            continue
        seen_artifacts.add(artifact_id)
        artifact_type = "pull_request" if issue.get("pull_request") else "issue"
        artifact = {
            "id": artifact_id,
            "type": artifact_type,
            "url": issue.get("html_url"),
            "title": issue.get("title"),
            "state": issue.get("state"),
            "author": (issue.get("user") or {}).get("login"),
            "created_at": issue.get("created_at"),
            "closed_at": issue.get("closed_at"),
            "related_commits": [],
            "related_paths": query.get("normalized_paths", []),
            "link_method": "commit_text_reference",
            "link_confidence": 0.65,
            "labels": [label.get("name") for label in issue.get("labels", []) if isinstance(label, dict)],
            "limitations": ["Commit text reference does not prove causality."],
        }
        external["artifacts"].append(artifact)
        append_external_rationales(external, artifact_id, "\n".join([issue.get("title") or "", issue.get("body") or ""]), artifact.get("author"), artifact.get("created_at"))

    external["collaboration_signals"] = build_remote_collaboration_signals(external["artifacts"])


def compact_github_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for review in reviews:
        login = (review.get("user") or {}).get("login")
        state = review.get("state")
        key = (login, state)
        if key in seen:
            continue
        compacted.append({"login": login, "role": str(state or "").lower(), "date": review.get("submitted_at")})
        seen.add(key)
    return compacted[:20]


def enrich_gitlab_evidence(
    external: dict[str, Any],
    provider: dict[str, str],
    commits: list[dict[str, Any]],
    query: dict[str, Any],
) -> None:
    slug = provider["slug"]
    encoded_slug = urllib.parse.quote(slug, safe="")
    headers = {"User-Agent": "code-archaeology-skill"}
    token = os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN")
    if token:
        headers["PRIVATE-TOKEN"] = token
    seen_artifacts: set[str] = set()
    issue_numbers: set[str] = set()
    for commit in commits:
        sha = commit["sha"]
        for ref in commit.get("recorded_context", {}).get("issue_references", []):
            if ref.get("number"):
                issue_numbers.add(str(ref["number"]))
        url = f"{provider['api_base']}/projects/{encoded_slug}/repository/commits/{sha}/merge_requests"
        merge_requests = fetch_json(url, headers, external["warnings"])
        if not isinstance(merge_requests, list):
            continue
        for mr in merge_requests:
            iid = str(mr.get("iid") or mr.get("id") or "")
            if not iid:
                continue
            artifact_id = f"GL-MR-{iid}"
            if artifact_id in seen_artifacts:
                continue
            seen_artifacts.add(artifact_id)
            artifact = {
                "id": artifact_id,
                "type": "merge_request",
                "url": mr.get("web_url"),
                "title": mr.get("title"),
                "state": mr.get("state"),
                "author": (mr.get("author") or {}).get("username"),
                "created_at": mr.get("created_at"),
                "merged_at": mr.get("merged_at"),
                "merge_commit_sha": mr.get("merge_commit_sha"),
                "related_commits": [sha],
                "related_paths": query.get("normalized_paths", []),
                "link_method": "commit_merge_requests_api",
                "link_confidence": 0.9,
                "referenced_issues": extract_issue_references("\n".join([mr.get("title") or "", mr.get("description") or ""])),
                "limitations": [],
            }
            external["artifacts"].append(artifact)
            append_external_rationales(
                external,
                artifact_id,
                "\n".join([mr.get("title") or "", mr.get("description") or ""]),
                artifact.get("author"),
                artifact.get("created_at"),
            )
    for number in sorted(issue_numbers)[:20]:
        artifact_id = f"GL-ISSUE-{number}"
        if artifact_id in seen_artifacts:
            continue
        issue = fetch_json(f"{provider['api_base']}/projects/{encoded_slug}/issues/{number}", headers, external["warnings"])
        if not isinstance(issue, dict) or not issue.get("iid"):
            continue
        seen_artifacts.add(artifact_id)
        artifact = {
            "id": artifact_id,
            "type": "issue",
            "url": issue.get("web_url"),
            "title": issue.get("title"),
            "state": issue.get("state"),
            "author": (issue.get("author") or {}).get("username"),
            "created_at": issue.get("created_at"),
            "closed_at": issue.get("closed_at"),
            "related_commits": [],
            "related_paths": query.get("normalized_paths", []),
            "link_method": "commit_text_reference",
            "link_confidence": 0.65,
            "labels": issue.get("labels", []),
            "limitations": ["Commit text reference does not prove causality."],
        }
        external["artifacts"].append(artifact)
        append_external_rationales(
            external,
            artifact_id,
            "\n".join([issue.get("title") or "", issue.get("description") or ""]),
            artifact.get("author"),
            artifact.get("created_at"),
        )
    external["collaboration_signals"] = build_remote_collaboration_signals(external["artifacts"])


def fetch_json(url: str, headers: dict[str, str], warnings: list[str]) -> Any:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        warnings.append(f"Remote fetch failed {exc.code}: {url}")
        return None
    except urllib.error.URLError as exc:
        warnings.append(f"Remote fetch failed: {exc.reason}")
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        warnings.append(f"Remote response was not valid JSON: {url}")
        return None


def append_external_rationales(
    external: dict[str, Any],
    artifact_id: str,
    text: str,
    author: str | None,
    date: str | None,
) -> None:
    for item in extract_explicit_rationales(text):
        external["recorded_rationales"].append(
            {
                "id": f"R{len(external['recorded_rationales']) + 1}",
                "source_artifact": artifact_id,
                "statement_type": item["statement_type"],
                "text": item["text"],
                "author": author,
                "date": date,
                "confidence": 0.8,
                "caveat": "Recorded rationale only; not a private motive inference.",
            }
        )


def build_remote_collaboration_signals(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    people: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        author = artifact.get("author")
        if author:
            entry = people.setdefault(author, {"person": author, "roles": Counter(), "artifact_ids": []})
            entry["roles"]["author"] += 1
            entry["artifact_ids"].append(artifact["id"])
        for review in artifact.get("reviewers", []):
            login = review.get("login")
            if not login:
                continue
            entry = people.setdefault(login, {"person": login, "roles": Counter(), "artifact_ids": []})
            entry["roles"][review.get("role") or "reviewer"] += 1
            entry["artifact_ids"].append(artifact["id"])
    signals: list[dict[str, Any]] = []
    for entry in people.values():
        signals.append(
            {
                "person": entry["person"],
                "evidence_roles": dict(entry["roles"]),
                "artifact_ids": sorted(set(entry["artifact_ids"])),
                "caveat": "Collaboration activity is not ownership proof or performance judgment.",
            }
        )
    return sorted(signals, key=lambda item: sum(item["evidence_roles"].values()), reverse=True)


def build_timeline_candidates(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for commit in commits:
        bucket = quarter_bucket(commit["author_date"])
        buckets[bucket].append(commit)

    candidates: list[dict[str, Any]] = []
    for bucket, items in sorted(buckets.items()):
        flags = Counter(flag for commit in items for flag in commit.get("flags", []))
        top_flags = [flag for flag, _ in flags.most_common(5)]
        candidates.append(
            {
                "phase": bucket,
                "start": min(commit["author_date"] for commit in items),
                "end": max(commit["author_date"] for commit in items),
                "commit_shas": [commit["sha"] for commit in sorted(items, key=lambda c: c["importance"]["score"], reverse=True)[:8]],
                "signals": top_flags,
            }
        )
    return candidates


def quarter_bucket(iso_date: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        quarter = ((dt.month - 1) // 3) + 1
        return f"{dt.year}-Q{quarter}"
    except ValueError:
        return "unknown-date"


def collect_all(args: argparse.Namespace) -> dict[str, Any]:
    runner, repo_info = get_repo_info(args.repo)
    warnings: list[str] = []
    if repo_info["is_shallow"]:
        warnings.append(
            "Repository is shallow; avoid definitive earliest/first-ever claims unless history is deepened."
        )
    if any(line and not line.startswith("##") for line in repo_info["status"]):
        warnings.append("Working tree has local changes; current-shape observations may differ from committed history.")

    files = list_tracked_files(runner)
    query = resolve_target(runner, args.target, files)
    if query["target_type"] == "ambiguous" or not query["pathspecs"]:
        warnings.append("Target could not be resolved cleanly; inspect query.ambiguities before writing conclusions.")

    shas = collect_commits(
        runner,
        query,
        max_commits=args.max_commits,
        rev_range=args.rev_range,
        since=args.since,
        until=args.until,
        include_merges=not args.no_merges,
    )
    if not shas:
        warnings.append("No relevant commits found for the requested target and range.")

    blame_counts = collect_blame_survival(runner, query, files)
    max_blame = max(blame_counts.values()) if blame_counts else 0

    author_frequency: Counter = Counter()
    raw_commits: list[dict[str, Any]] = []
    for sha in shas:
        commit = parse_commit_metadata(runner, sha)
        author_frequency[person_key(commit["author"])] += 1
        raw_commits.append(commit)

    commits: list[dict[str, Any]] = []
    total = len(raw_commits)
    for index, commit in enumerate(raw_commits):
        changes, stats, changed_paths = collect_change_details(runner, commit["sha"], query["pathspecs"])
        flags = classify_flags(commit, changes, stats)
        importance = score_commit(
            commit,
            query,
            stats,
            flags,
            blame_counts.get(commit["sha"], 0),
            max_blame,
            author_frequency,
            index,
            total,
        )
        review = build_agent_review(commit, query, importance["score"], flags)
        commit_payload = {
            **commit,
            "changed_paths": changed_paths,
            "target_stats": {
                "files": stats["files"],
                "added": stats["added"],
                "deleted": stats["deleted"],
                "binary_files": stats["binary_files"],
            },
            "flags": flags,
            "importance": importance,
            "agent_review": review,
            "changes": changes,
            "recorded_context": build_recorded_context(commit),
        }
        if args.ast_diff:
            semantic_diffs, semantic_summary = collect_semantic_diffs(
                runner,
                commit,
                changes,
                args.ast_max_files,
                args.ast_max_blob_bytes,
            )
            commit_payload["semantic_diffs"] = semantic_diffs
            commit_payload["semantic_diff_summary"] = semantic_summary
        commits.append(commit_payload)

    commits.sort(key=lambda item: (item["importance"]["score"], item["author_date"]), reverse=True)
    if args.top_k and args.top_k > 0:
        review_shas = {commit["sha"] for commit in commits[: args.top_k]}
        for commit in commits:
            if commit["sha"] in review_shas and commit["agent_review"]["priority"] == "low":
                commit["agent_review"]["required"] = True
                commit["agent_review"]["priority"] = "medium"
                commit["agent_review"]["reason"] = "Read because commit is inside the top-k evidence window."

    people = build_people(commits, blame_counts)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "repo": repo_info,
        "query": query,
        "collection": {
            "commands_run": runner.commands_run,
            "limits": {
                "max_commits": args.max_commits,
                "top_k_enriched": args.top_k,
                "ast_max_files_per_commit": args.ast_max_files,
                "ast_max_blob_bytes": args.ast_max_blob_bytes,
                "remote_limit": args.remote_limit,
            },
            "rev_range": args.rev_range,
            "since": args.since,
            "until": args.until,
            "warnings": warnings,
        },
        "semantic_diff": {
            "enabled": bool(args.ast_diff),
            "schema_version": AST_DIFF_SCHEMA_VERSION,
            "languages": ["python"],
            "limits": {
                "max_files_per_commit": args.ast_max_files,
                "max_blob_bytes": args.ast_max_blob_bytes,
            },
        },
        "path_lineage": build_path_lineage(commits),
        "commits": commits,
        "people": people,
        "maintenance_signals": build_maintenance_signals(people),
        "external_evidence": collect_external_evidence(
            runner,
            commits,
            query,
            args.remote_context,
            args.remote_limit,
        ),
        "timeline_candidates": build_timeline_candidates(commits),
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect JSON git evidence for a code archaeology report.",
    )
    parser.add_argument("target", help="File, directory, glob, module name, or symbol to investigate.")
    parser.add_argument("--repo", default=".", help="Repository path. Defaults to current directory.")
    parser.add_argument("--rev-range", help="Optional git revision range, such as v1.2.0..HEAD.")
    parser.add_argument("--since", help="Optional git --since date, such as 2025-01-01 or '18 months ago'.")
    parser.add_argument("--until", help="Optional git --until date.")
    parser.add_argument("--max-commits", type=int, default=300, help="Maximum candidate commits to collect.")
    parser.add_argument("--top-k", type=int, default=20, help="Number of top commits to force into review.")
    parser.add_argument("--no-merges", action="store_true", help="Exclude merge commits from initial collection.")
    parser.add_argument("--ast-diff", action="store_true", help="Add Python AST symbol diff evidence for changed files.")
    parser.add_argument(
        "--ast-max-files",
        type=int,
        default=DEFAULT_AST_MAX_FILES,
        help="Maximum files per commit to analyze with --ast-diff.",
    )
    parser.add_argument(
        "--ast-max-blob-bytes",
        type=int,
        default=DEFAULT_AST_MAX_BLOB_BYTES,
        help="Maximum blob size to parse with --ast-diff.",
    )
    parser.add_argument(
        "--remote-context",
        choices=["off", "auto", "github", "gitlab"],
        default="off",
        help="Optionally fetch GitHub/GitLab PR and issue evidence. Default: off.",
    )
    parser.add_argument(
        "--remote-limit",
        type=int,
        default=20,
        help="Maximum top-ranked commits to enrich when --remote-context is enabled.",
    )
    parser.add_argument("--output", help="Write JSON to this file instead of stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = collect_all(args)
    except GitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
