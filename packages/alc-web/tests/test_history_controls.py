"""History query metadata and client-side combinations."""
import pathlib
import shutil
import subprocess

import pytest
from alc_web.presentation import source_type
from alc_web.store import Store


@pytest.mark.parametrize('spec,expected', [
    ({'source_id': 'upload', 'title': 'Paper.PDF'}, 'pdf'),
    ({'source_id': 'upload', 'title': 'notes.md'}, 'markdown'),
    ({'source_id': 'upload', 'title': 'Notes.MARKDOWN'}, 'markdown'),
    ({'source_id': 'upload', 'title': 'notes.txt'}, 'other'),
    ({'source_label': 'doi:10.1234/test', 'source_url': 'https://doi.org/10.1234/test'}, 'doi'),
    ({'source_label': 'https://doi.org/10.1234/test'}, 'https'),
    ({'source_label': 'arXiv:2609.04308v1'}, 'arxiv'),
    ({'source_label': 'astro-ph/0601001'}, 'arxiv'),
    ({'source_label': 'https://arxiv.org/html/2609.04308'}, 'https'),
    ({'source_url': 'https://doi.org/10.1234/test'}, 'doi'),
    ({'source_url': 'https://arxiv.org/html/2609.04308'}, 'arxiv'),
    ({}, 'other'),
])
def test_input_type_uses_submitted_identifier(spec, expected):
    assert source_type(spec) == expected


def test_completion_sort_metadata_survives_later_updates(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('time.time', lambda: clock[0])
    store = Store(tmp_path)
    job_id = store.create({'title': 'paper.pdf', 'source_id': 'upload'})['id']
    assert store.summaries()[0]['completed'] is None
    clock[0] = 200
    store.finish(job_id, {})
    clock[0] = 300
    store.rename(job_id, 'New title')
    store.update(job_id, detail={'note': 'later metadata'})
    summary = store.summaries()[0]
    assert summary['completed'] == 200
    assert summary['created'] == 100
    assert summary['source_type'] == 'pdf'
    assert summary['source_label'] == 'paper.pdf'
    store.update(job_id, state='running')
    assert store.summaries()[0]['completed'] is None


def test_history_search_filter_and_sort_combinations():
    root = pathlib.Path(__file__).resolve().parents[3]
    node = shutil.which('node')
    if not node or not (root / 'apps/web/node_modules/typescript').exists():
        pytest.skip('Node and frontend TypeScript dependency required')
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const ts = require('./apps/web/node_modules/typescript');
const context = {exports:{}};
vm.createContext(context);
vm.runInContext(ts.transpile(fs.readFileSync('apps/web/src/taskHistory.tsx','utf8'),
 {target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}), context);
const jobs = [
 {id:'a',display_title:'Chapter 10',source_label:'Lecture.PDF',source_type:'pdf',created:1,completed:30,spec:{}},
 {id:'b',display_title:'Chapter 2',source_label:'2609.12345',source_type:'arxiv',external:true,created:2,completed:20,spec:{}},
 {id:'c',display_title:'量子场论',source_label:'other.pdf',source_type:'pdf',created:3,completed:null,spec:{title:'Original title'}},
];
const select = (q='', origin='all', type='all', sort='created:desc') =>
 Array.from(context.exports.selectHistory(jobs,q,origin,type,sort), j=>j.id).join(',');
assert.equal(select(' lecture.pdf '),'a');
assert.equal(select('CHAPTER'),'b,a');
assert.equal(select('量子'),'c');
assert.equal(select('original'),'c');
assert.equal(select('', 'web', 'pdf'),'c,a');
assert.equal(select('', 'agent', 'pdf'),'');
assert.equal(select('', 'agent', 'arxiv'),'b');
assert.equal(select('','all','all','created:asc'),'a,b,c');
assert.equal(select('','all','all','completed:asc'),'b,a,c');
assert.equal(select('','all','all','completed:desc'),'a,b,c');
assert.equal(select('chapter','all','all','name:asc'),'b,a');
assert.equal(select('chapter','all','all','name:desc'),'a,b');
assert.equal(jobs.map(j=>j.id).join(','),'a,b,c');
const otherJobs = ['other','unknown','file',undefined,'markdown'].map((source_type,i)=>({...jobs[0],id:String(i),source_type}));
assert.equal(context.exports.selectHistory(otherJobs,'','all','other','created:asc').length,4);
assert.equal(context.exports.selectHistory(otherJobs,'','all','markdown','created:asc').length,1);
'''
    subprocess.run([node, '-e', script], cwd=root, check=True, capture_output=True, text=True)


def test_history_does_not_drop_older_searchable_jobs(tmp_path):
    store = Store(tmp_path)
    with store.connect() as db:
        db.executemany(
            'INSERT INTO jobs(id,state,created,updated,spec) VALUES(?,?,?,?,?)',
            [(f'{i:032x}', 'queued', i, i, '{"title":"paper.pdf","source_id":"upload"}') for i in range(501)],
        )
    summaries = store.summaries()
    assert len(summaries) == 501
    assert summaries[-1]['id'] == '0' * 32
