# Contributing

Thanks for improving `code-archaeology`.

Good contributions usually do one of three things:

- improve evidence collection without making unsupported claims
- tighten the report or evidence contract
- add tests for real git history edge cases

## Local Checks

```bash
python tests/test_collect_git_history.py
PYTHONUTF8=1 python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/code-archaeology
```

On Windows PowerShell:

```powershell
python tests\test_collect_git_history.py
$env:PYTHONUTF8 = "1"
python "$HOME\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "skill\code-archaeology"
```

## Evidence Discipline

Do not add behavior that invents author intent, PR context, issue context, or ownership from local git data alone. If a conclusion cannot be proven from evidence, the report should mark it as inference or unknown.
