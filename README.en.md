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

## Feature Description

`code-archaeology` turns a fuzzy code-history question into auditable evidence collection, important diff inspection, and an engineering report.

| User Goal | Input Scope | What The Skill Does | Main Output |
|---|---|---|---|
| Explain why a module became its current shape | File, directory, glob, module name, or symbol | Resolves the target, collects relevant commits, and detects add/delete/rename/copy/move/revert/merge signals | Evidence-cited evolution report |
| Find key commits and historical turning points | Full history, date range, or version range | Scores commits using churn, blame survivorship, lifecycle events, and intent keywords | Ranked commits, review priority, recommended `git show` commands |
| Inspect GitHub/GitLab PR or issue context | Explicit `--remote-context auto` opt-in | Fetches linked PRs, issues, reviews, and recorded rationale with link method and confidence | `external_evidence` block |
| Inspect AST-level structural change | Python `.py` / `.pyi` files with explicit `--ast-diff` | Compares imports, functions, classes, signatures, decorators, and body changes | Structured `semantic_diffs` |
| Browse a visual timeline | Collector JSON | Renders an offline HTML page with no server or build step | `timeline.html` evidence index |

Typical workflow:

1. The user gives a target such as `src/auth`, `src/click/core.py`, or `login`.
2. The collector writes a JSON evidence package with repository state, target resolution, commit ranking, path lineage, people maintenance signals, and warnings.
3. Codex reads the important diffs recommended by the JSON instead of summarizing commit messages alone.
4. When requested, the run adds remote collaboration evidence, Python AST diffs, or an offline HTML timeline.
5. The final report only states conclusions supported by evidence; unsupported questions are marked unknown.

## What It Produces

- Engineer summary: current responsibility, main evolution, and biggest maintenance constraint.
- Evolution timeline: phases with key commits, themes, changes, and impact.
- Turning points: creation, migration, refactor, revert, security, and performance moments.
- Key people / maintenance signals: authors, reviewers, current blame survivorship, and caveats.
- Evidence index and unknowns: every non-trivial conclusion is cited; missing evidence stays unknown.

See a complete report example: [examples/sample-report.md](examples/sample-report.md).

The skill is designed for engineers taking over a code area, preparing a refactor, reviewing a risky module, or trying to understand why a file carries so much historical weight.

## Safety Boundaries

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

If your runtime does not support automatic Agent Skills loading yet, read [SKILL.md](skill/code-archaeology/SKILL.md) as a reference workflow.

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

## Collector Capabilities

The collector is a deterministic evidence script that turns git history into auditable JSON for Codex:

- Target resolution: file, directory, glob, module name, or symbol.
- History signals: `git log --follow`, rename/copy/move/add/delete/revert/merge, and shallow clone warnings.
- Maintenance signals: current blame survivorship, author activity, weighted importance, and recommended diff commands.
- Optional enrichments: GitHub/GitLab PRs, issues, reviews, Python AST symbol diffs, and offline HTML timelines.

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

## Verification

This repository has been smoke-tested against local and public repositories:

- `pallets/click` `src/click/core.py`: collected `80` real commits and produced the sample report.
- Installed local skill: ran collector, Python AST diff, and HTML renderer against this repository.
- GitHub remote connection: fetched `9` real PR artifacts from `pallets/click` with no warnings.

Details: [docs/verification.en.md](docs/verification.en.md). Examples: [examples/click-core-summary.json](examples/click-core-summary.json) and [examples/sample-report.md](examples/sample-report.md).

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
├── docs/
│   ├── design.md
│   ├── verification.md
│   └── verification.en.md
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
