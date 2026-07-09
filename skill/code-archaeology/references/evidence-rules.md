# Evidence Rules

## Evidence IDs

Use two ID families:

- `[E<n>]` for observed evidence from git, current files, or commands.
- `[I<n>]` for inference derived from evidence.

Examples:

- `[E1] commit abc1234 2025-03-17 "Extract auth middleware"; src/auth/middleware.ts; hunk @@ -42,8 +58,21`
- `[E2] HEAD:src/auth/index.ts:37`
- `[E3] command: git log --follow -- src/auth/session.ts`
- `[I1] Inferred from E4 and E5: the module boundary shifted from request handling to reusable auth policy. No direct design note was found.`

## Claim Rules

- Every non-trivial factual claim needs an evidence ID.
- Inferences must say what evidence they came from.
- Unknowns are acceptable. Do not fill gaps with plausible stories.
- Commit messages are weak evidence for motivation and strong evidence only for what the author wrote.
- Diffs are stronger evidence for behavior, structure, dependencies, and file movement.
- Blame is evidence of current survivorship, not authorship of the whole design.
- Author count is evidence of activity, not ownership by itself.

## Prohibited Claims Without Direct Evidence

- "The team decided..."
- "The author intended..."
- "This was caused by customer requirements..."
- "PR review forced..."
- "This was the first/original implementation..." when history is shallow, squashed, or incomplete.
- "This person owns the module..." from commit count alone.

## Historical Code References

For historical code, cite:

```text
[E7] commit <sha> <date> "<subject>"; <path>; hunk <@@ marker>
```

For current code, cite:

```text
[E8] HEAD:<path>:<line>
```

If line numbers are unstable or not inspected, cite file-level evidence only:

```text
[E9] HEAD:<path>; current file structure inspected
```

## Confidence Language

Use:

- "The history shows..." for direct evidence.
- "The diff indicates..." for structural or behavior changes visible in code.
- "Likely..." only when supported by multiple evidence points.
- "Unknown from local git history..." when evidence is absent.

Avoid:

- "Obviously"
- "Clearly intended"
- "Must have"
- "The reason was" unless a commit, doc, or issue states it directly.
