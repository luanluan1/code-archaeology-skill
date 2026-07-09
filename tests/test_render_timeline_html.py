import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "code-archaeology" / "scripts" / "render_timeline_html.py"


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


class RenderTimelineHtmlTests(unittest.TestCase):
    def test_renders_standalone_escaped_timeline(self):
        payload = {
            "schema_version": "0.2",
            "repo": {
                "root": "/repo",
                "head": "abcdef1234567890",
                "branch": "main",
                "history_complete": True,
            },
            "query": {
                "raw_target": "src/auth.py",
                "target_type": "file",
                "normalized_paths": ["src/auth.py"],
            },
            "collection": {
                "warnings": ["Working tree has local changes"],
                "limits": {"max_commits": 20, "top_k_enriched": 5},
            },
            "timeline_candidates": [
                {
                    "phase": "2026-Q1",
                    "start": "2026-01-01T00:00:00+00:00",
                    "end": "2026-02-01T00:00:00+00:00",
                    "commit_shas": ["abcdef1234567890"],
                    "signals": ["refactor", "bugfix"],
                }
            ],
            "commits": [
                {
                    "sha": "abcdef1234567890",
                    "author_date": "2026-01-15T00:00:00+00:00",
                    "subject": "Refactor <auth> boundary",
                    "flags": ["refactor"],
                    "changed_paths": ["src/auth.py"],
                    "importance": {"score": 73.5, "confidence": 0.8},
                    "semantic_diff_summary": {"flags": ["semantic_change"], "files_analyzed": 1, "files_skipped": 0},
                    "recorded_context": {
                        "issue_references": [{"raw": "#42", "number": "42", "kind": "issue_or_pr"}],
                        "explicit_rationales": [{"text": "Reason: 因为策略复用"}],
                    },
                }
            ],
            "people": [
                {
                    "identity": "Test Author <abc123>",
                    "first_touch": "2026-01-15T00:00:00+00:00",
                    "last_touch": "2026-01-15T00:00:00+00:00",
                    "commit_count": 1,
                    "weighted_importance": 73.5,
                    "current_blame_lines": 12,
                }
            ],
            "external_evidence": {
                "enabled": False,
                "provider": None,
                "warnings": [],
                "artifacts": [],
                "recorded_rationales": [],
                "collaboration_signals": [],
                "caveat": "Remote evidence is opt-in.",
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "evidence.json"
            output = root / "timeline.html"
            source.write_text(json.dumps(payload), encoding="utf-8")

            result = run(
                [sys.executable, str(SCRIPT), str(source), "--output", str(output)],
                cwd=root,
            )

            html = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Code Archaeology Timeline", html)
        self.assertIn("src/auth.py", html)
        self.assertIn("2026-Q1", html)
        self.assertIn("Refactor &lt;auth&gt; boundary", html)
        self.assertIn("因为策略复用", html)
        self.assertNotIn("Refactor <auth> boundary", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link href=", html)


if __name__ == "__main__":
    unittest.main()
