"""Cross-platform staged-publication privacy gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.privacy_helpers import (
    PrivacyError,
    contains_sensitive_publication_text,
    get_index_entries,
    git_blob_bytes,
    git_blob_size,
    is_forbidden_publication_path,
    strict_utf8,
)


MAX_BLOB_BYTES = 10 * 1024 * 1024
TEXT_SCAN_EXEMPTIONS = {".png", ".docx"}


def scan_index(repo_root: Path) -> dict[str, Any]:
    entries = get_index_entries(repo_root)
    violations: list[str] = []
    for entry in entries:
        if is_forbidden_publication_path(entry.path):
            violations.append(f"Forbidden staged path: {entry.path}")
            continue
        size = git_blob_size(repo_root, entry.object_id)
        if size > MAX_BLOB_BYTES:
            violations.append(f"Staged blob exceeds 10 MiB: {entry.path}")
            continue
        if Path(entry.path).suffix.lower() in TEXT_SCAN_EXEMPTIONS:
            continue
        try:
            text = strict_utf8(git_blob_bytes(repo_root, entry.object_id), f"Staged blob {entry.path}")
        except PrivacyError as error:
            violations.append(f"Unable to scan staged blob: {entry.path} ({error})")
            continue
        if contains_sensitive_publication_text(text):
            violations.append(f"Sensitive staged publication text: {entry.path}")
    return {"scanned": len(entries), "violations": violations}


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan staged Git blobs for publication risks.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    try:
        result = scan_index(args.repo_root.resolve())
    except PrivacyError as error:
        print(f"Privacy check failed: {error}")
        return 1
    for violation in result["violations"]:
        print(f"VIOLATION: {violation}")
    print(
        f"Privacy check: {result['scanned']} staged file(s) scanned, "
        f"{len(result['violations'])} violation(s)."
    )
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
