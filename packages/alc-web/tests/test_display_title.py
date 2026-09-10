import json
from alc_web.presentation import source_title, document_title
from alc_web.store import Store


def test_title_excludes_publication_note_but_preserves_title_content(tmp_path):
    path=tmp_path/'source.html'
    path.write_text('<h1 class="ltx_title_document">A <i>Swift</i> study (III): <a href="https://example.org">results</a><span class="ltx_pubnotes">Facilities: telescope (https://other.org)</span></h1>')
    assert source_title(path)=='A Swift study (III): results'


def test_existing_auto_title_uses_source_but_manual_name_wins(tmp_path):
    store=Store(tmp_path);job=store.create({'title':'url'})
    root=store.job_directory(job['id']);root.mkdir(parents=True)
    (root/'source.html').write_text('<h1>Paper<span class="ltx_pubnotes">Footnote</span></h1>')
    (root/'source.json').write_text(json.dumps({'path':'source.html'}))
    store.update(job['id'],detail={'document_title':'PaperFootnote'})
    assert store.get(job['id'])['display_title']=='Paper'
    store.rename(job['id'],'My paper')
    assert store.get(job['id'])['display_title']=='My paper'


def test_missing_html_heading_keeps_stored_title(tmp_path):
    store=Store(tmp_path);job=store.create({'title':'url'})
    store.update(job['id'],detail={'document_title':'Saved'})
    assert document_title(store,store.get(job['id']))=='Saved'


def test_uploaded_pdf_filename_wins_over_extracted_title(tmp_path):
    store = Store(tmp_path)
    job = store.create({'source_id': 'a' * 32, 'title': 'Chapter 01.PDF'})
    store.update(job['id'], detail={'document_title': 'Extracted paper heading'})
    assert store.get(job['id'])['display_title'] == 'Chapter 01.PDF'
    assert store.summaries()[0]['display_title'] == 'Chapter 01.PDF'
    store.rename(job['id'], 'My chapter')
    assert store.get(job['id'])['display_title'] == 'My chapter'


def test_source_warnings_deduplicate_and_do_not_claim_empty_pages():
    from alc_web.presentation import source_warning_messages
    notice = 'OCR extraction has not been proofread against the original PDF.'
    result = source_warning_messages([notice, notice,
        'PDF page 3, item 27: no readable content was emitted.',
        'PDF page 3: extraction coverage is partial.',
        'PDF page 4: extraction coverage is partial.',
    ])
    assert len(result) == 3
    assert '尚未对照原 PDF' in result[0]
    assert '可能已合并' in result[1] and '也可能存在漏识别' in result[1]
    assert '第 4 页' in result[2]


def test_same_language_notice_requires_known_skip(tmp_path):
    from alc_web.presentation import translation_notice
    store=Store(tmp_path)
    job=store.create({'output':'reader'})
    assert translation_notice(store,job) is None
    store.update(job['id'],detail={'translation_skipped_same_language':True})
    assert '已跳过翻译' in translation_notice(store,store.get(job['id']))


def test_source_warnings_exclude_completion_but_preserve_actual_problems():
    from alc_web.presentation import source_warning_messages

    problem = '部分修订或结构补全未能安全应用，已保留原识别内容；这是执行限制，不是内容歧义。'
    warnings = [
        problem,
        '模型校对已完成，保留 39 项不确定提示，已自动继续。',
        'OCR was checked by a model and has not been reviewed by a person.',
        '模型校对已完成。',
        'OCR 已完成模型校对。',
    ]
    original = list(warnings)
    assert source_warning_messages(warnings) == ['部分 OCR 修订未能应用，已保留原识别结果。展开“查看校对提示”查看具体内容。']
    assert warnings == original
    assert source_warning_messages(warnings[1:]) == []
    assert source_warning_messages(['OCR 已完成，但识别覆盖不完整。']) == ['OCR 已完成，但识别覆盖不完整。']
