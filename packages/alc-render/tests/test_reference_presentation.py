"""Original-source references use deterministic visible labels, not model prose."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_reference_locations_render_and_export_without_rewriting_ids():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node unavailable')
    reader = (Path(__file__).parents[1]/'src/alc_render/web_assets/reader.js').read_text()
    script = reader[:reader.rfind('\n  if (document.readyState')] + r'''
    const assert = require('node:assert/strict');
    state.payload = {publication:{reader_profile:{target_language:'zh-CN'},source_document:{
      blocks:[{block_id:'h',kind:'heading',payload:{text:'2.1 Functions'}},
              {block_id:'b',kind:'paragraph'},{block_id:'c',kind:'paragraph'},
              {block_id:'h2',kind:'heading',payload:{text:'2.1 Functions'}}],
      sections:[{title:'2.1 Functions',block_start:0,block_end:3}],
      page_map:[{block_id:'h',page_number:2},{block_id:'b',page_number:2},{block_id:'c',page_number:3}]
    }}};
    const typed={title:'Ignored duplicate title',source:'alc-source:'+JSON.stringify({version:1,anchor:'h',blocks:['h','b','c']})};
    const frozen=JSON.stringify(typed);
    const unordered={...typed,source:"alc-source:"+JSON.stringify({version:1,anchor:"h",blocks:["c","b","h"]})};
    assert.equal(originalReferencePresentation(unordered).targetId,"h");
    assert.deepEqual(originalReferencePresentation(typed),{text:'原文 · 2.1 Functions · PDF 第 2–3 页',targetId:'h'});
    assert.equal(JSON.stringify(typed),frozen);
    const legacy={title:'《2.1 Functions》',source:'供稿原文《2.1 Functions》，第 1–3 部分（已检查）'};
    assert.equal(originalReferencePresentation(legacy).text,'原文 · 2.1 Functions');
    assert.equal(originalReferencePresentation({...legacy,source:'供稿原文，第4–8部分（式 (2.86)–(2.87））'}).text,'原文 · 2.1 Functions · 式 (2.86)–(2.87)');
    assert.equal(originalReferencePresentation({...legacy,source:'supplied original document, parts 1–99'}).text,'原文 · 2.1 Functions');
    assert.equal(originalReferencePresentation({...legacy,source:'supplied original document, batch parts 1–3'}).text,'原文 · 2.1 Functions');
    assert.equal(originalReferencePresentation({title:'Book',source:'Publisher, 2020'}),null);
    assert.equal(originalReferencePresentation({title:'Web',source:'https://example.org/supplied-original-document'}),null);
    assert.equal(originalReferencePresentation({title:'Web',source:'supplied original document',dois:['10.1/x']}),null);
    const incomplete={...typed,source:'alc-source:'+JSON.stringify({version:1,anchor:'h',blocks:['missing']})};
    assert.deepEqual(originalReferencePresentation(incomplete),{text:'原文 · Ignored duplicate title',targetId:''});
    const unknown={...typed,source:'alc-source:{bad'};
    assert.equal(originalReferencePresentation(unknown).text,'原文 · Ignored duplicate title');
    state.selected=new Map([['t',{role:'translation',anchor:{target_id:'h'},markdown_body:'## 函数',deleted:false}]]);
    assert.equal(originalReferencePresentation({title:'函数',source:'供稿原文，第1–3部分'}).text,'原文 · 2.1 Functions');
    state.payload.publication.source_document.sections.push({title:'2.1 Functions',block_start:3,block_end:4});
    assert.equal(originalReferencePresentation(legacy).targetId,'');
    state.payload.publication.source_document.sections.pop();
    state.payload.publication.bibliography=[{...typed,evidence_id:'ref1'}];
    const output=exportBibliographyMarkdown(state.payload.publication.bibliography);
    assert.ok(output.includes('[@ref1]'));
    assert.ok(output.includes('原文 · 2.1 Functions · PDF 第 2–3 页'));
    assert.ok(!output.includes('alc-source:'));
    state.payload.publication.reader_profile.target_language='en';
    assert.equal(originalReferencePresentation(typed).text,'Original · 2.1 Functions · PDF pp. 2–3');
    assert.deepEqual(externalReferencePresentation({source:'https://arxiv.org/html/2504.15222'}),{label:'arXiv:2504.15222',href:'https://arxiv.org/abs/2504.15222'});
    assert.equal(externalReferencePresentation({source:'https://arxiv.org/abs/2503.14738',arxiv_ids:['2503.14738'],dois:['10.1234/test']}).label,'arXiv:2503.14738');
    assert.equal(externalReferencePresentation({source:'https://arxiv.org/pdf/hep-ph/0607187v2.pdf'}).label,'arXiv:hep-ph/0607187v2');
    assert.equal(externalReferencePresentation({source:'https://doi.org/10.1234/example'}).label,'DOI:10.1234/example');
    assert.deepEqual(externalReferencePresentation({source:'https://example.org/paper?x=1'}),{label:'example.org',href:'https://example.org/paper?x=1'});
    assert.equal(externalReferencePresentation({source:'javascript:alert(1)'}).href,'');
    assert.equal(externalReferencePresentation({source:'https://arxiv.org.evil.test/abs/2504.15222'}).label,'arxiv.org.evil.test');
    console.log('reference presentation verified');
}());
'''
    result = subprocess.run([node,'-'],input=script,capture_output=True,text=True)
    assert result.returncode == 0, result.stdout+result.stderr
