"""Git-index and history privacy helpers shared by Python entry points."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class PrivacyError(RuntimeError):
    """Raised when Git data cannot be inspected safely."""


@dataclass(frozen=True)
class GitIndexEntry:
    path: str
    object_id: str
    mode: str


def run_git_bytes(repo_root: Path, arguments: Sequence[str]) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise PrivacyError(f"git {' '.join(arguments)} failed: {message}")
    return result.stdout


def strict_utf8(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PrivacyError(f"{label} is not valid UTF-8 text.") from error


def get_index_entries(repo_root: Path) -> list[GitIndexEntry]:
    listing = strict_utf8(
        run_git_bytes(repo_root, ["ls-files", "--stage", "-z"]), "Git index listing"
    )
    entries: list[GitIndexEntry] = []
    seen: set[str] = set()
    pattern = re.compile(r"^(\d+) ([0-9a-fA-F]+) (\d+)\t([\s\S]+)$")
    for raw_entry in listing.split("\0"):
        if not raw_entry:
            continue
        match = pattern.fullmatch(raw_entry)
        if match is None:
            raise PrivacyError(f"Malformed Git index entry: {raw_entry}")
        mode, object_id, stage_text, path = match.groups()
        stage = int(stage_text)
        if stage != 0:
            raise PrivacyError(f"Unmerged Git index entry is not publishable: {path} (stage {stage}).")
        if path in seen:
            raise PrivacyError(f"Duplicate Git index path: {path}")
        seen.add(path)
        entries.append(GitIndexEntry(path=path, object_id=object_id.lower(), mode=mode))
    return entries


_FORBIDDEN_EXTENSION = re.compile(r"\.(gguf|pyc|zip|7z|dll|exe)$", re.IGNORECASE)
_FORBIDDEN_SEGMENT = re.compile(
    r"(^|/)(runtime|downloads|process-cache|logs|__pycache__|\.serena|"
    r"\.env(?:\.[^/]+)?|cache|\.cache|models?|local-manifests|tmp-clone|"
    r"temp-clone|[^/]*-clone|[^/]*manifest\.local[^/]*|"
    r"(?=[^/]*32b)(?=[^/]*incomplete)[^/]+|[^/]*(credential|token)[^/]*)(/|$)",
    re.IGNORECASE,
)


def is_forbidden_publication_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/").lstrip("/")
    return bool(_FORBIDDEN_EXTENSION.search(normalized) or _FORBIDDEN_SEGMENT.search(normalized))


_SENSITIVE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"[\"']?thread_id[\"']?\s*:",
        r"\b[A-Z]:[\\/]+Users(?:[\\/]|$)",
        r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----",
        r"\bBearer\s+\S+",
        r"\b[A-Z0-9_]*(api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|client[_-]?secret|password)\b\s*[:=]\s*[\"']?\S+",
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    )
)


def contains_sensitive_publication_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)


def git_blob_size(repo_root: Path, object_id: str) -> int:
    text = strict_utf8(run_git_bytes(repo_root, ["cat-file", "-s", object_id]), f"Git object size for {object_id}")
    try:
        value = int(text.strip())
    except ValueError as error:
        raise PrivacyError(f"Git returned an invalid blob size for {object_id}.") from error
    if value < 0:
        raise PrivacyError(f"Git returned an invalid blob size for {object_id}.")
    return value


def git_blob_bytes(repo_root: Path, object_id: str) -> bytes:
    return run_git_bytes(repo_root, ["cat-file", "blob", object_id])
