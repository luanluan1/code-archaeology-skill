#!/usr/bin/env python3
"""Collect auditable git evidence for the code-archaeology skill.

The script intentionally stops at evidence collection and lightweight ranking.
It does not explain why a module evolved; the calling agent must read the
recommended diffs and write evidence-backed conclusions.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"
FIELD_SEP = "\x1f"
SHA_RE = re.compile(r"^[0-9a-f]{40}(?:\s|$)")
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if check and result.returncode != 0:
            raise GitError(result.stderr.strip() or result.stdout.strip() or "git command failed")
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
        commits.append(
            {
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
            }
        )

    commits.sort(key=lambda item: (item["importance"]["score"], item["author_date"]), reverse=True)
    if args.top_k and args.top_k > 0:
        review_shas = {commit["sha"] for commit in commits[: args.top_k]}
        for commit in commits:
            if commit["sha"] in review_shas and commit["agent_review"]["priority"] == "low":
                commit["agent_review"]["required"] = True
                commit["agent_review"]["priority"] = "medium"
                commit["agent_review"]["reason"] = "Read because commit is inside the top-k evidence window."

    payload = {
        "schema_version": SCHEMA_VERSION,
        "repo": repo_info,
        "query": query,
        "collection": {
            "commands_run": runner.commands_run,
            "limits": {"max_commits": args.max_commits, "top_k_enriched": args.top_k},
            "rev_range": args.rev_range,
            "since": args.since,
            "until": args.until,
            "warnings": warnings,
        },
        "path_lineage": build_path_lineage(commits),
        "commits": commits,
        "people": build_people(commits, blame_counts),
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
