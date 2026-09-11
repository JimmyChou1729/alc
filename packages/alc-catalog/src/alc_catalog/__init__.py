"""Local project discovery; catalog entries never own task execution."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any

__version__ = "2.1.2"

KINDS = ('companion', 'translate', 'ocr-proofread', 'pdf-bundle-proofread')


def catalog_root() -> Path:
    return Path(os.environ.get('ALC_CATALOG_DIR', str(Path.home() / '.alc/catalog'))).expanduser()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Invalid catalog document')
    return value


def register_project(project: str | Path) -> str:
    path = Path(project).expanduser().resolve()
    key = hashlib.sha256(str(path).encode()).hexdigest()
    root = catalog_root() / 'projects'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {'schema_version': 'alc.catalog.project.v1', 'path': str(path)}
    fd, temporary = tempfile.mkstemp(prefix='.project-', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(payload, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, root / f'{key}.json')
    finally:
        Path(temporary).unlink(missing_ok=True)
    return key


def register_cli_project(value: str | Path | None) -> None:
    if value is None:
        return
    try:
        register_project(value)
    except OSError as exc:
        # Discovery failure must not abort expensive document processing.
        warnings.warn(f'ALC history registration failed: {type(exc).__name__}', RuntimeWarning)


def projects() -> list[Path]:
    result = []
    for entry in sorted((catalog_root() / 'projects').glob('*.json')):
        try:
            value = _read(entry)
            path = Path(value['path']).expanduser().resolve()
            if (value['schema_version'] != 'alc.catalog.project.v1'
                    or entry.stem != hashlib.sha256(str(path).encode()).hexdigest()):
                continue
            result.append(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result


def _inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('History file escaped its project')
    return resolved


def project_records(project: Path) -> list[dict[str, Any]]:
    """Read each durable run; skip broken records without hiding healthy siblings."""
    result = []
    for kind in KINDS:
        base = project / '.alc' / kind
        try:
            marker = _read(_inside(base / 'project.json', project))
        except (OSError, ValueError):
            marker = {}
        for run in sorted((base / 'jobs/runs').glob('*')):
            try:
                snapshot = _read(_inside(run / 'snapshot.json', project))
                spec = _read(_inside(run / 'spec.json', project))
                if kind == 'translate' and spec.get('handler', '').startswith((
                    'alc.translate.detect_language.', 'alc.translate.build_glossary.')):
                    continue
                run_id = snapshot['run_id']
                if run_id != run.name or spec.get('run_id') != run_id:
                    continue
                key = hashlib.sha256(f'{project}\0{kind}\0{run_id}'.encode()).hexdigest()
                source = spec.get('semantic_input', {}).get('request', {}).get('source', {})
                title = source.get('metadata', {}).get('title') if isinstance(source, dict) else None
                if not isinstance(title, str) or not title.strip():
                    title = next((b.get('payload', {}).get('text') for b in source.get('blocks', [])
                                  if b.get('kind') == 'heading' and isinstance(b.get('payload', {}).get('text'), str)), None) if isinstance(source, dict) else None
                result.append({'id': 'agent-' + key, 'project': str(project), 'kind': kind,
                    'run_id': run_id, 'state': snapshot.get('status', 'unknown'),
                    'created_at': snapshot.get('created_at'), 'updated_at': snapshot.get('updated_at'),
                    'title': title if isinstance(title, str) and title.strip() else project.name,
                    'reader': _reader(project, kind, run, marker),
                    'artifact': _artifact(project, run, snapshot)})
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
    return result


def _reader(project: Path, kind: str, run: Path, marker: dict) -> str | None:
    candidates = [project / '.alc' / kind / 'publications' / run.name / 'companion.html',
                  run / 'partial-reader/companion.html']
    if marker.get('current_run_id') == run.name:
        candidates.insert(0, project / 'companion.html')
    for candidate in candidates:
        try:
            safe = _inside(candidate, project)
        except ValueError:
            continue
        if safe.is_file():
            return str(safe)
    return None


def records(*, exclude_root: Path | None = None) -> list[dict[str, Any]]:
    result = []
    for project in projects():
        if exclude_root is not None and project.is_relative_to(exclude_root.resolve()):
            continue
        result.extend(project_records(project))
    return result


def _artifact(project: Path, run: Path, snapshot: dict) -> str | None:
    ref = snapshot.get('result_ref') or {}
    if ref.get('media_type') not in ('application/json', 'text/markdown'):
        return None
    try:
        path = _inside(run / ref['relative_path'], project)
        if not path.is_relative_to(run.resolve()) or not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() == ref['digest']['value']:
            return str(path)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None
