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
    spec = job.get('spec', {})
    filename = spec.get('title', '')
    if spec.get('source_id') and Path(filename).suffix.lower() == '.pdf':
        return filename
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


def source_warning_messages(warnings) -> list[str]:
    """Present extraction diagnostics without changing frozen source evidence."""
    import re
    messages, empty_pages, partial_pages = [], set(), set()
    for warning in dict.fromkeys(warnings):
        if warning == '部分修订或结构补全未能安全应用，已保留原识别内容；这是执行限制，不是内容歧义。':
            messages.append('部分 OCR 修订未能应用，已保留原识别结果。展开“查看校对提示”查看具体内容。')
            continue
        if warning == 'no PDF validator was supplied; rich source structure remains authoritative':
            continue
        if warning == 'OCR extraction has not been proofread against the original PDF.':
            messages.append('OCR 已完成，但尚未对照原 PDF 页面校对。此提示不表示识别失败；翻译内容校对也不等同于 OCR 校对。')
            continue
        if warning in {
            'OCR was checked by a model and has not been reviewed by a person.',
            'OCR 已完成模型校对。',
            '模型校对已完成。',
        }:
            continue
        if re.fullmatch(r'模型校对已完成，保留 \d+ 项不确定提示，已自动继续。', warning):
            continue
        model_uncertain = re.fullmatch(r'Model OCR review retained (\d+) unresolved uncertainties\.', warning)
        if model_uncertain:
            messages.append(f'模型校对保留 {model_uncertain[1]} 项不确定提示；已使用可用结果继续处理。')
            continue
        empty = re.fullmatch(r'PDF page (\d+), item \d+: no readable content was emitted\.', warning)
        partial = re.fullmatch(r'PDF page (\d+): extraction coverage is partial\.', warning)
        if empty:
            empty_pages.add(int(empty[1]))
        elif partial:
            partial_pages.add(int(partial[1]))
        else:
            messages.append(warning)
    if empty_pages:
        pages = '、'.join(map(str, sorted(empty_pages)))
        messages.append(f'第 {pages} 页有区域未单独输出文字：可能已合并到其他段落，也可能存在漏识别，需要对照原 PDF 确认。这不表示整页没有识别出来。')
    remaining = partial_pages - empty_pages
    if remaining:
        pages = '、'.join(map(str, sorted(remaining)))
        messages.append(f'第 {pages} 页的识别覆盖可能不完整，请对照原 PDF 核对；已识别内容仍会保留。')
    return list(dict.fromkeys(messages))


def translation_notice(store, job) -> str | None:
    if job['spec'].get('output') != 'reader':
        return None
    if (job.get('detail') or {}).get('translation_skipped_same_language'):
        return '原文与目标语言相同，已跳过翻译。本次生成的是原文 Reader，不会另列一份相同语言的译文。'
    root = store.job_directory(job['id']) / 'project/publication'
    if not (root / '.alc/translate/project.json').is_file():
        return None
    from alc_translate.project import TranslationProject, TranslationProjectError
    from alc_translate.service import TranslationService, TranslationServiceError
    from alc_translate.workflow import LanguageResult
    from ac_jobs.errors import AcJobsError
    try:
        project = TranslationProject.load(root)
        run_id = project.run_id('language')
        if not run_id:
            return None
        result = TranslationService(project.jobs_root).result(run_id)
        if isinstance(result, LanguageResult) and result.mode == 'skipped':
            return '原文与目标语言相同，已跳过翻译。本次生成的是原文 Reader，不会另列一份相同语言的译文。'
    except (OSError, ValueError, TranslationProjectError, TranslationServiceError, AcJobsError):
        return None
    return None
