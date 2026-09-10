"""Cross-platform, model-free verification entry point."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.privacy_check import scan_index
from scripts.privacy_helpers import PrivacyError
from scripts.verify_helpers import VerificationError, verify_repository


def _run_tests(repo_root: Path) -> None:
    commands = (
        [sys.executable, "-m", "unittest", "discover", "-s", "experiments/broad-screen/tests", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "report/tests", "-p", "test_build_report.py", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests", "-p", "test_python*.py", "-v"],
    )
    labels = ("broad-screen tests", "report builder safety tests", "Python verifier tests")
    for label, command in zip(labels, commands):
        print(f"VERIFY {label}", flush=True)
        result = subprocess.run(command, cwd=repo_root, check=False)
        if result.returncode != 0:
            raise VerificationError(f"{label} failed with exit code {result.returncode}.")


def run_verification(repo_root: Path, *, run_tests: bool = True, run_privacy: bool = True) -> int:
    try:
        if run_tests:
            _run_tests(repo_root)
        summary = verify_repository(repo_root)
        if run_privacy:
            privacy = scan_index(repo_root)
            for violation in privacy["violations"]:
                print(f"VIOLATION: {violation}")
            print(
                f"Privacy check: {privacy['scanned']} staged file(s) scanned, "
                f"{len(privacy['violations'])} violation(s)."
            )
            if privacy["violations"]:
                raise VerificationError("Staged-file privacy gate failed.")
            summary["privacy_gate"] = "passed"
        print("VERIFICATION_SUMMARY")
        print(json.dumps(summary, indent=2))
        return 0
    except (OSError, PrivacyError, VerificationError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Repository verification failed: {error}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the published experiment without running a model.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--skip-tests", action="store_true", help="Run evidence checks without unit tests.")
    parser.add_argument("--skip-privacy", action="store_true", help="Skip the staged-file publication gate.")
    args = parser.parse_args()
    return run_verification(
        args.repo_root.resolve(), run_tests=not args.skip_tests, run_privacy=not args.skip_privacy
    )


if __name__ == "__main__":
    raise SystemExit(main())
