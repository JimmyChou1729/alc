"""Reference-cost fallback for an active service with stale model cards."""
import pathlib
import shutil
import subprocess

import pytest


def test_gpt6_reference_fallback_is_bounded_and_never_invents_missing_usage():
    root = pathlib.Path(__file__).resolve().parents[3]
    node = shutil.which('node')
    if not node or not (root / 'apps/web/node_modules/typescript').exists():
        pytest.skip('Node and frontend TypeScript dependency required')
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const ts=require('./apps/web/node_modules/typescript');
const context={exports:{}};vm.createContext(context);
vm.runInContext(ts.transpile(fs.readFileSync('apps/web/src/referenceCost.ts','utf8'),
  {target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}),context);
const price=context.exports.currentModelReferenceCost;
const usage={input_tokens:1000000,output_tokens:100000,cached_input_tokens:200000,cache_write_tokens:0,reported_calls:3};
const luna=price('gpt-6-luna',usage),sol=price('gpt-6-sol',usage);
assert.deepEqual(Array.from(luna.amount_range,Number),[.132,.152]);
assert.deepEqual(Array.from(sol.amount_range,Number),[2.64,3.04]);
assert.equal(luna.source,'https://developers.openai.com/api/docs/pricing');
assert.equal(price('gpt-5.6-luna',usage),null);
assert.equal(price('gpt-6-luna',{...usage,output_tokens:null}),null);
assert.equal(price('gpt-6-luna',{...usage,reported_calls:0}),null);
'''
    subprocess.run([node, '-e', script], cwd=root, check=True, capture_output=True, text=True)
