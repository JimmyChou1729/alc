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
