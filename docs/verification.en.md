# Verification

🌐 [中文](./verification.md) · **English**

This page records real smoke tests for `code-archaeology`. The README keeps only the summary; full commands and results live here.

## Public Repository History Collection

Repository: `pallets/click`

Target: `src/click/core.py`

Result:

- collected commits: `80`
- history completeness: `true`
- warnings: none
- top evidence included bugfix, revert, and refactor signals

Related examples:

- [click-core-summary.json](../examples/click-core-summary.json)
- [sample-report.md](../examples/sample-report.md)

## Installed Local Skill Test

This test called the skill installed under `~/.codex/skills/code-archaeology` and ran collection, AST analysis, remote detection, and HTML rendering against this repository.

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

Real result:

- related commits: `3`
- Python AST file versions analyzed successfully: `3`
- semantic flags: `function_body_changed`, `import_changed`, `semantic_change`, `signature_changed`, `symbol_added`
- remote detected: GitHub
- PR artifacts: `0`, because these repository commits had no linked PR
- warnings: none
- HTML timeline: generated successfully

## GitHub PR Artifact Connection Test

This test used the real public repository `pallets/click` to verify GitHub PR evidence fetching.

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

Real result:

- related commits: `12`
- Python AST file versions analyzed successfully: `12`
- GitHub API PR artifacts returned: `9`
- sample artifacts: `GH-PR-3404`, `GH-PR-3578`, `GH-PR-3509`
- warnings: none
- HTML timeline: generated successfully

This test used a shallow clone for speed, so `history_complete=false`. Reports must not claim "earliest" or "first-ever" from it.
