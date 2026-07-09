---
name: code-archaeology
description: Use when the user asks to analyze git history or code archaeology for a file, directory, module, symbol, key commits, key people, historical turning points, ownership, "why did this become this way", 代码考古, 模块演化, 关键提交, 关键人, or 历史转折点.
---

# Code Archaeology

## Overview

Generate evidence-backed archaeology reports that explain how a code area evolved. Treat git history as evidence, not truth: collect first, inspect important diffs, then write conclusions with explicit evidence and uncertainty.

## Required Workflow

1. Identify the repository, target, and range.
   - Target can be a file, directory, glob, module name, or symbol.
   - Default repository is the current workspace.
   - Default range is all available local history.
   - If no target is provided, ask for the target before continuing.
2. Run the bundled collector before making historical claims:

```bash
python <skill-dir>/scripts/collect_git_history.py --repo <repo> --max-commits 300 --top-k 20 <target>
```

Use `--rev-range`, `--since`, `--until`, or `--no-merges` when the user requests a narrower history.

3. Inspect the JSON warnings and `query.ambiguities`.
   - If the target is ambiguous, ask the user to pick a path unless a safe obvious scope exists.
   - If `repo.history_complete` is false, avoid "first", "earliest", and "origin" claims.
   - If the target is too broad, narrow it or state the sampling strategy.
4. Read key diffs before writing the report.
   - Run `agent_review.read_commands` for every high-priority commit.
   - Read medium-priority commits until the main timeline is explainable, usually 8-15 commits.
   - Always read lifecycle commits: birth, rename, move, delete, migration, revert, and important merge commits.
5. Load the needed references:
   - Read `references/evidence-rules.md` before writing any report.
   - Read `references/report-template.md` when producing the final Markdown.
   - Read `references/workflow.md` for broad, ambiguous, merge-heavy, or shallow histories.
   - Read `references/scoring.md` when explaining why a commit is "key".
6. Write the report as Markdown. Every non-trivial factual claim must cite an evidence ID or be marked as inference/unknown.

## Collector Contract

The collector outputs JSON with:

- `repo`: root, branch, head, shallow status, working tree warnings.
- `query`: resolved target type, paths, pathspecs, ambiguities.
- `commits`: candidate commits sorted by importance, with flags, changed paths, target stats, scoring factors, and review commands.
- `path_lineage`: add/delete/rename/copy/move evidence.
- `people`: author identities, first/last touch, weighted importance, current blame lines.
- `timeline_candidates`: coarse time buckets for phase building.

The collector ranks evidence; it does not decide the historical explanation.

## Evidence Discipline

- Do not invent PRs, issues, design docs, reviewers, business motivations, or author intent.
- Do not treat commit messages as complete truth; verify important claims against diffs.
- Distinguish fact, inference, and unknown.
- Cite historical code by commit SHA plus file/hunk, not current line number.
- Cite current code as `HEAD:<path>:<line>` only after reading the current file.
- For merge commits, inspect parent diffs when the merge itself matters.
- For squash/rebase/shallow histories, state the limitation.

## Quick Commands

```bash
# Standard file or directory investigation
python <skill-dir>/scripts/collect_git_history.py --repo . src/auth

# Limited date range
python <skill-dir>/scripts/collect_git_history.py --repo . --since 2025-01-01 src/auth

# Version range
python <skill-dir>/scripts/collect_git_history.py --repo . --rev-range v1.2.0..HEAD src/auth

# Save reusable evidence
python <skill-dir>/scripts/collect_git_history.py --repo . --output archaeology.json src/auth
```

## Common Mistakes

| Mistake | Fix |
|---|---|
| Reading `git log` manually and skipping the collector | Run the collector first so rename, blame, scoring, and warnings are captured. |
| Calling the top committer the "owner" | Use commit count, weighted importance, lifecycle commits, and current blame separately. |
| Treating a formatting migration as the main turning point | Check flags and scoring penalties; read the diff before elevating it. |
| Saying "this was introduced first" in a shallow clone | Mark it unknown unless full history is available. |
| Reporting a timeline as a commit list | Cluster commits into phases with themes and evidence. |

## Output Standard

The final report should help an engineer safely change the code tomorrow. Prefer concise conclusions, a phase timeline, key turning points, key people, legacy constraints, maintenance advice, evidence index, and unknowns.
