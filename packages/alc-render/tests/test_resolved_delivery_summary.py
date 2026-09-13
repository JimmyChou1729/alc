import shutil
import subprocess
from pathlib import Path

import pytest


def test_summary_uses_current_translation_revisions_without_changing_ledger():
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable')
    source = Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js'
    script = r'''
const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
eval(source.slice(source.indexOf('  function activeDeliveryIssues('),source.indexOf('  function renderDeliverySummary(')));
const state={selected:new Map()};
const translationQualityResolved=f=>!!f.provenance.translation_quality_resolved;
const ledger={issues:[{category:'translation_source_text',scope:'b'}, {category:'translation_review_skipped',scope:'c'}, {category:'resource_unavailable',scope:'b'}]};
const original=JSON.stringify(ledger);
assert.equal(activeDeliveryIssues(ledger).length,3);
state.selected.set('f',{role:'translation',priority:10,anchor:{target_id:'b'},provenance:{translation_quality_resolved:{by:'publication_review'}}});
assert.deepEqual(activeDeliveryIssues(ledger).map(i=>i.scope),['c','b']);
assert.equal(JSON.stringify(ledger),original);
state.selected.get('f').provenance={};assert.equal(activeDeliveryIssues(ledger).length,3);
state.selected.get('f').provenance={translation_quality_resolved:true};state.selected.get('f').role='companion';
assert.equal(activeDeliveryIssues(ledger).length,3);
state.selected.clear();state.payloadVersion='v2';const groupedFragments=()=>new Map([['hydrated',true]]);state.payload={publication:{source_document:{blocks:[{block_id:'b'}]}}};
function loadPayloadForBlockRange(start,end){assert.equal(start,0);assert.equal(end,1);state.selected.set('lazy',{role:'translation',priority:10,anchor:{target_id:'b'},provenance:{translation_quality_resolved:true}});}
assert.equal(activeDeliveryIssues(ledger).length,2,'header hydrates affected history before counting');
assert(state.fragmentGroups.has('hydrated'),'hydrated translations must join rendered source rows');
'''
    result = subprocess.run([node, '-e', script, str(source)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_summary_tracks_recovered_units_glossary_and_provider_history():
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable')
    source = Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js'
    script = r'''
const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
eval(source.slice(source.indexOf('  function activeDeliveryIssues('),source.indexOf('  function renderDeliverySummary(')));
let language='zh-CN'; const targetLanguage=()=>language;
const state={selected:new Map(),payload:{publication:{source_document:{blocks:[]},glossary:[]}}};
const translationQualityResolved=f=>!!(f.provenance||{}).translation_quality_resolved;
const glossaryTranslatedKey=()=> 'target_term';
const glossaryDefinitionHasForbiddenControl=s=>/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(s);
const groupedFragments=()=>new Map();
function loadPayloadForBlockRange(){}
let hydrate=()=>{}; function loadAllPayload(){hydrate();}
const ledger={issues:[{category:'guide_content_recovered',scope:'chapter',evidence:'learning_markdown_invalid'}, {category:'guide_content_normalized',scope:'chapter'}, {category:'guide_content_warning',scope:'unit'}, {category:'unknown_error',scope:'x'}]};
state.selected.set('a',{title:'Good',markdown_body:'Good.',provenance:{chapter_id:'chapter'}});
state.selected.set('b',{title:'Bad',markdown_body:'待核对：此内容未通过自动验收，已保留供编辑。',provenance:{chapter_id:'chapter'}});
state.selected.set('c',{provenance:{unit_id:'unit',recovery_diagnostic:{schema_version:'alc.companion.recovery_diagnostic.v1',issues:['markdown_literal']}}});
assert.equal(activeDeliveryIssues(ledger).length,3);
state.selected.get('a').provenance.content_quality_resolved=true;
assert.equal(activeDeliveryIssues(ledger).length,3,'one sibling edit must not clear chapter');
state.selected.get('b').markdown_body='Audited content';
assert.equal(activeDeliveryIssues(ledger).length,2);
ledger.issues[0].evidence='chapter_guide_review_audit_invalid';
assert.equal(activeDeliveryIssues(ledger).length,3,'missing review must not clear from clean text');
state.selected.get('b').provenance.content_quality_resolved='false';
assert.equal(activeDeliveryIssues(ledger).length,3);
state.selected.get('b').provenance.content_quality_resolved=true;
assert.equal(activeDeliveryIssues(ledger).length,2,'all matching units explicitly resolved');
ledger.issues[0].evidence='unknown_reason';
state.selected.get('a').provenance.content_quality_resolved=false;
assert.equal(activeDeliveryIssues(ledger).length,3,'unknown reasons remain visible');
state.selected.get('a').provenance.content_quality_resolved=true;
ledger.issues[0].evidence='learning_markdown_invalid';
state.selected.get('c').provenance.content_quality_resolved=true;
assert.deepEqual(activeDeliveryIssues(ledger).map(i=>i.category),['unknown_error']);
state.selected.get('c').provenance.content_quality_resolved='false';
assert.equal(activeDeliveryIssues(ledger).length,2,'string false must not resolve warning');
state.selected.get('c').provenance.content_quality_resolved=false;
assert(recoveryDiagnosticText(state.selected.get('c')).includes('格式无法'));
language='en';assert(recoveryDiagnosticText(state.selected.get('c')).includes('could not be formatted'));
assert(!recoveryDiagnosticText(state.selected.get('a')));
const reviewFragment={provenance:{recovery_diagnostic:{schema_version:'alc.companion.recovery_diagnostic.v1',issues:['review_unconfirmed']}}};
assert(recoveryDiagnosticText(reviewFragment).includes('Source review could not be confirmed'));
language='zh-CN';assert.equal(recoveryDiagnosticText(reviewFragment),'原文审核未确认，内容已保留供核对。');
assert(!recoveryDiagnosticText(reviewFragment).includes('位置'));
state.payloadVersion='v2';state.selected.delete('c');hydrate=()=>state.selected.set('c',{provenance:{unit_id:'unit',content_quality_resolved:true}});
assert.deepEqual(activeDeliveryIssues(ledger).map(i=>i.category),['unknown_error'],'hydrate before unit resolution');
const omitted={issues:[{category:'glossary_omitted',scope:'term'}]};
state.payload.publication.glossary=[{entry_id:'other',target_term:'译文',definition:'定义'}];
assert.equal(activeDeliveryIssues(omitted).length,1);
state.payload.publication.glossary[0].entry_id='term';assert.equal(activeDeliveryIssues(omitted).length,0);
state.payload.publication.glossary[0].definition='\x05';assert.equal(activeDeliveryIssues(omitted).length,1);
const provider={issues:[{category:'translation_provider_failure',scope:'window:0',fallback:'source_text_current_window'},{category:'translation_source_text',scope:'block'}]};
assert.equal(activeDeliveryIssues(provider).length,2);
state.selected.set('t',{role:'translation',priority:10,anchor:{target_id:'block'},provenance:{translation_quality_resolved:true,translation_fallback:{kind:'source_text'}}});
assert.equal(activeDeliveryIssues(provider).length,0);
provider.issues[0].fallback='unknown';assert.equal(activeDeliveryIssues(provider).length,1);
'''
    result = subprocess.run([node, '-e', script, str(source)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_summary_hides_term_details_but_keeps_important_counts():
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable')
    source = Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js'
    script = r'''
const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
eval(source.slice(source.indexOf('  function renderDeliverySummary('),source.indexOf('  function deliveryIssueForBlock(')));
let issues=[{category:'glossary_omitted'},{category:'glossary_recovered'}];
const deliveryLedger=()=>({delivery_grade:'degraded'}),activeDeliveryIssues=()=>issues;
const deliverySummaryIsDismissed=()=>false,targetLanguage=()=> 'zh-CN';
const document={body:{dataset:{}}};
const element=(tag,cls,text)=>({text:text||'',children:[],dataset:{},setAttribute(){},addEventListener(){},appendChild(x){this.children.push(x)}});
const iconButton=()=>element('button'),labels=()=>({close:'Close'}),speechIcon=()=>'';
assert.equal(renderDeliverySummary(),null);
issues.push({category:'translation_source_text'},{category:'translation_review_skipped'},{category:'translation_partial_source_text'},{category:'guide_reference_unlinked'});
const panel=renderDeliverySummary();
const text=JSON.stringify(panel);
for(const label of ['保留原文','未完成审查','译文待校对','来源提醒']) assert(text.includes(label));
assert(!text.includes('术语'));assert(!text.includes('其他降级'));
assert.equal(panel.dataset.deliveryIssueCount,'4');
'''
    result = subprocess.run([node, '-e', script, str(source)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
