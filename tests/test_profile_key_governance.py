from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROFILE_KEYS = (
    "hybrid_growth_income",
    "semiconductor_rotation_income",
    "tech_pullback_cash_buffer",
)
ALLOWED_PATHS = ['tests/test_profile_key_governance.py']


def _iter_repo_files():
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("research/results/"):
            continue
        yield path, rel


def test_legacy_profile_keys_only_exist_in_explicit_rejection_tests():
    offenders: dict[str, tuple[str, ...]] = {}
    for path, rel in _iter_repo_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = tuple(key for key in LEGACY_PROFILE_KEYS if key in text)
        if hits and rel not in ALLOWED_PATHS:
            offenders[rel] = hits
    assert offenders == {}
