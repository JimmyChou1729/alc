#!/usr/bin/env python3
"""Check formal tag versions and, optionally, immutable runtime provenance."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "alc-catalog", "alc-companion", "alc-ocr-proofread", "alc-render",
    "alc-translate", "alc-web",
}
SCRIPTS = Path("plugins/alc/skills/alc/scripts")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def document(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
    )
    require(result.returncode == 0, f"git {' '.join(args)} failed in {root}: {result.stderr.strip()}")
    return result.stdout.strip()


def check_versions(root: Path, tag: str) -> None:
    require(re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag) is not None,
            "tag must be vMAJOR.MINOR.PATCH without leading zeroes")
    version = tag[1:]

    def matches(value: object, label: object) -> None:
        require(value == version, f"{label}: expected {version}, found {value!r}")

    matches((root / "VERSION").read_text(encoding="utf-8").strip(), "VERSION")
    projects = sorted((root / "packages").glob("alc-*/pyproject.toml"))
    require({p.parent.name for p in projects} == PACKAGES, "ALC package set differs from release contract")
    for project in projects:
        matches(tomllib.loads(project.read_text(encoding="utf-8"))["project"]["version"], project)
        init = project.parent / "src" / project.parent.name.replace("-", "_") / "__init__.py"
        values = [ast.literal_eval(node.value) for node in ast.parse(init.read_text(encoding="utf-8")).body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
        require(len(values) == 1, f"{init}: expected exactly one literal __version__")
        matches(values[0], init)
    for relative in ("plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = root / "plugins/alc" / relative
        matches(document(path)["version"], path)
    for name in ("package.json", "package-lock.json"):
        path = root / "apps/web" / name
        data = document(path)
        matches(data["version"], path)
        if name == "package-lock.json":
            matches(data["packages"][""]["version"], f"{path}: packages['']")


def check_pins(root: Path, foundation_root: Path) -> None:
    lock = document(root / SCRIPTS / "runtime-sources.json")
    sources = lock["sources"]
    require(len(sources) == 2 and {item["id"] for item in sources} == {"product", "foundation"},
            "runtime lock must contain exactly one product and one foundation source")
    by_id = {item["id"]: item for item in sources}
    for source_id, repo in (("product", "alc"), ("foundation", "ac-foundation")):
        source = by_id[source_id]
        require(source["repository"] == f"https://github.com/tririver/{repo}.git",
                f"{source_id}: formal tags require the canonical upstream repository")
        require(re.fullmatch(r"[0-9a-f]{40}", source["commit"]) is not None,
                f"{source_id}: commit must be a full lowercase SHA")
    product_sha = by_id["product"]["commit"]
    git(root, "cat-file", "-e", f"{product_sha}^{{commit}}")
    git(root, "merge-base", "--is-ancestor", product_sha, "HEAD")
    require(git(root, "rev-parse", f"{product_sha}:packages") == git(root, "rev-parse", "HEAD:packages"),
            "product pin packages tree differs from the tagged packages tree")
    expected_packages = PACKAGES - {"alc-web"}
    packages = by_id["product"]["packages"]
    require(len(packages) == len(expected_packages) and set(packages) == expected_packages,
            "product pin package list differs from the plugin runtime")
    foundation_sha = by_id["foundation"]["commit"]
    require(document(root / SCRIPTS / "generated-sources.json")["foundation_commit"] == foundation_sha,
            "generated source manifest differs from the Foundation pin")
    git(foundation_root, "cat-file", "-e", f"{foundation_sha}^{{commit}}")
    git(foundation_root, "merge-base", "--is-ancestor", foundation_sha, "refs/remotes/origin/main")
    require(git(foundation_root, "rev-parse", "HEAD") == foundation_sha,
            "Foundation checkout HEAD differs from the locked commit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check-pins", action="store_true")
    parser.add_argument("--foundation-root", type=Path)
    args = parser.parse_args()
    if args.check_pins and args.foundation_root is None:
        parser.error("--check-pins requires --foundation-root (full upstream clone at the locked SHA)")
    try:
        check_versions(args.root, args.tag)
        if args.check_pins:
            check_pins(args.root, args.foundation_root)
    except (ValueError, KeyError, OSError, SyntaxError, TypeError) as exc:
        parser.exit(1, f"release tag validation failed: {exc}\n")
    print(f"{args.tag}: versions verified" + ("; runtime provenance verified" if args.check_pins else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
