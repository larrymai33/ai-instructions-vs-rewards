import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.privacy_helpers import (
    get_index_entries,
    is_forbidden_publication_path,
    contains_sensitive_publication_text,
)


class PrivacyPatternTests(unittest.TestCase):
    def test_rejects_forbidden_paths(self):
        for path in ("models/model.gguf", "logs/run.txt", ".env", "cache/item.bin"):
            with self.subTest(path=path):
                self.assertTrue(is_forbidden_publication_path(path))

    def test_allows_publication_paths(self):
        for path in ("results/data.json", "report/figure.png", "scripts/verify.py"):
            with self.subTest(path=path):
                self.assertFalse(is_forbidden_publication_path(path))

    def test_detects_sensitive_text(self):
        samples = (
            '"thread' + '_id": "private"',
            "C:" + "\\" + "Users\\person\\file.txt",
            "Authorization: " + "Bear" + "er " + "secret-token",
            "contact" + "@" + "example.com",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(contains_sensitive_publication_text(sample))


class GitIndexTests(unittest.TestCase):
    def test_reads_staged_blob_not_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            path = repo / "example.txt"
            path.write_text("staged", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "example.txt"], check=True)
            path.write_text("dirty", encoding="utf-8")
            entries = get_index_entries(repo)
            self.assertEqual(len(entries), 1)
            blob = subprocess.run(
                ["git", "-C", str(repo), "cat-file", "blob", entries[0].object_id],
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual(blob, b"staged")


if __name__ == "__main__":
    unittest.main()
