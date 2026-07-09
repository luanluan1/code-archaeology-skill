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

        self.assertEqual(payload["schema_version"], "0.1")
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


if __name__ == "__main__":
    unittest.main()
