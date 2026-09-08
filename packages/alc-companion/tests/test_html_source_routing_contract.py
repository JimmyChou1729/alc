from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_direct_html_routing_stays_skill_owned_and_uses_one_bundle_contract() -> None:
    skill = (
        _REPOSITORY_ROOT / "plugins" / "alc" / "skills" / "alc" / "SKILL.md"
    ).read_text(encoding="utf-8")
    workflow = (
        _REPOSITORY_ROOT
        / "plugins"
        / "alc"
        / "skills"
        / "alc"
        / "workflows"
        / "companion.md"
    ).read_text(encoding="utf-8")
    manual = (
        _REPOSITORY_ROOT
        / "plugins"
        / "alc"
        / "skills"
        / "alc"
        / "manuals"
        / "alc-companion.md"
    ).read_text(encoding="utf-8")
    readme = (
        _REPOSITORY_ROOT / "packages" / "alc-companion" / "README.md"
    ).read_text(encoding="utf-8")
    assert "ac-document acquire-html-bundle" in skill
    assert "ac-document acquire-html-bundle" in workflow
    assert "ac-document acquire-html-bundle" in manual
    assert "--output-dir <bundle-dir>" in workflow
    assert "--html-source-manifest" in workflow
    assert "--html-source-manifest bundle/manifest.json" in readme
    assert "Do not choose an alternate acquisition route merely because ARC is installed" in skill
    assert "--execution-profile local-app" in skill
    assert "--review-rounds 1" in skill
    assert "1–8 workers" in skill


def test_companion_package_declares_no_arc_runtime_dependency() -> None:
    package = (
        _REPOSITORY_ROOT / "packages" / "alc-companion" / "pyproject.toml"
    ).read_text(encoding="utf-8")
    source_root = _REPOSITORY_ROOT / "packages" / "alc-companion" / "src"
    arc_distribution = "-".join(("arc", "paper"))
    arc_module = "_".join(("arc", "paper"))

    assert arc_distribution not in package
    assert arc_module not in package
    assert not any(
        f"import {arc_module}" in path.read_text(encoding="utf-8")
        or f"from {arc_module}" in path.read_text(encoding="utf-8")
        for path in source_root.rglob("*.py")
    )
