"""Shared local OCR defaults without inheriting remote upload destinations."""
from pathlib import Path
import json
import os
import tempfile
from . import catalog_root


def default_config_path() -> Path:
    return catalog_root() / 'mineru.json'


def effective_config_path(project: Path) -> Path:
    specific = Path(project) / '.ac/mineru.json'
    if specific.exists():
        return specific
    default = default_config_path()
    if default.is_file():
        value = json.loads(default.read_text())
        if value.get('executable') and not value.get('api_url'):
            return default
    return specific


def remember_local_config(value: dict | None, *, overwrite: bool = True) -> bool:
    if not value or value.get('api_url') or not value.get('executable'):
        return False
    executable = Path(value['executable']).expanduser()
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        return False
    path = default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps({'executable': str(executable), 'language': value.get('language', 'en'),
                          'api_url': None, 'token_env': None}).encode()
    fd, name = tempfile.mkstemp(prefix='.mineru-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        if overwrite:
            os.replace(name, path)
        else:
            try:
                os.link(name, path)
            except FileExistsError:
                return False
    finally:
        Path(name).unlink(missing_ok=True)
    return True
