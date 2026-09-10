import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout

from scripts.history_privacy_check import scan_history
from scripts.privacy_check import scan_index
from scripts.verify import run_verification
from scripts.verify_helpers import VerificationError, verify_repository


REPO_ROOT = Path(__file__).resolve().parents[2]


class RepositoryVerificationTests(unittest.TestCase):
    def test_frozen_broad_screen_hashes_match_staged_git_blobs(self):
        reference = json.loads(
            (REPO_ROOT / "results" / "derived" / "verification-reference.json").read_text(
                encoding="utf-8"
            )
        )

        for source in reference["broad_screen"]["sources"]:
            result = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "show", f":{source['path']}"],
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            with self.subTest(path=source["path"]):
                self.assertEqual(hashlib.sha256(result.stdout).hexdigest(), source["sha256"])

    def test_frozen_repository_recomputes_published_results(self):
        summary = verify_repository(REPO_ROOT)
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["logprob"]["rows"], 112)
        self.assertEqual(summary["logprob"]["coverage"], "14x8")
        self.assertAlmostEqual(summary["logprob"]["primary_did"], -0.9345689862966537)
        self.assertEqual(summary["broad_screen"], {
            "calls": 58,
            "model_ids": 13,
            "strict_valid": 50,
            "strict_valid_odd": 0,
        })
        self.assertEqual(summary["mirrored_capped_thinking_conflict_reward_alignment"], "0/12")
        self.assertEqual(summary["explicit_maximize_capped_thinking_reward_alignment"], "6/6")

    def test_entry_point_prints_machine_readable_summary(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = run_verification(REPO_ROOT, run_tests=False, run_privacy=False)
        self.assertEqual(exit_code, 0)
        self.assertIn("VERIFICATION_SUMMARY\n{", output.getvalue())
        self.assertIn('"status": "passed"', output.getvalue())


class PrivacyEntryPointTests(unittest.TestCase):
    def test_privacy_cli_runs_as_a_script(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "safe.txt").write_text("safe", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "safe.txt"], check=True)
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "privacy_check.py"), "--repo-root", str(repo)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 staged file(s) scanned, 0 violation(s)", result.stdout)

    def test_history_cli_runs_as_a_script(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            release_email = "release" + "@" + "example.invalid"
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Release Author"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", release_email], check=True)
            (repo / "safe.txt").write_text("safe", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "safe.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "safe"], check=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "history_privacy_check.py"),
                    "--repo-root", str(repo),
                    "--ref", "refs/heads/main",
                    "--expected-author-name", "Release Author",
                    "--expected-author-email", release_email,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0 violation(s)", result.stdout)

    def test_index_scan_reads_staged_sensitive_content(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            path = repo / "example.txt"
            path.write_text("safe", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "example.txt"], check=True)
            path.write_text("contact" + "@" + "example.com", encoding="utf-8")
            self.assertEqual(scan_index(repo)["violations"], [])
            subprocess.run(["git", "-C", str(repo), "add", "example.txt"], check=True)
            self.assertIn("Sensitive staged publication text", scan_index(repo)["violations"][0])

    def test_history_scan_checks_identity_and_removed_blobs(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            release_email = "release" + "@" + "example.invalid"
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Release Author"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", release_email], check=True)
            (repo / "safe.txt").write_text("safe", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "safe.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "safe"], check=True)
            result = scan_history(repo, ["refs/heads/main"], "Release Author", release_email)
            self.assertEqual(result["violations"], [])
            wrong = scan_history(repo, ["refs/heads/main"], "Another Author", release_email)
            self.assertIn("Commit identity is not the approved release identity", wrong["violations"][0])


if __name__ == "__main__":
    unittest.main()
