#!/usr/bin/env python3
"""Render code-archaeology collector JSON into a standalone HTML timeline."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_PREFIXES = ("0.",)


def esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def short_sha(value: str | None) -> str:
    return (value or "")[:12]


def badge(value: str) -> str:
    return f'<span class="badge">{esc(value)}</span>'


def render_badges(values: list[Any]) -> str:
    if not values:
        return '<span class="muted">none</span>'
    return " ".join(badge(str(value)) for value in values)


def render_timeline(payload: dict[str, Any], title: str | None = None) -> str:
    repo = payload.get("repo", {})
    query = payload.get("query", {})
    collection = payload.get("collection", {})
    commits = payload.get("commits", [])
    commit_by_sha = {commit.get("sha"): commit for commit in commits}
    page_title = title or "Code Archaeology Timeline"

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc(page_title)}</title>",
            "<style>",
            css(),
            "</style>",
            "</head>",
            "<body>",
            '<main class="shell">',
            render_header(page_title, repo, query),
            render_warnings(collection.get("warnings", [])),
            render_phases(payload.get("timeline_candidates", []), commit_by_sha),
            render_commits(commits),
            render_people(payload.get("people", []), payload.get("maintenance_signals", {})),
            render_external(payload.get("external_evidence", {})),
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def css() -> str:
    return """
:root {
  color-scheme: light;
  --ink: #172033;
  --muted: #5d6b82;
  --line: #d9e1ec;
  --panel: #f7f9fc;
  --accent: #0f766e;
  --accent-2: #9f1239;
  --badge: #e8eef7;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: #ffffff;
  font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.shell {
  width: min(1120px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 28px 0 48px;
}
header {
  border-bottom: 2px solid var(--line);
  padding-bottom: 18px;
}
h1 {
  margin: 0 0 8px;
  font-size: clamp(28px, 5vw, 48px);
  line-height: 1;
  letter-spacing: 0;
}
h2 {
  margin: 28px 0 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
  font-size: 18px;
  letter-spacing: 0;
}
.meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px 16px;
  color: var(--muted);
}
.label {
  display: block;
  color: var(--ink);
  font-weight: 700;
}
.notice {
  margin: 14px 0;
  padding: 10px 12px;
  border-left: 4px solid var(--accent-2);
  background: #fff1f2;
}
.timeline {
  display: grid;
  gap: 12px;
}
.phase,
.commit,
.person,
.external {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  padding: 14px;
}
.phase-head,
.commit-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}
.phase-title,
.commit-title {
  font-weight: 800;
  font-size: 16px;
}
.score {
  color: var(--accent);
  font-weight: 800;
}
.muted {
  color: var(--muted);
}
.badge {
  display: inline-block;
  margin: 2px 4px 2px 0;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--badge);
  color: #24324a;
  font-size: 12px;
  white-space: nowrap;
}
.paths {
  margin-top: 8px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
code {
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 0.95em;
}
""".strip()


def render_header(title: str, repo: dict[str, Any], query: dict[str, Any]) -> str:
    target = query.get("raw_target") or query.get("normalized_target") or ", ".join(query.get("normalized_paths", []))
    return "\n".join(
        [
            "<header>",
            f"<h1>{esc(title)}</h1>",
            '<div class="meta">',
            meta_item("Target", target),
            meta_item("Type", query.get("target_type")),
            meta_item("Repo", repo.get("root")),
            meta_item("Branch", repo.get("branch") or "detached"),
            meta_item("Head", short_sha(repo.get("head"))),
            meta_item("History Complete", str(repo.get("history_complete"))),
            "</div>",
            "</header>",
        ]
    )


def meta_item(label: str, value: Any) -> str:
    return f'<div><span class="label">{esc(label)}</span>{esc(value)}</div>'


def render_warnings(warnings: list[Any]) -> str:
    if not warnings:
        return ""
    items = "\n".join(f"<div>{esc(item)}</div>" for item in warnings)
    return f'<section class="notice"><strong>Warnings</strong>{items}</section>'


def render_phases(phases: list[dict[str, Any]], commit_by_sha: dict[str, dict[str, Any]]) -> str:
    if not phases:
        return '<section><h2>Timeline Phases</h2><p class="muted">No timeline candidates were collected.</p></section>'
    rows = []
    for phase in phases:
        commits = []
        for sha in phase.get("commit_shas", []):
            commit = commit_by_sha.get(sha, {})
            commits.append(f'<code>{esc(short_sha(sha))}</code> {esc(commit.get("subject", ""))}')
        rows.append(
            "\n".join(
                [
                    '<article class="phase">',
                    '<div class="phase-head">',
                    f'<div class="phase-title">{esc(phase.get("phase"))}</div>',
                    f'<div class="muted">{esc(phase.get("start"))} - {esc(phase.get("end"))}</div>',
                    "</div>",
                    f'<div>{render_badges(phase.get("signals", []))}</div>',
                    f'<div class="paths">{"<br>".join(commits)}</div>',
                    "</article>",
                ]
            )
        )
    return '<section><h2>Timeline Phases</h2><div class="timeline">' + "\n".join(rows) + "</div></section>"


def render_commits(commits: list[dict[str, Any]]) -> str:
    if not commits:
        return '<section><h2>Key Commits</h2><p class="muted">No commits were collected.</p></section>'
    rows = []
    for commit in commits[:30]:
        importance = commit.get("importance", {})
        semantic = commit.get("semantic_diff_summary", {})
        context = commit.get("recorded_context", {})
        refs = [item.get("raw") for item in context.get("issue_references", []) if item.get("raw")]
        rationales = [item.get("text") for item in context.get("explicit_rationales", []) if item.get("text")]
        extra = []
        if semantic:
            extra.append("AST: " + ", ".join(str(flag) for flag in semantic.get("flags", [])))
        if refs:
            extra.append("Refs: " + ", ".join(refs))
        if rationales:
            extra.append("Rationale: " + " | ".join(rationales))
        rows.append(
            "\n".join(
                [
                    '<article class="commit">',
                    '<div class="commit-head">',
                    f'<div class="commit-title"><code>{esc(short_sha(commit.get("sha")))}</code> {esc(commit.get("subject"))}</div>',
                    f'<div class="score">{esc(importance.get("score", 0))}</div>',
                    "</div>",
                    f'<div class="muted">{esc(commit.get("author_date"))} confidence {esc(importance.get("confidence", ""))}</div>',
                    f'<div>{render_badges(commit.get("flags", []))}</div>',
                    f'<div class="paths">{esc(", ".join(commit.get("changed_paths", [])))}</div>',
                    f'<div class="paths">{esc(" / ".join(extra))}</div>' if extra else "",
                    "</article>",
                ]
            )
        )
    return '<section><h2>Key Commits</h2><div class="timeline">' + "\n".join(rows) + "</div></section>"


def render_people(people: list[dict[str, Any]], maintenance: dict[str, Any]) -> str:
    if not people:
        return '<section><h2>People Signals</h2><p class="muted">No people signals were collected.</p></section>'
    rows = []
    for person in people[:12]:
        rows.append(
            "\n".join(
                [
                    '<article class="person">',
                    f'<strong>{esc(person.get("identity"))}</strong>',
                    f'<div class="muted">{esc(person.get("first_touch"))} - {esc(person.get("last_touch"))}</div>',
                    f'<div>commits {esc(person.get("commit_count"))}; weighted {esc(person.get("weighted_importance"))}; current blame lines {esc(person.get("current_blame_lines"))}</div>',
                    "</article>",
                ]
            )
        )
    caveat = maintenance.get("caveat") or "People signals are not ownership proof or performance judgment."
    return (
        '<section><h2>People Signals</h2>'
        f'<p class="muted">{esc(caveat)}</p>'
        '<div class="grid">'
        + "\n".join(rows)
        + "</div></section>"
    )


def render_external(external: dict[str, Any]) -> str:
    enabled = external.get("enabled")
    artifacts = external.get("artifacts", [])
    warnings = external.get("warnings", [])
    rows = []
    for artifact in artifacts[:20]:
        rows.append(
            "\n".join(
                [
                    '<article class="external">',
                    f'<strong>{esc(artifact.get("id"))}</strong> {esc(artifact.get("title"))}',
                    f'<div class="muted">{esc(artifact.get("type"))} {esc(artifact.get("state"))} {esc(artifact.get("url"))}</div>',
                    f'<div>{render_badges(artifact.get("limitations", []))}</div>',
                    "</article>",
                ]
            )
        )
    if not rows:
        rows.append('<p class="muted">Remote evidence is disabled or no linked remote artifacts were found.</p>')
    warning_html = render_warnings(warnings)
    return (
        '<section><h2>Remote Evidence</h2>'
        f'<p class="muted">enabled={esc(enabled)} provider={esc(external.get("provider"))}. {esc(external.get("caveat"))}</p>'
        + warning_html
        + '<div class="timeline">'
        + "\n".join(rows)
        + "</div></section>"
    )


def load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read input: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("input JSON must be an object")
    schema = str(payload.get("schema_version", ""))
    if not schema.startswith(SUPPORTED_SCHEMA_PREFIXES):
        raise ValueError(f"unsupported schema_version: {schema or '<missing>'}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render code archaeology JSON as a standalone HTML timeline.")
    parser.add_argument("input", help="Collector JSON file.")
    parser.add_argument("--output", default="timeline.html", help="HTML output path. Defaults to timeline.html.")
    parser.add_argument("--title", help="Optional page title.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = load_payload(Path(args.input))
        rendered = render_timeline(payload, args.title)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
