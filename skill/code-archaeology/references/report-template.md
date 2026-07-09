# Report Template

```markdown
# Code Archaeology: <target>

## 1. Scope And Method
- Repository: `<repo>`
- Target: `<file/directory/module/symbol>`
- Range: `<range>`
- Head: `<sha>`
- History completeness: `<complete/shallow/limited>`
- Method: collector JSON + inspected diffs `<count>` + optional AST/remote evidence `<if used>`

## 2. Engineer Summary
- Current responsibility: <what this code owns now> [E1]
- Main evolution: <one sentence> [E2][I1]
- Biggest maintenance constraint: <constraint> [E3]
- Confidence: <high/medium/low and why>

## 3. Current Shape
- Entry points:
- Core abstractions:
- Important dependencies:
- Boundaries with other modules:

## 4. Evolution Timeline
| Phase | Date/Commits | Theme | What Changed | Why It Matters | Evidence |
|---|---|---|---|---|---|
| Phase 1 | <range> | <theme> | <facts> | <impact> | [E1][E2] |

## 5. Turning Points
- <Turning point>: changed from <old shape> to <new shape>; impact: <impact>. Evidence: [E4][I2]

## 6. Key People
| Person | Evidence Role | First/Last Touch | Why They Matter | Caveat |
|---|---|---|---|---|
| <name> | <creator/refactorer/maintainer/fixer> | <dates> | <evidence-backed reason> | <not owner unless proven> |

## 7. Recorded Rationale And Remote Evidence
- <PR/issue/review/design artifact says X> [E6]
- Caveat: <linked artifact / text reference / API limitation; no hidden motivation or performance judgment>

## 8. Semantic Diff Notes
- <AST symbol/import change that helped interpret a turning point> [E7]
- Caveat: <Python-only / parse skipped / AST evidence does not replace patch review>

## 9. Legacy Layers And Constraints
- <compatibility layer / old naming / migration trace> [E5]
- <risk that cannot be safely removed without checks> [I3]

## 10. Maintenance Advice
- Start reading from:
- Before modifying, check:
- High-risk areas:
- Tests or commands to run:

## 11. Evidence Index
- [E1] commit `<sha>` `<date>` "<subject>"; `<path>`; hunk `<@@ marker>`
- [E2] `HEAD:<path>:<line>`
- [I1] Inference from [E1] and [E2]: <inference>

## 12. Unknowns
- <question not answerable from local git history>
- <history limitation such as shallow clone, squash merge, missing PRs>
```

Keep the report readable. Do not include every commit; include the commits that explain the shape of the code.
