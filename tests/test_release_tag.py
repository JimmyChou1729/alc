"""Offline release checks against small real Git histories."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check-release-tag.py"
SPEC = importlib.util.spec_from_file_location("alc_release_tag", SCRIPT)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def write(root: Path, relative: str | Path, value: str | dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, dict) else value, encoding="utf-8")
    return path


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def init(root: Path) -> None:
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "commit.gpgsign", "false")


def commit(root: Path, message: str) -> str:
    git(root, "add", ".")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def release(tmp_path: Path) -> tuple[Path, Path]:
    root, foundation = tmp_path / "alc", tmp_path / "foundation"
    init(root)
    init(foundation)
    write(foundation, "VERSION", "2.0.0\n")
    foundation_sha = commit(foundation, "Foundation")
    git(foundation, "update-ref", "refs/remotes/origin/main", foundation_sha)
    write(root, "VERSION", "3.1.2\n")
    for package in CHECKER.PACKAGES:
        write(root, f"packages/{package}/pyproject.toml", '[project]\nversion = "3.1.2"\n')
        write(root, f"packages/{package}/src/{package.replace('-', '_')}/__init__.py", '__version__ = "3.1.2"\n')
    for manifest in ("plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        write(root, f"plugins/alc/{manifest}", {"version": "3.1.2"})
    write(root, "apps/web/package.json", {"version": "3.1.2"})
    write(root, "apps/web/package-lock.json", {"version": "3.1.2", "packages": {"": {"version": "3.1.2"}}})
    source_sha = commit(root, "Product source")
    write(root, CHECKER.SCRIPTS / "runtime-sources.json", {"sources": [
        {"id": "product", "repository": "https://github.com/tririver/alc.git", "commit": source_sha,
         "packages": sorted(CHECKER.PACKAGES - {"alc-web"})},
        {"id": "foundation", "repository": "https://github.com/tririver/ac-foundation.git", "commit": foundation_sha},
    ]})
    write(root, CHECKER.SCRIPTS / "generated-sources.json", {"foundation_commit": foundation_sha})
    commit(root, "Pin source")
    return root, foundation


def test_pin_only_commit_is_valid(release):
    root, foundation = release
    result = subprocess.run([
        sys.executable, str(SCRIPT), "--root", str(root), "--tag", "v3.1.2",
        "--check-pins", "--foundation-root", str(foundation),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "runtime provenance verified" in result.stdout


@pytest.mark.parametrize("tag", ["3.1.2", "v03.1.2", "v3.1.2-rc1", "v3.1.3"])
def test_invalid_or_mismatched_tag(release, tag):
    with pytest.raises(ValueError):
        CHECKER.check_versions(release[0], tag)


@pytest.mark.parametrize("relative", [
    "VERSION", "packages/alc-render/pyproject.toml",
    "packages/alc-render/src/alc_render/__init__.py",
    "plugins/alc/plugin.json", "plugins/alc/.codex-plugin/plugin.json",
    "plugins/alc/.claude-plugin/plugin.json", "apps/web/package.json",
    "apps/web/package-lock.json",
])
def test_version_drift(release, relative):
    path = release[0] / relative
    path.write_text(path.read_text().replace("3.1.2", "3.1.1"))
    with pytest.raises(ValueError, match="expected 3.1.2"):
        CHECKER.check_versions(release[0], "v3.1.2")


def test_frontend_lock_root_version(release):
    root, _ = release
    write(root, "apps/web/package-lock.json", {"version": "3.1.2", "packages": {"": {"version": "0.0.0"}}})
    with pytest.raises(ValueError, match="packages"):
        CHECKER.check_versions(root, "v3.1.2")


def test_stale_product_pin(release):
    root, foundation = release
    write(root, "packages/alc-render/src/alc_render/new.py", "value = 1\n")
    commit(root, "Change product after pin")
    with pytest.raises(ValueError, match="packages tree differs"):
        CHECKER.check_pins(root, foundation)


@pytest.mark.parametrize("source_id", ["product", "foundation"])
@pytest.mark.parametrize("field,value", [("repository", "https://github.com/example/fork.git"), ("commit", "abcdef0")])
def test_development_sources_rejected(release, source_id, field, value):
    root, foundation = release
    path = root / CHECKER.SCRIPTS / "runtime-sources.json"
    lock = json.loads(path.read_text())
    next(source for source in lock["sources"] if source["id"] == source_id)[field] = value
    write(root, path.relative_to(root), lock)
    with pytest.raises(ValueError, match=source_id):
        CHECKER.check_pins(root, foundation)


def test_foundation_commit_must_be_merged(release):
    root, foundation = release
    write(foundation, "new", "unmerged")
    sha = commit(foundation, "Unmerged Foundation")
    path = root / CHECKER.SCRIPTS / "runtime-sources.json"
    lock = json.loads(path.read_text())
    lock["sources"][1]["commit"] = sha
    write(root, path.relative_to(root), lock)
    write(root, CHECKER.SCRIPTS / "generated-sources.json", {"foundation_commit": sha})
    with pytest.raises(ValueError, match="merge-base"):
        CHECKER.check_pins(root, foundation)


def test_generated_manifest_must_match_pin(release):
    root, foundation = release
    write(root, CHECKER.SCRIPTS / "generated-sources.json", {"foundation_commit": "a" * 40})
    with pytest.raises(ValueError, match="generated source manifest"):
        CHECKER.check_pins(root, foundation)


def test_unmerged_product_pin(release):
    root, foundation = release
    current = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-b", "unmerged")
    write(root, "note", "side branch")
    sha = commit(root, "Unmerged product")
    git(root, "checkout", "--detach", current)
    path = root / CHECKER.SCRIPTS / "runtime-sources.json"
    lock = json.loads(path.read_text())
    lock["sources"][0]["commit"] = sha
    write(root, path.relative_to(root), lock)
    with pytest.raises(ValueError, match="merge-base"):
        CHECKER.check_pins(root, foundation)
