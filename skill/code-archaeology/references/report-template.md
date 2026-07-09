# Report Template

```markdown
# Code Archaeology: <target>

## 1. Scope And Method
- Repository: `<repo>`
- Target: `<file/directory/module/symbol>`
- Range: `<range>`
- Head: `<sha>`
- History completeness: `<complete/shallow/limited>`
- Method: collector JSON + inspected diffs `<count>`

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

## 7. Legacy Layers And Constraints
- <compatibility layer / old naming / migration trace> [E5]
- <risk that cannot be safely removed without checks> [I3]

## 8. Maintenance Advice
- Start reading from:
- Before modifying, check:
- High-risk areas:
- Tests or commands to run:

## 9. Evidence Index
- [E1] commit `<sha>` `<date>` "<subject>"; `<path>`; hunk `<@@ marker>`
- [E2] `HEAD:<path>:<line>`
- [I1] Inference from [E1] and [E2]: <inference>

## 10. Unknowns
- <question not answerable from local git history>
- <history limitation such as shallow clone, squash merge, missing PRs>
```

Keep the report readable. Do not include every commit; include the commits that explain the shape of the code.
