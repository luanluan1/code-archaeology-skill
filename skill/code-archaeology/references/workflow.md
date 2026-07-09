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
3. Read high-priority `agent_review.read_commands`.
4. Read enough medium-priority commits to explain every major phase.
5. Inspect current files before writing "current shape".
6. Build phases from evidence, not from equal time intervals.

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
