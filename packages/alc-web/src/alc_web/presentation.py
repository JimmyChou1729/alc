"""Display metadata is separate from the frozen model request."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=128)
def _title(path: str, stamp: int) -> str:
    doc = json.loads(Path(path).read_text())
    for block in doc.get('blocks', []):
        if block.get('kind') == 'heading':
            return str(block.get('payload', {}).get('text', ''))[:500]
    return ''


@lru_cache(maxsize=128)
def _html_title(path: str, stamp: int) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(Path(path).read_text(), "html.parser")
    heading = soup.select_one("h1.ltx_title_document") or soup.find("h1")
    if heading is None:
        return ""
    for note in heading.select(".ltx_pubnotes, .ltx_note, [role='doc-noteref']"):
        note.decompose()
    return " ".join(heading.get_text().split())[:500]


def source_title(path: Path) -> str:
    if path.suffix.lower() not in {".html", ".htm"}:
        return ""
    try:
        return _html_title(str(path), path.stat().st_mtime_ns)
    except (OSError, UnicodeError, ValueError):
        return ""


def document_title(store, job) -> str:
    root = store.job_directory(job['id']).resolve()
    try:
        info = json.loads((root / 'source.json').read_text())
        source = (root / info['path']).resolve()
        if source.is_relative_to(root):
            cleaned = source_title(source)
            if cleaned:
                return cleaned
    except (OSError, ValueError, KeyError, TypeError):
        pass
    title = job.get('detail', {}).get('document_title')
    if title:
        return title
    path = store.job_directory(job['id']) / 'project/publication/rich-source.json'
    try:
        if path.resolve().is_relative_to(store.job_directory(job['id']).resolve()):
            return _title(str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError):
        pass
    return ''
