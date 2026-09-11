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
    assert a <= b < 60  # Entering translation must not reuse the 90% glossary fraction.
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


def test_companion_phase_label_follows_actual_progress():
    import pathlib
    import shutil
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[3]
    node = shutil.which('node')
    if not node or not (root / 'apps/web/node_modules/typescript').exists():
        pytest.skip('Node and frontend TypeScript dependency required')
    script = r'''
const fs = require('fs'), vm = require('vm');
const ts = require('./apps/web/node_modules/typescript');
const source = fs.readFileSync('apps/web/src/main.tsx', 'utf8');
const helper = source.slice(source.indexOf('function taskPhaseLabel('), source.indexOf('const speeds ='));
const js = ts.transpile(helper, {target: ts.ScriptTarget.ES2022});
const context = {phases: {ocr:'PDF识别', completed:'已交付'}};
vm.createContext(context); vm.runInContext(js, context);
for (const [phase, expected] of [['glossary','整理术语'], ['translation','翻译与审查'], ['guides','编写伴读指南']]) {
 if(context.taskPhaseLabel({phase:'companion',detail:{progress:{phase}}}) !== expected) throw Error(phase);
}
if(context.taskPhaseLabel({phase:'companion', detail:{}}) !== '准备翻译与伴读') throw Error('fallback');
if(context.taskPhaseLabel({phase:'completed',detail:{progress:{phase:'guides'}}}) !== '已交付') throw Error('stale');
'''
    subprocess.run([node, '-e', script], cwd=root, check=True, capture_output=True, text=True)


def test_url_suffix_never_hides_remote_pdf_consent():
    import pathlib
    import shutil
    import subprocess

    root = pathlib.Path(__file__).resolve().parents[3]
    node = shutil.which("node")
    if not node or not (root / "apps/web/node_modules/typescript").exists():
        pytest.skip("Node and frontend TypeScript dependency required")
    script = r'''
const fs = require('fs'), vm = require('vm');
const {createRequire} = require('module');
const localRequire = createRequire(process.cwd() + '/apps/web/package.json');
const ts = localRequire('typescript');
const React = localRequire('react');
const {renderToStaticMarkup} = localRequire('react-dom/server');
let source = fs.readFileSync('apps/web/src/main.tsx', 'utf8')
  .replace('import "./style.css";', '')
  .replaceAll('import.meta.url', JSON.stringify('file:///web/main.tsx'))
  .replace(/createRoot\(document.getElementById\("root"\)!\).render\(<App \/>\);/, '')
  + '\nexport {NewJob};';
const options = {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
 jsx: ts.JsxEmit.React, esModuleInterop: true};
const js = ts.transpile(source, options);
const modules = new Map();
function requireModule(id) {
 if (!id.startsWith('./')) return localRequire(id);
 if (modules.has(id)) return modules.get(id).exports;
 const filename = 'apps/web/src/' + id.slice(2) + '.tsx';
 const context = {exports: {}, require: requireModule};
 modules.set(id, context);
 vm.createContext(context);
 vm.runInContext(ts.transpile(fs.readFileSync(filename, 'utf8'), options), context);
 return context.exports;
}
for (const suffix of ['html', 'htm', 'md', 'markdown', 'tex', 'pdf']) {
 const context = {exports: {}, require: requireModule, URLSearchParams,
   location: {search: '?url=' + encodeURIComponent('https://example.test/paper.' + suffix)}};
 vm.createContext(context); vm.runInContext(js, context);
 const html = renderToStaticMarkup(React.createElement(context.exports.NewJob, {
   settings: {providers: [], ocr: {api_url:'https://mineru.example.test', executable:null}},
   onCreated:()=>{}, onError:()=>{}, onOpenSettings:()=>{}
 }));
 if (!html.includes('我同意将 PDF 上传到此服务进行识别')) throw Error('Hidden consent: ' + suffix);
 if (!html.includes('https://mineru.example.test')) throw Error('Hidden endpoint: ' + suffix);
}
'''
    subprocess.run([node, "-e", script], cwd=root, check=True, capture_output=True, text=True)
