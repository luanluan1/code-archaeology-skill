# Code Archaeology Skill Design

## Goal

Create a Codex skill that explains how a code area evolved using local git evidence. The report should help an engineer understand why the current module shape exists before changing it.

## Shape

The project is a skill plus a deterministic collector script:

- `SKILL.md` defines the investigation workflow.
- `scripts/collect_git_history.py` gathers auditable evidence.
- `scripts/render_timeline_html.py` renders saved evidence as an offline visual index.
- `references/` holds report, evidence, workflow, and scoring rules.

This is deliberately not a full CLI product. The script ranks and packages evidence; Codex performs the final interpretation after reading selected diffs.

## Collector Pipeline

1. Verify the target repository with `git rev-parse`.
2. Capture repo state: root, branch, head, shallow status, working tree status, git version.
3. Resolve target as file, directory, glob, module-like name, symbol, or ambiguous query.
4. Collect candidate commits with path-limited `git log`, `--follow` for files, and pickaxe fallback for symbols.
5. Enrich candidates with metadata, `name-status`, `numstat`, rename/copy signals, parent count, and blame survivorship.
6. Extract recorded context from commit text: issue/PR references and explicit rationale statements.
7. Optionally add Python AST symbol/import diff evidence with `--ast-diff`.
8. Optionally fetch GitHub/GitLab PR, issue, review, and recorded-rationale artifacts with explicit `--remote-context`.
9. Score commits from 0-100 using relevance, lifecycle events, behavior/structure signals, churn, message intent, current survival, time boundaries, and people signals.
10. Penalize generated/vendor/lock-only changes, formatting churn, incidental cross-cutting changes, and low-signal bot commits.
11. Emit JSON with commands Codex should run for manual review.

## Report Contract

Every final report should contain:

- scope and method
- engineer summary
- current shape
- evolution timeline
- turning points
- key people
- legacy layers and constraints
- maintenance advice
- evidence index
- unknowns

Every non-trivial claim must cite an evidence ID or be marked as inference/unknown.

## Validation

Automated tests cover:

- non-git directory failures
- basic file history collection
- importance ranking and review command generation
- rename lineage for moved files
- recorded issue references and explicit rationale extraction
- Python AST symbol diff enrichment
- standalone HTML timeline rendering and escaping

Manual smoke testing covers a real public repository: `pallets/click`, target `src/click/core.py`.

## Non-Goals

- No hidden author motivation, organization politics, blame, or performance judgment.
- No treating weak PR/issue references as causality.
- No remote platform fetching unless explicitly requested.
- No automatic architecture diagrams.
- No multi-language AST platform in MVP; AST diff is Python-only.
- No destructive git commands.

## Success Criteria

- The skill can be installed by copying `skill/code-archaeology` into the Codex skills directory.
- `quick_validate.py` accepts the skill metadata.
- The collector emits valid JSON for local git repositories.
- The report workflow prevents unsupported causal claims.
- A shallow clone is clearly marked as incomplete history.
