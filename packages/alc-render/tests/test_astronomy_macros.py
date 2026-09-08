"""Exercise the bundled KaTeX renderer with the Reader's actual macro table."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_angular_units_render_with_decimal_and_prime():
    node=shutil.which('node')
    if node is None:
        pytest.skip('Node is required for bundled KaTeX verification')
    assets=Path(__file__).parents[1]/'src/alc_render/web_assets'
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1]+'/reader.js','utf8');
const code=source.match(/function katexSemanticMacros\(\) \{[\s\S]*?\n  \}/)[0];
const macros=vm.runInNewContext(code+';katexSemanticMacros()');
const scope={}; vm.runInNewContext(fs.readFileSync(process.argv[1]+'/katex/katex.min.js','utf8'),scope); const katex=scope.katex;
for(const tex of ['4\\arcsec','0\\farcs8','2\\arcmin','0\\farcm5']) {
 const html=katex.renderToString(tex,{macros,throwOnError:true});
 assert(!html.includes('katex-error'));
 assert(html.includes('′'));
 if(tex.startsWith('0')) assert(html.includes('.'));
}
'''
    result=subprocess.run([node,'-e',script,str(assets)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
