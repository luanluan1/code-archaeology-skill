# Investigation Workflow

## Target Handling

Use the collector's `query.target_type`:

- `file`: trust `git log --follow` most, but inspect rename records.
- `directory`: directory history does not support perfect `--follow`; rely on `name-status -M -C`, path lineage, and hotspot files.
- `glob`: treat as an explicit file set; mention if the glob misses moved/deleted files.
- `module`: check ambiguity. Module names often map to multiple files.
- `symbol`: use pickaxe evidence as a hint, then inspect diffs. Symbol search can miss renames and generated code.
- `ambiguous`: ask for a narrower target unless the user explicitly requested a broad survey.

## Reading Order

1. Read `collection.warnings` and `query.ambiguities`.
2. Skim `path_lineage` for birth, delete, rename, copy, and move.
3. Skim `recorded_context` for issue references and explicit rationale, but do not treat it as causality.
4. Skim `semantic_diffs` when present to spot Python symbol/import changes before opening patches.
5. Read high-priority `agent_review.read_commands`.
6. Read enough medium-priority commits to explain every major phase.
7. Inspect current files before writing "current shape".
8. Build phases from evidence, not from equal time intervals.

## Optional Remote Evidence

Remote evidence is off by default. Enable it only when the user asks for PR, issue, review, GitHub, GitLab, or recorded-rationale context.

- Use `--remote-context auto` for recognized GitHub/GitLab remotes.
- Treat API failures and missing artifacts as limitations, not as absence of history.
- Link strength matters: commit-to-PR API links are stronger than `#123` text references.
- Never infer private motivation, organization politics, blame, or performance from remote artifacts.

## Optional AST Diff

Use `--ast-diff` when the user asks for semantic or AST-level evidence.

- Current support is Python `.py`/`.pyi` via stdlib `ast`.
- Non-Python files, large blobs, parse errors, and merge commits are recorded as skipped.
- AST output helps choose diffs to read; it does not replace reading important patches.

## Optional Visual Timeline

After saving collector output, render an offline HTML evidence index when the user asks for a visual timeline:

```bash
python <skill-dir>/scripts/render_timeline_html.py archaeology.json --output timeline.html
```

Do not present the HTML as a full report. It is a browser-friendly index over collected evidence.

## Merge Commits

Do not automatically discard merge commits.

- If a merge has target-path changes relative to a parent, inspect it.
- If it only joins a topic branch, use it as weak chronology evidence.
- Use `git show -m` or parent-specific diffs for important merges.

## Shallow Or Incomplete History

If `repo.history_complete` is false:

- Do not claim "first", "original", or "introduced by" as certain.
- Say "earliest visible in this clone" when needed.
- Suggest deepening history only as an optional next step; do not fetch automatically.

## Large Repositories

Prefer two stages:

1. Collector pass with path-limited history and capped commit count.
2. Human/agent reading of top-ranked diffs.

Avoid whole-repo pickaxe searches unless the user explicitly requests them or the target cannot be mapped to paths.

## Phase Construction

A good phase has:

- A date or commit range.
- A theme such as "initial extraction", "API stabilization", "migration", "hardening", or "cleanup".
- At least one evidence commit.
- A consequence for today's code.

Avoid phases that are just "2024-Q1 had 12 commits".

## Current Shape

Inspect current files directly. The collector can identify history and blame, but it cannot summarize runtime boundaries, public APIs, or architectural responsibilities without code reading.
