import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "code-archaeology" / "scripts" / "collect_git_history.py"


def run(command, cwd, check=True):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(command)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


class CollectGitHistoryTests(unittest.TestCase):
    def test_reports_non_git_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(
                [sys.executable, str(SCRIPT), "--repo", tmp, "src/auth.py"],
                cwd=tmp,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a git work tree", result.stderr.lower())

    def test_collects_file_history_with_importance_and_agent_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run(["git", "init"], cwd=repo)
            run(["git", "config", "user.email", "tester@example.com"], cwd=repo)
            run(["git", "config", "user.name", "Test Author"], cwd=repo)

            src = repo / "src"
            src.mkdir()
            auth = src / "auth.py"
            auth.write_text("def login(user):\n    return user is not None\n", encoding="utf-8")
            run(["git", "add", "src/auth.py"], cwd=repo)
            run(["git", "commit", "-m", "Add auth module"], cwd=repo)

            auth.write_text(
                "def login(user):\n    if user is None:\n        return False\n    return bool(user.get('active'))\n",
                encoding="utf-8",
            )
            run(["git", "add", "src/auth.py"], cwd=repo)
            run(["git", "commit", "-m", "Harden auth login behavior"], cwd=repo)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(repo),
                    "--max-commits",
                    "20",
                    "--top-k",
                    "5",
                    "src/auth.py",
                ],
                cwd=repo,
            )
            payload = json.loads(result.stdout)

        self.assertEqual(payload["schema_version"], "0.2")
        self.assertTrue(payload["repo"]["history_complete"])
        self.assertEqual(payload["query"]["target_type"], "file")
        self.assertIn("src/auth.py", payload["query"]["normalized_paths"])
        self.assertGreaterEqual(len(payload["commits"]), 2)
        self.assertTrue(any("birth" in commit["flags"] for commit in payload["commits"]))
        self.assertTrue(any(commit["agent_review"]["required"] for commit in payload["commits"]))
        self.assertGreaterEqual(payload["commits"][0]["importance"]["score"], payload["commits"][-1]["importance"]["score"])

    def test_tracks_file_rename_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run(["git", "init"], cwd=repo)
            run(["git", "config", "user.email", "tester@example.com"], cwd=repo)
            run(["git", "config", "user.name", "Test Author"], cwd=repo)

            src = repo / "src"
            src.mkdir()
            old_path = src / "legacy_auth.py"
            new_path = src / "auth.py"
            old_path.write_text("def login(user):\n    return bool(user)\n", encoding="utf-8")
            run(["git", "add", "src/legacy_auth.py"], cwd=repo)
            run(["git", "commit", "-m", "Add legacy auth"], cwd=repo)
            run(["git", "mv", "src/legacy_auth.py", "src/auth.py"], cwd=repo)
            run(["git", "commit", "-m", "Rename legacy auth module"], cwd=repo)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(repo),
                    "--max-commits",
                    "20",
                    "src/auth.py",
                ],
                cwd=repo,
            )
            payload = json.loads(result.stdout)

        self.assertTrue(
            any(
                item["change_type"] == "rename"
                and item["previous_path"] == "src/legacy_auth.py"
                and item["current_path"] == "src/auth.py"
                for item in payload["path_lineage"]
            )
        )

    def test_collects_directory_with_utf8_content_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run(["git", "init"], cwd=repo)
            run(["git", "config", "user.email", "tester@example.com"], cwd=repo)
            run(["git", "config", "user.name", "Test Author"], cwd=repo)

            docs = repo / "docs"
            docs.mkdir()
            (docs / "notes.md").write_text("# 代码考古\n\n模块演化与关键提交。\n", encoding="utf-8")
            run(["git", "add", "docs/notes.md"], cwd=repo)
            run(["git", "commit", "-m", "Add Chinese archaeology notes"], cwd=repo)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(repo),
                    "--max-commits",
                    "20",
                    "docs",
                ],
                cwd=repo,
            )
            payload = json.loads(result.stdout)

        self.assertEqual(payload["query"]["target_type"], "directory")
        self.assertEqual(len(payload["commits"]), 1)
        self.assertEqual(payload["people"][0]["current_blame_lines"], 3)

    def test_records_issue_references_and_explicit_rationale(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run(["git", "init"], cwd=repo)
            run(["git", "config", "user.email", "tester@example.com"], cwd=repo)
            run(["git", "config", "user.name", "Test Author"], cwd=repo)

            src = repo / "src"
            src.mkdir()
            auth = src / "auth.py"
            auth.write_text("def login(user):\n    return bool(user)\n", encoding="utf-8")
            run(["git", "add", "src/auth.py"], cwd=repo)
            run(
                [
                    "git",
                    "commit",
                    "-m",
                    "Refactor auth boundary (#42)",
                    "-m",
                    "Reason: because policy checks need reuse.",
                    "-m",
                    "Fixes #7",
                ],
                cwd=repo,
            )

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(repo),
                    "--max-commits",
                    "20",
                    "src/auth.py",
                ],
                cwd=repo,
            )
            payload = json.loads(result.stdout)

        commit = payload["commits"][0]
        numbers = {item["number"] for item in commit["recorded_context"]["issue_references"]}
        self.assertIn("42", numbers)
        self.assertIn("7", numbers)
        rationale_text = " ".join(item["text"] for item in commit["recorded_context"]["explicit_rationales"])
        self.assertIn("policy checks need reuse", rationale_text)
        self.assertFalse(payload["external_evidence"]["enabled"])

    def test_ast_diff_detects_python_symbol_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run(["git", "init"], cwd=repo)
            run(["git", "config", "user.email", "tester@example.com"], cwd=repo)
            run(["git", "config", "user.name", "Test Author"], cwd=repo)

            src = repo / "src"
            src.mkdir()
            auth = src / "auth.py"
            auth.write_text(
                "import os\n\n"
                "def login(user):\n"
                "    return bool(user)\n",
                encoding="utf-8",
            )
            run(["git", "add", "src/auth.py"], cwd=repo)
            run(["git", "commit", "-m", "Add auth module"], cwd=repo)

            auth.write_text(
                "import os\n"
                "import hmac\n\n"
                "def login(user, *, active=True):\n"
                "    if not active:\n"
                "        return False\n"
                "    return bool(user)\n\n"
                "class Policy:\n"
                "    pass\n",
                encoding="utf-8",
            )
            run(["git", "add", "src/auth.py"], cwd=repo)
            run(["git", "commit", "-m", "Change auth semantic structure"], cwd=repo)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(repo),
                    "--max-commits",
                    "20",
                    "--ast-diff",
                    "src/auth.py",
                ],
                cwd=repo,
            )
            payload = json.loads(result.stdout)

        self.assertEqual(payload["schema_version"], "0.2")
        self.assertTrue(payload["semantic_diff"]["enabled"])
        commit = next(item for item in payload["commits"] if item["subject"] == "Change auth semantic structure")
        self.assertIn("semantic_change", commit["semantic_diff_summary"]["flags"])
        self.assertIn("signature_changed", commit["semantic_diff_summary"]["flags"])
        diff = commit["semantic_diffs"][0]
        self.assertEqual(diff["result"], "ok")
        self.assertIn("import hmac", diff["summary"]["imports_added"])
        modified = {item["qualname"]: item for item in diff["summary"]["symbols_modified"]}
        self.assertTrue(modified["login"]["signature_changed"])
        self.assertTrue(modified["login"]["body_changed"])
        added = {item["qualname"] for item in diff["summary"]["symbols_added"]}
        self.assertIn("Policy", added)


if __name__ == "__main__":
    unittest.main()
