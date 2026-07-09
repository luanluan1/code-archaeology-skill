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
  <img alt="Local first, remote opt-in" src="https://img.shields.io/badge/runtime-local_first_remote_opt--in-7c3aed?style=flat-square">
</p>

`code-archaeology` is a Codex skill for answering questions like:

> "Why did this module become this shape?"

It collects local git evidence first, asks Codex to inspect the important diffs, then produces a report with key commits, key people, turning points, legacy constraints, and unknowns.

No GitHub/GitLab API is required by default. No PRs, issues, author motives, or team stories are invented. If evidence cannot prove something, the report must say so.

When explicitly requested, the skill can add remote collaboration evidence, Python AST-level structure diffs, and an offline HTML timeline. These are evidence enrichments; Codex still needs to inspect important diffs before writing conclusions.

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

## Capability Boundaries

- Local-first evidence by default: `log`, `show`, `blame`, rename/copy lineage, scoring, and recommended diffs.
- Optional remote evidence: with `--remote-context auto`, fetch GitHub/GitLab PRs, issues, reviews, and recorded rationale.
- Optional AST diff: with `--ast-diff`, analyze Python `.py`/`.pyi` imports, functions, classes, signatures, and body changes.
- Optional visualization: render collector JSON into an offline HTML timeline for phases, commits, flags, people signals, and warnings.

It does not infer hidden motivation, organization politics, blame, or individual performance. Commit counts, review counts, and blame lines are maintenance signals only.

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
- recorded issue/PR references and explicit rationale extraction
- optional GitHub/GitLab PR, issue, and review evidence
- optional Python AST symbol diffs
- optional offline HTML timeline rendering
- review commands for the commits Codex should inspect

Example:

```bash
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo /path/to/repo \
  --since 2025-01-01 \
  --top-k 12 \
  src/click/core.py
```

Optional enrichments:

```bash
# Python AST symbol diff
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo /path/to/repo \
  --ast-diff \
  --output archaeology.json \
  src/auth.py

# Explicit GitHub/GitLab PR, issue, and review evidence
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo /path/to/repo \
  --remote-context auto \
  --output archaeology.json \
  src/auth

# Render an offline HTML timeline
python skill/code-archaeology/scripts/render_timeline_html.py \
  archaeology.json \
  --output timeline.html
```

Remote evidence is disabled by default. Private repository PRs, issues, and reviews may contain internal paths, usernames, or business context; inspect JSON/HTML before sharing.

## Real Smoke Test

This repository was smoke-tested against the real public repository `pallets/click`:

- target: `src/click/core.py`
- collected commits: `80`
- history completeness: `true`
- warnings: none
- top evidence included bugfix, revert, and refactor signals
- this repository has also been regression-tested with `--ast-diff` and the HTML renderer

See [examples/click-core-summary.json](examples/click-core-summary.json) and [examples/sample-report.md](examples/sample-report.md).

This feature expansion was also tested with two local installed-skill smoke tests.

The first test called the skill installed under `~/.codex/skills/code-archaeology` and ran collection, AST analysis, remote detection, and HTML rendering against this repository:

```bash
python ~/.codex/skills/code-archaeology/scripts/collect_git_history.py \
  --repo . \
  --max-commits 30 \
  --top-k 10 \
  --ast-diff \
  --remote-context auto \
  --remote-limit 5 \
  --output .tmp-real/installed-skill-evidence.json \
  skill/code-archaeology/scripts/collect_git_history.py

python ~/.codex/skills/code-archaeology/scripts/render_timeline_html.py \
  .tmp-real/installed-skill-evidence.json \
  --output .tmp-real/installed-skill-timeline.html
```

Real result: `3` related commits collected, `3` Python AST file versions analyzed successfully, semantic flags included `function_body_changed`, `import_changed`, `semantic_change`, `signature_changed`, and `symbol_added`; the remote was recognized as GitHub, these commits had no linked PR artifacts, warnings were empty, and the HTML timeline was generated successfully.

The second test used the real public repository `pallets/click` to verify GitHub PR evidence fetching:

```bash
git clone --depth=200 https://github.com/pallets/click.git .tmp-real/pallets-click

python ~/.codex/skills/code-archaeology/scripts/collect_git_history.py \
  --repo .tmp-real/pallets-click \
  --max-commits 12 \
  --top-k 6 \
  --ast-diff \
  --remote-context auto \
  --remote-limit 6 \
  --output .tmp-real/click-installed-evidence.json \
  src/click/core.py

python ~/.codex/skills/code-archaeology/scripts/render_timeline_html.py \
  .tmp-real/click-installed-evidence.json \
  --output .tmp-real/click-installed-timeline.html
```

Real result: `12` related commits collected, `12` Python AST file versions analyzed successfully, the GitHub API returned `9` PR artifacts, including `GH-PR-3404`, `GH-PR-3578`, and `GH-PR-3509`; remote warnings were empty, and the HTML timeline was generated successfully. This test used a shallow clone for speed, so `history_complete=false` and reports must not claim "earliest" or "first-ever" from it.

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
│       └── scripts/
│           ├── collect_git_history.py
│           └── render_timeline_html.py
├── tests/
│   ├── test_collect_git_history.py
│   └── test_render_timeline_html.py
├── docs/design.md
└── examples/
```

The skill folder stays lean. Human-facing project docs live at the repository root.

## Development

Run tests:

```bash
python tests/test_collect_git_history.py
python tests/test_render_timeline_html.py
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
