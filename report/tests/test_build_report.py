import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPORT_DIR = Path(__file__).resolve().parents[1]
BUILDER = REPORT_DIR / "build_report.py"
AUDITED_NAME = "odd-number-model-forensics-takehome.docx"


class ReportBuilderSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.builder = self.root / "build_report.py"
        self.builder.write_bytes(BUILDER.read_bytes())
        figures = self.root / "figures"
        figures.mkdir()
        for name in ("behavioral-results.png", "logprob-results.png"):
            (figures / name).write_bytes((REPORT_DIR / "figures" / name).read_bytes())
        self.audited = self.root / AUDITED_NAME
        self.audited.write_bytes(b"audited-sentinel")
        self.figure_bytes = {
            path.name: path.read_bytes() for path in figures.iterdir()
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_builder(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-S", str(self.builder), "--check-output-policy", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_dependency_free_default_policy_preserves_hash_gated_artifacts(self):
        result = self.run_builder()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str((self.root / "generated" / AUDITED_NAME).resolve()), result.stdout)
        self.assertFalse((self.root / "generated" / AUDITED_NAME).exists())
        self.assertEqual(self.audited.read_bytes(), b"audited-sentinel")
        for name, expected in self.figure_bytes.items():
            self.assertEqual((self.root / "figures" / name).read_bytes(), expected)

    def test_checked_in_docx_requires_force_even_with_explicit_output(self):
        result = self.run_builder("--output", str(self.audited))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--force", result.stderr)
        self.assertEqual(self.audited.read_bytes(), b"audited-sentinel")

    def test_force_allows_deliberate_checked_in_docx_policy(self):
        result = self.run_builder("--output", str(self.audited), "--force")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.audited.resolve()), result.stdout)
        self.assertEqual(self.audited.read_bytes(), b"audited-sentinel")


if __name__ == "__main__":
    unittest.main()
