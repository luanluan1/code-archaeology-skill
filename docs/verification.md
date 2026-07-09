# 真实验证

🌐 **中文** · [English](./verification.en.md)

本页记录 `code-archaeology` 的真实 smoke test。README 只保留摘要，完整命令和结果放在这里。

## 公开仓库历史采集

仓库：`pallets/click`

目标：`src/click/core.py`

结果：

- 收集 commit：`80`
- 历史完整性：`true`
- warning：无
- top evidence 包含 bugfix、revert、refactor 信号

相关示例：

- [click-core-summary.json](../examples/click-core-summary.json)
- [sample-report.md](../examples/sample-report.md)

## 本机安装版 Skill 测试

直接调用安装到 `~/.codex/skills/code-archaeology` 的 skill，对本仓库自身做采集、AST 分析、远端探测和 HTML 渲染。

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

真实结果：

- 相关 commit：`3`
- Python AST 成功分析文件版本：`3`
- 语义信号：`function_body_changed`、`import_changed`、`semantic_change`、`signature_changed`、`symbol_added`
- 远端识别：GitHub
- PR artifact：`0`，因为本仓库这些提交没有关联 PR
- warning：无
- HTML 时间线：生成成功

## GitHub PR Artifact 联通测试

用真实公开仓库 `pallets/click` 验证 GitHub PR 证据抓取。

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

真实结果：

- 相关 commit：`12`
- Python AST 成功分析文件版本：`12`
- GitHub API 返回 PR artifact：`9`
- 示例 artifact：`GH-PR-3404`、`GH-PR-3578`、`GH-PR-3509`
- warning：无
- HTML 时间线：生成成功

该测试为了速度使用浅克隆，所以 `history_complete=false`。报告中不能据此声称“最早”或“首次”。
