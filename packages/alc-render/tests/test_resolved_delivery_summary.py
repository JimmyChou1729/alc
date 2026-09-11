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
