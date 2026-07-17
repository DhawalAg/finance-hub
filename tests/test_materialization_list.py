"""Tests for the runtime surface materialization list (evals/materialization_list.txt).

The materialization list is the authoritative manifest of every file the harness copies
into a trial dir. It is also the exact input to the §8.3 prompt hash. These tests enforce:
  - the file exists and parses cleanly
  - every listed file exists on disk under runtime/
  - no dev-scaffolding paths appear (root CLAUDE.md, docs/agents/, etc.)
  - runtime/CLAUDE.md is present
  - the prompt hash is deterministic
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MATERIALIZATION_LIST = REPO_ROOT / "evals" / "materialization_list.txt"

_DEV_SCAFFOLDING_PREFIXES = (
    "CLAUDE.md",
    "AGENTS.md",
    "docs/agents/",
    "docs/requests/",
    "docs/adr/",
    "docs/notes/",
)


def _parse_list(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


class TestMaterializationList:
    def test_file_exists(self):
        assert MATERIALIZATION_LIST.exists(), (
            f"Materialization list not found at {MATERIALIZATION_LIST}"
        )

    def test_every_listed_file_exists(self):
        missing = [
            rel
            for rel in _parse_list(MATERIALIZATION_LIST)
            if not (REPO_ROOT / rel).exists()
        ]
        assert not missing, f"Listed files do not exist: {missing}"

    def test_all_paths_under_runtime(self):
        non_runtime = [
            rel
            for rel in _parse_list(MATERIALIZATION_LIST)
            if not rel.startswith("runtime/")
        ]
        assert not non_runtime, (
            f"Paths not under runtime/ found in materialization list: {non_runtime}"
        )

    def test_no_dev_scaffolding(self):
        bad = [
            rel
            for rel in _parse_list(MATERIALIZATION_LIST)
            if any(rel == p or rel.startswith(p) for p in _DEV_SCAFFOLDING_PREFIXES)
        ]
        assert not bad, f"Dev-scaffolding paths in materialization list: {bad}"

    def test_runtime_claude_md_is_listed(self):
        assert "runtime/CLAUDE.md" in _parse_list(MATERIALIZATION_LIST), (
            "runtime/CLAUDE.md is missing from the materialization list"
        )

    def test_no_duplicate_entries(self):
        entries = _parse_list(MATERIALIZATION_LIST)
        assert len(entries) == len(set(entries)), (
            "Materialization list has duplicate entries"
        )

    def test_prompt_hash_is_deterministic(self):
        entries = _parse_list(MATERIALIZATION_LIST)

        def compute_hash() -> str:
            h = hashlib.sha256()
            for rel in entries:
                h.update(rel.encode())
                h.update(b"\n")
                h.update((REPO_ROOT / rel).read_bytes())
                h.update(b"\n")
            return h.hexdigest()

        assert compute_hash() == compute_hash()
