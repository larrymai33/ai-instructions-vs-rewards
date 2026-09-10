"""Cross-platform privacy gate for every commit and blob reachable from refs."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.privacy_check import MAX_BLOB_BYTES, TEXT_SCAN_EXEMPTIONS
from scripts.privacy_helpers import (
    PrivacyError,
    contains_sensitive_publication_text,
    git_blob_bytes,
    git_blob_size,
    is_forbidden_publication_path,
    run_git_bytes,
    strict_utf8,
)


def scan_history(
    repo_root: Path,
    refs: Sequence[str],
    expected_author_name: str,
    expected_author_email: str,
) -> dict[str, Any]:
    if not refs or not expected_author_name or not expected_author_email:
        raise PrivacyError("Refs and expected release identity must not be empty.")
    tips: list[str] = []
    for ref_name in refs:
        resolved = strict_utf8(
            run_git_bytes(repo_root, ["rev-parse", "--verify", "--end-of-options", f"{ref_name}^{{commit}}"]),
            f"Resolved ref {ref_name}",
        ).strip()
        if re.fullmatch(r"[0-9a-f]{40,64}", resolved) is None:
            raise PrivacyError(f"Ref did not resolve to a commit: {ref_name}")
        tips.append(resolved)
    commits = [
        line
        for line in strict_utf8(
            run_git_bytes(repo_root, ["rev-list", *tips, "--"]), "Reachable commit listing"
        ).splitlines()
        if line
    ]
    if not commits:
        raise PrivacyError("No commits are reachable from the intended push refs.")
    violations: list[str] = []
    blob_paths: dict[str, set[str]] = defaultdict(set)
    tree_pattern = re.compile(r"^(\d+) (\w+) ([0-9a-f]+)\t([\s\S]+)$")
    for commit_id in commits:
        identity = strict_utf8(
            run_git_bytes(repo_root, ["show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", commit_id]),
            f"Commit identity {commit_id}",
        ).rstrip("\r\n").split("\0")
        expected = [expected_author_name, expected_author_email] * 2
        if identity != expected:
            violations.append(f"Commit identity is not the approved release identity: {commit_id}")
        tree = strict_utf8(
            run_git_bytes(repo_root, ["ls-tree", "-r", "-z", "--full-tree", commit_id]),
            f"Tree listing {commit_id}",
        )
        for raw_entry in tree.split("\0"):
            if not raw_entry:
                continue
            match = tree_pattern.fullmatch(raw_entry)
            if match is None:
                raise PrivacyError(f"Malformed tree entry in {commit_id}.")
            _, kind, object_id, path = match.groups()
            if kind == "blob":
                blob_paths[object_id].add(path)
    path_pairs = 0
    for object_id in sorted(blob_paths):
        paths = sorted(blob_paths[object_id])
        path_pairs += len(paths)
        for path in paths:
            if is_forbidden_publication_path(path):
                violations.append(f"Forbidden reachable path: {path} (blob {object_id})")
        size = git_blob_size(repo_root, object_id)
        if size > MAX_BLOB_BYTES:
            violations.append(
                f"Reachable blob exceeds 10 MiB: {object_id} ({size} bytes; paths: {', '.join(paths)})"
            )
            continue
        text_paths = [path for path in paths if Path(path).suffix.lower() not in TEXT_SCAN_EXEMPTIONS]
        if not text_paths:
            continue
        try:
            text = strict_utf8(git_blob_bytes(repo_root, object_id), f"Reachable blob {object_id}")
        except PrivacyError as error:
            violations.append(f"Unable to scan reachable text blob: {object_id} ({error})")
            continue
        if contains_sensitive_publication_text(text):
            violations.append(
                f"Sensitive reachable blob text: {object_id} (paths: {', '.join(text_paths)})"
            )
    return {
        "commits": len(commits),
        "blobs": len(blob_paths),
        "path_pairs": path_pairs,
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit all Git history reachable from publication refs.")
    parser.add_argument("--expected-author-name", required=True)
    parser.add_argument("--expected-author-email", required=True)
    parser.add_argument("--ref", action="append", required=True, dest="refs")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    try:
        result = scan_history(
            args.repo_root.resolve(), args.refs, args.expected_author_name, args.expected_author_email
        )
    except PrivacyError as error:
        print(f"History privacy check failed: {error}")
        return 1
    for violation in result["violations"]:
        print(f"VIOLATION: {violation}")
    print(
        f"History privacy check: {result['commits']} commit(s), {result['blobs']} unique blob(s), "
        f"{result['path_pairs']} blob/path pair(s), {len(result['violations'])} violation(s)."
    )
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
