"""Conservative runtime binding for durable jobs, including editable checkouts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import platform
from pathlib import Path


def runtime_identity() -> dict:
    packages = (
        "ac-jobs",
        "ac-llm",
        "ac-document",
        "ac-proposer-reviewer",
        "alc-render",
        "alc-translate",
        "alc-companion",
        "alc-web",
    )
    result = {}
    for name in packages:
        spec = importlib.util.find_spec(name.replace("-", "_"))
        if spec is None or not spec.submodule_search_locations:
            raise RuntimeError(f"Required runtime package is unavailable: {name}")
        root = Path(next(iter(spec.submodule_search_locations)))
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*.py")):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        result[name] = {
            "version": importlib.metadata.version(name),
            "code_sha256": digest.hexdigest(),
        }
    libraries = {
        name: importlib.metadata.version(name)
        for name in (
            "jsonschema",
            "json-repair",
            "beautifulsoup4",
            "lxml",
            "markdown-it-py",
            "Pillow",
            "httpx",
        )
    }
    return {
        "schema_version": "alc.web.runtime.v1",
        "python": platform.python_version(),
        "packages": result,
        "libraries": libraries,
    }
