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

## 功能描述

`code-archaeology` 把一次模糊的代码历史问题，拆成可审计的证据采集、关键 diff 阅读和工程报告生成。

| 用户想做 | 输入范围 | Skill 会做什么 | 主要输出 |
|---|---|---|---|
| 解释一个模块为什么变成今天这样 | 文件、目录、glob、模块名、symbol | 解析目标、收集相关 commit、识别 add/delete/rename/copy/move/revert/merge 等历史信号 | 带证据编号的模块演化报告 |
| 找关键 commit 和历史转折点 | 全历史、日期范围、版本范围 | 对 commit 做重要性评分，结合 churn、blame 存活度、生命周期事件和意图关键词排序 | 关键 commit 列表、阅读优先级、`git show` 推荐命令 |
| 看 GitHub/GitLab PR 或 issue 背景 | 显式开启 `--remote-context auto` | 抓取关联 PR、issue、review、记录中的理由，并标注关联方式和置信度 | `external_evidence` 证据块 |
| 看 AST 级结构变化 | Python `.py` / `.pyi` 文件，显式开启 `--ast-diff` | 比较 import、函数、类、签名、decorator、body 变化 | `semantic_diffs` 结构化结果 |
| 浏览可视化时间线 | collector 生成的 JSON | 生成一个离线 HTML 页面，不依赖服务端或构建工具 | `timeline.html` 证据索引 |

典型工作流：

1. 用户给出目标，例如 `src/auth`、`src/click/core.py` 或 `login`。
2. collector 先生成 JSON 证据包，包括仓库状态、目标解析、commit 排名、路径演化、人员维护信号和警告。
3. Codex 按 JSON 推荐的命令阅读关键 diff，而不是只复述 commit message。
4. 如果用户要求，额外补充远端协作证据、Python AST diff 或离线 HTML 时间线。
5. 最终报告只写证据能支持的结论；证据不足的地方明确写成未知。

## 能输出什么

- 工程摘要：当前职责、主要演化路径、最大维护约束。
- 演化时间线：按阶段组织关键 commit、主题、变化和影响。
- 历史转折点：创建、迁移、重构、回滚、安全/性能修复等关键变化。
- 关键人/维护信号：作者、评审、当前 blame 存活度和 caveat。
- 证据索引与未知项：每个非平凡结论都引用证据，不足处明确标未知。

查看完整报告样例：[examples/sample-report.md](examples/sample-report.md)。

它适合接手旧模块、准备重构、评估高风险文件，或者解释“为什么这里这么复杂”。

## 安全边界

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

如果你的 runtime 暂不支持自动加载 Agent Skills，也可以直接阅读 [SKILL.md](skill/code-archaeology/SKILL.md) 作为参考工作流。

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

## Collector 能力

collector 是一个确定性证据采集脚本，负责把 git 历史整理成 Codex 可审计的 JSON：

- 目标解析：文件、目录、glob、模块名、symbol。
- 历史信号：`git log --follow`、rename/copy/move/add/delete/revert/merge、shallow clone 警告。
- 维护信号：当前 blame 存活度、作者活跃度、加权重要性、关键 diff 阅读命令。
- 可选增强：GitHub/GitLab PR、issue、review，Python AST 符号 diff，离线 HTML 时间线。

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

## 真实验证

这个仓库已经做过本地和公开仓库 smoke test：

- `pallets/click` 的 `src/click/core.py`：采集 `80` 个真实 commit，生成样例报告。
- 本机安装版 skill：对本仓库自身跑通 collector、Python AST diff 和 HTML renderer。
- GitHub 远端联通：对 `pallets/click` 抓到 `9` 个真实 PR artifact，且 warning 为空。

详情见 [docs/verification.md](docs/verification.md)，示例见 [examples/click-core-summary.json](examples/click-core-summary.json) 和 [examples/sample-report.md](examples/sample-report.md)。

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
├── docs/
│   ├── design.md
│   ├── verification.md
│   └── verification.en.md
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
