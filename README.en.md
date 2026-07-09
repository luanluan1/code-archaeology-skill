<h1 align="center">Code Archaeology Skill</h1>

<p align="center">
  🌐 <a href="./README.md">中文</a> · <strong>English</strong>
</p>

<p align="center">
  Turn git history into an evidence-backed engineering timeline.
</p>

<p align="center">
  <a href="skill/code-archaeology/SKILL.md"><img alt="Codex Skill" src="https://img.shields.io/badge/Codex-Skill-111827?style=flat-square"></a>
  <a href="tests/test_collect_git_history.py"><img alt="Tests" src="https://img.shields.io/badge/tests-unittest-2563eb?style=flat-square"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-16a34a?style=flat-square"></a>
  <img alt="No network required at runtime" src="https://img.shields.io/badge/runtime-local_git_only-7c3aed?style=flat-square">
</p>

`code-archaeology` is a Codex skill for answering questions like:

> "Why did this module become this shape?"

It collects local git evidence first, asks Codex to inspect the important diffs, then produces a report with key commits, key people, turning points, legacy constraints, and unknowns.

No GitHub API is required at runtime. No PR or issue history is invented. If the local git history cannot prove something, the report must say so.

The current version focuses on local git history; PRs, issues, and remote platform data can be added later.

## What It Produces

```markdown
# Code Archaeology: src/auth

## Engineer Summary
- Current responsibility: ...
- Main evolution: ...
- Biggest maintenance constraint: ...

## Evolution Timeline
| Phase | Date/Commits | Theme | What Changed | Why It Matters | Evidence |

## Turning Points
## Key People
## Legacy Layers And Constraints
## Evidence Index
## Unknowns
```

The skill is designed for engineers taking over a code area, preparing a refactor, reviewing a risky module, or trying to understand why a file carries so much historical weight.

## Install

`code-archaeology` follows the [Agent Skills](https://agentskills.io/) structure and can run in skills-compatible AI agent runtimes.

### Method 1: One-Line Agent Install (Recommended)

Open the agent runtime you use, such as Codex or another Agent Skills compatible tool, and tell it:

```text
Install this skill: https://github.com/luanluan1/code-archaeology-skill
```

If your runtime supports the universal Skills CLI, you can also run:

```bash
npx skills add luanluan1/code-archaeology-skill
```

When needed, add a runtime flag as prompted by the CLI, such as `-a codex`, `-a claude-code`, or `-a cursor`.

Use `-g` when you want a user-level global install.

### Method 2: Manual Install

<details>
<summary>Expand for Codex manual install steps</summary>

Clone the repository:

```bash
git clone https://github.com/luanluan1/code-archaeology-skill.git
cd code-archaeology-skill
```

Copy the skill into the Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skill/code-archaeology "${CODEX_HOME:-$HOME/.codex}/skills/"
```

PowerShell:

```powershell
$skills = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $HOME ".codex\skills" }
New-Item -ItemType Directory -Force $skills | Out-Null
Copy-Item -Recurse -Force ".\skill\code-archaeology" $skills
```

Restart Codex so it reloads skill metadata.

</details>

### Method 3: Use As Reference Material

If your runtime does not support automatic Agent Skills loading yet, paste the contents of [SKILL.md](skill/code-archaeology/SKILL.md) into the conversation. It is a Markdown workflow document with YAML frontmatter.

## Use It

Ask Codex naturally:

```text
Use code-archaeology to explain why src/auth became this shape.
```

Or point it at a range:

```text
用 code-archaeology 分析 src/payments 从 v1.8.0 到现在的关键转折点和关键人。
```

Under the hood, the skill runs:

```bash
python skill/code-archaeology/scripts/collect_git_history.py --repo . --max-commits 300 --top-k 20 src/auth
```

Then Codex reads the recommended `git show` commands before writing the report.

## Why This Is Different

Most "git history summaries" become commit-message fan fiction.

`code-archaeology` prevents that with a hard split:

| Layer | Responsibility |
|---|---|
| Collector script | Deterministic evidence: log, blame, rename lineage, scoring, people stats |
| Skill workflow | Investigation discipline: what to inspect and when to stop |
| Codex report | Human-readable timeline with evidence IDs and uncertainty |

Every non-trivial claim in the final report must cite evidence or be marked as inference/unknown.

## Built-In Evidence Collection

The collector handles:

- file, directory, glob, module-name, and symbol targets
- `git log --follow` for file history
- rename, copy, move, add, delete, and revert signals
- directory history via `--name-status -M -C`
- current survivorship via `git blame -w -M -C`
- merge commit detection
- shallow clone warnings
- generated/vendor/lockfile and formatting noise penalties
- author activity, weighted importance, and current blame lines
- review commands for the commits Codex should inspect

Example:

```bash
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo /path/to/repo \
  --since 2025-01-01 \
  --top-k 12 \
  src/click/core.py
```

## Real Smoke Test

This repository was smoke-tested against the real public repository `pallets/click`:

- target: `src/click/core.py`
- collected commits: `80`
- history completeness: `true`
- warnings: none
- top evidence included bugfix, revert, and refactor signals

See [examples/click-core-summary.json](examples/click-core-summary.json) and [examples/sample-report.md](examples/sample-report.md).

## Repository Layout

```text
.
├── skill/
│   └── code-archaeology/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       ├── references/
│       │   ├── evidence-rules.md
│       │   ├── report-template.md
│       │   ├── scoring.md
│       │   └── workflow.md
│       └── scripts/collect_git_history.py
├── tests/test_collect_git_history.py
├── docs/design.md
└── examples/
```

The skill folder stays lean. Human-facing project docs live at the repository root.

## Development

Run tests:

```bash
python tests/test_collect_git_history.py
```

Validate the skill:

```bash
PYTHONUTF8=1 python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/code-archaeology
```

PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
python "$HOME\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "skill\code-archaeology"
```

## License

MIT. See [LICENSE](LICENSE).
