<h1 align="center">Code Archaeology Skill</h1>

<p align="center">
  🌐 <strong>中文</strong> · <a href="./README.en.md">English</a>
</p>

<p align="center">
  把 git 历史变成有证据链的工程演化时间线。
</p>

<p align="center">
  <a href="skill/code-archaeology/SKILL.md"><img alt="Codex Skill" src="https://img.shields.io/badge/Codex-Skill-111827?style=flat-square"></a>
  <a href="tests/test_collect_git_history.py"><img alt="Tests" src="https://img.shields.io/badge/tests-unittest-2563eb?style=flat-square"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-16a34a?style=flat-square"></a>
  <img alt="Local first, remote opt-in" src="https://img.shields.io/badge/runtime-local_first_remote_opt--in-7c3aed?style=flat-square">
</p>

`code-archaeology` 是一个 Codex skill，用来回答这类问题：

> “这个模块为什么变成今天这样？”

它会先从本地 git 历史里收集证据，再让 Codex 阅读关键 diff，最后产出包含关键 commit、关键人、历史转折点、遗留约束和未知项的工程报告。

默认运行不依赖 GitHub/GitLab API，也不会编造 PR、issue、作者动机或组织故事。如果证据证明不了，报告必须明确写成未知。

需要时可以显式开启远端协作证据、Python AST 级结构差异，以及离线 HTML 时间线。它们都是证据增强，不会替代 Codex 阅读关键 diff 后写出的判断。

## 能输出什么

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

它适合接手旧模块、准备重构、评估高风险文件，或者解释“为什么这里这么复杂”。

## 能力边界

- 默认只读本地 git：`log`、`show`、`blame`、rename/copy lineage、评分和关键 diff 推荐。
- 可选远端证据：用户明确要求后，用 `--remote-context auto` 抓取 GitHub/GitLab PR、issue、review 和记录中的理由。
- 可选 AST diff：用 `--ast-diff` 分析 Python `.py`/`.pyi` 的 import、函数、类、签名和 body 变化。
- 可选可视化：把 collector JSON 渲染成离线 HTML 时间线，方便浏览阶段、commit、flags、人员信号和警告。

不会做的事也很明确：不推断隐藏动机、组织政治、责任归因或个人绩效；commit 数、review 数和 blame 行数只能作为维护信号。

## 安装

`code-archaeology` 遵循 [Agent Skills](https://agentskills.io/) 结构，可在 skills-compatible 的 AI agent runtime 中使用。

### 方式一：一句话安装（推荐，跨 runtime）

打开你正在使用的 agent runtime，例如 Codex 或其他支持 Agent Skills 的工具，告诉它：

```text
帮我安装这个 skill: https://github.com/luanluan1/code-archaeology-skill
```

如果你的 runtime 支持通用 Skills CLI，也可以直接运行：

```bash
npx skills add luanluan1/code-archaeology-skill
```

需要指定 runtime 时，可按 CLI 提示追加参数，例如 `-a codex`、`-a claude-code`、`-a cursor`。

想安装为用户级全局 skill 时，可以加 `-g`。

### 方式二：手动安装

<details>
<summary>展开查看 Codex 手动安装步骤</summary>

克隆仓库：

```bash
git clone https://github.com/luanluan1/code-archaeology-skill.git
cd code-archaeology-skill
```

复制 skill 到 Codex skills 目录：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skill/code-archaeology "${CODEX_HOME:-$HOME/.codex}/skills/"
```

PowerShell：

```powershell
$skills = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $HOME ".codex\skills" }
New-Item -ItemType Directory -Force $skills | Out-Null
Copy-Item -Recurse -Force ".\skill\code-archaeology" $skills
```

重启 Codex，让它重新加载 skill 元数据。

</details>

### 方式三：作为参考资料使用

如果你的 runtime 暂不支持自动加载 Agent Skills，也可以直接把 [SKILL.md](skill/code-archaeology/SKILL.md) 的内容粘贴进对话。它本质上是一份带 YAML frontmatter 的 Markdown 工作流文档。

## 如何使用

自然地问 Codex：

```text
用 code-archaeology 分析 src/auth 为什么变成今天这样。
```

也可以指定版本范围：

```text
用 code-archaeology 分析 src/payments 从 v1.8.0 到现在的关键转折点和关键人。
```

底层会先运行类似命令：

```bash
python skill/code-archaeology/scripts/collect_git_history.py --repo . --max-commits 300 --top-k 20 src/auth
```

然后 Codex 根据脚本推荐的 `git show` 命令阅读关键 diff，再写报告。

## 为什么不一样

很多“git 历史总结”最后都会变成 commit message 故事会。

`code-archaeology` 用三层结构避免这个问题：

| 层 | 责任 |
|---|---|
| Collector script | 确定性证据：log、blame、rename lineage、评分、人员统计 |
| Skill workflow | 调查纪律：什么时候采集、什么时候读 diff、什么时候标未知 |
| Codex report | 带证据编号和不确定性标注的人类可读报告 |

最终报告里的每个非平凡结论都必须引用证据，或者明确标为推断/未知。

## 内置证据采集

collector 支持：

- 文件、目录、glob、模块名、symbol 目标
- 文件历史的 `git log --follow`
- rename、copy、move、add、delete、revert 信号
- 目录历史的 `--name-status -M -C`
- `git blame -w -M -C` 当前存活度
- merge commit 检测
- shallow clone 警告
- generated/vendor/lockfile 和格式化噪音降权
- 作者活跃度、加权重要性、当前 blame 行数
- 记录中的 issue/PR 引用和显式理由摘取
- 可选 GitHub/GitLab PR、issue、review 证据补充
- 可选 Python AST 符号级 diff
- 可选离线 HTML 时间线渲染
- 给 Codex 阅读的 `git show` 推荐命令

示例：

```bash
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo /path/to/repo \
  --since 2025-01-01 \
  --top-k 12 \
  src/click/core.py
```

可选增强：

```bash
# Python AST 符号 diff
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo /path/to/repo \
  --ast-diff \
  --output archaeology.json \
  src/auth.py

# 显式开启 GitHub/GitLab PR、issue、review 证据
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo /path/to/repo \
  --remote-context auto \
  --output archaeology.json \
  src/auth

# 渲染离线 HTML 时间线
python skill/code-archaeology/scripts/render_timeline_html.py \
  archaeology.json \
  --output timeline.html
```

远端证据默认关闭。私有仓库的 PR/issue/review 可能包含内部路径、用户名或业务信息，分享 JSON/HTML 前请先检查。

## 真实 Smoke Test

这个仓库已经用真实公开项目 `pallets/click` 跑过 smoke test：

- 目标：`src/click/core.py`
- 收集 commit：`80`
- 历史完整性：`true`
- 警告：无
- top evidence 包含 bugfix、revert、refactor 信号
- 本项目自身已用 `--ast-diff` 和 HTML renderer 做过真实回归

见 [examples/click-core-summary.json](examples/click-core-summary.json) 和 [examples/sample-report.md](examples/sample-report.md)。

后续又用本项目自身跑目录级真实测试，发现并修复了 Windows UTF-8 解码问题，回归测试已加入 `tests/test_collect_git_history.py`。

本次功能扩展也用本仓库自身做了真实联通测试：

```bash
python skill/code-archaeology/scripts/collect_git_history.py \
  --repo . \
  --max-commits 25 \
  --top-k 8 \
  --ast-diff \
  --remote-context auto \
  --remote-limit 3 \
  --output .tmp-real/self-evidence.json \
  skill/code-archaeology/scripts/collect_git_history.py

python skill/code-archaeology/scripts/render_timeline_html.py \
  .tmp-real/self-evidence.json \
  --output .tmp-real/self-timeline.html
```

真实结果：采集到 `2` 个相关 commit，Python AST 分析 `2` 个文件版本成功，识别出 `import_changed`、`symbol_added`、`signature_changed`、`function_body_changed` 等信号；远端识别为 GitHub，本仓库这些提交没有关联 PR artifact，warning 为空；HTML 时间线成功生成。

## 仓库结构

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

skill 包保持精简；面向人的说明文档放在仓库根目录。

## 开发验证

运行测试：

```bash
python tests/test_collect_git_history.py
python tests/test_render_timeline_html.py
```

校验 skill：

```bash
PYTHONUTF8=1 python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/code-archaeology
```

PowerShell：

```powershell
$env:PYTHONUTF8 = "1"
python "$HOME\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "skill\code-archaeology"
```

## License

MIT. See [LICENSE](LICENSE).
