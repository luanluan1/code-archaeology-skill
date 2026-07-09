# Scoring Reference

The collector's importance score ranks commits for review. It is not a truth score.

## Positive Factors

| Factor | Max | Meaning |
|---|---:|---|
| `target_relevance` | 25 | How directly the commit touched the requested target. |
| `lifecycle_event` | 20 | Add, delete, rename, copy, move, or revert signals. |
| `behavior_or_structure` | 15 | Refactor, migration, security, perf, or bugfix intent signals. |
| `diff_churn` | 10 | Normalized target additions/deletions. |
| `message_intent` | 10 | Intent keywords in subject/body. |
| `current_survival` | 10 | Current blame lines still point at the commit. |
| `time_boundary` | 5 | Near the start or end of the collected window. |
| `people_signal` | 5 | Author repeatedly touched the target. |

## Penalties

| Penalty | Meaning |
|---|---|
| `generated_or_vendor` | Generated, vendored, or lock-only target changes. |
| `formatting_noise` | Format/lint-only changes are often not design turns. |
| `broad_crosscut` | Huge change where the target may be incidental. |
| `bot_noise` | Bot commit without migration/security importance. |

## How To Use Scores

- Read high-score commits first.
- Promote lower-score commits if they are lifecycle events.
- Demote high-score commits if the diff is mechanical.
- Use `importance.factors` in the evidence index when explaining why a commit was considered key.
- Use optional `semantic_diffs` and `external_evidence` as extra evidence, not as automatic score truth.
- Never say a score proves causality.
