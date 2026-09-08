import json
import pytest
from alc_web.store import Store
from alc_web.metrics import summarize, _cache
from alc_web.timing import percentage


def test_names_and_removal_preserve_frozen_input_and_results(tmp_path):
    store=Store(tmp_path)
    job=store.create({'title':'https://example.test/paper','output':'source'})
    with pytest.raises(ValueError):store.delete(job['id'])
    store.update(job['id'],state='completed',detail={'document_title':'Paper title'})
    frozen=store.get(job['id'])['spec']
    assert store.get(job['id'])['display_title']=='Paper title'
    store.rename(job['id'],'My title')
    assert store.get(job['id'])['spec']==frozen
    assert store.summaries()[0]['display_title']=='My title'
    directory=store.job_directory(job['id']);directory.mkdir(parents=True)
    (directory/'saved').write_text('keep')
    store.delete(job['id'])
    assert not store.summaries()
    assert (directory/'saved').read_text()=='keep'
    with pytest.raises(ValueError):store.control(job['id'],'resume')


def test_progress_never_reuses_glossary_completion_in_translation(tmp_path):
    store=Store(tmp_path);j=store.create({'title':'x','output':'translation','provider':{}});id=j['id']
    store.claim(id)
    store.update(id,phase='glossary',detail={'progress':{'phase':'glossary','completed_units':9,'total_units':10}})
    a=summarize(store,store.get(id))['progress']['percent']
    store.update(id,phase='translation')
    b=summarize(store,store.get(id))['progress']['percent']
    assert a<=b<=30
    store.update(id,detail={'progress':{'phase':'translation','completed_units':8,'total_units':10}})
    c=summarize(store,store.get(id))['progress']['percent']
    store.update(id,detail={'progress':{'phase':'translation','completed_units':3,'total_units':10}})
    _cache.clear()
    assert summarize(store,store.get(id))['progress']['percent']==c


def test_elapsed_excludes_pause_and_survives_rename(tmp_path,monkeypatch):
    clock=[100.0];monkeypatch.setattr('time.time',lambda:clock[0])
    store=Store(tmp_path);id=store.create({'title':'x','output':'source'})['id']
    clock[0]=110;store.claim(id)
    clock[0]=140;store.update(id,state='paused')
    clock[0]=500;assert summarize(store,store.get(id))['progress']['elapsed_seconds']==30
    store.control(id,'resume');store.claim(id)
    clock[0]=520;store.finish(id,{})
    clock[0]=1000;store.rename(id,'new')
    assert summarize(store,store.get(id))['progress']['elapsed_seconds']==50


def test_eta_exists_before_samples_and_companion_setup_is_not_80_percent(tmp_path):
    store=Store(tmp_path);id=store.create({'title':'x','output':'companion'})['id'];store.claim(id)
    assert summarize(store,store.get(id))['progress']['eta_seconds'][1]>0
    assert percentage('companion',{'glossary_ready':False,'total_chapters':1,'completed_units':3,'total_units':8},'companion')<25
