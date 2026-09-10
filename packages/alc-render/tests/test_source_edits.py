import subprocess
import shutil
from pathlib import Path
import pytest


def test_source_revisions_render_export_and_restore_independently():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert = require('node:assert/strict');
    assert.deepEqual(sourceDefaultAppearance('source',null),{foreground:'inherit',background:'transparent'});
    const custom={foreground:'#112233',background:'#ddeeff'};
    assert.deepEqual(sourceDefaultAppearance('source',custom),custom);
    const original = {block_id:'b1',kind:'paragraph',payload:{text:'Original OCR'}};
    exportOriginalSourceBlockMarkdown = function(block) { return block.payload.text; };
    rewriteMarkdownResourceTargets = function(text) { return text; };
    function revision(id, operation, body, deleted=false) {
      return {fragment_id:id, role:'source', deleted, priority:50, markdown_body:body,
        anchor:{kind:'block',target_id:'b1'}, provenance:{source_edit:{schema_version:'alc.render.source_edit.v1',operation}}};
    }
    const replacement=revision('r','replace','Corrected');
    const insertion=revision('i','insert','Extra paragraph');
    const translation={fragment_id:'t',role:'translation',markdown_body:'译文不变',anchor:{kind:'block',target_id:'b1'}};
    state.selected=new Map([['r',replacement],['i',insertion],['t',translation]]);
    assert.equal(exportSourceBlockMarkdown(original,{},new Map()),'Corrected\n\nExtra paragraph');
    assert.equal(original.payload.text,'Original OCR');
    assert.equal(translation.markdown_body,'译文不变');
    replacement.deleted=true;
    assert.equal(exportSourceBlockMarkdown(original,{},new Map()),'Extra paragraph');
    insertion.deleted=true;
    assert.equal(exportSourceBlockMarkdown(original,{},new Map()),'');
    replacement.deleted=false;
    assert.equal(exportSourceBlockMarkdown(original,{},new Map()),'Corrected');
    state.selected.delete('r');
    assert.equal(exportSourceBlockMarkdown(original,{},new Map()),'Original OCR');
    state.selected.set('r',replacement);
    state.payload={publication:{source_document:{blocks:[original]},reader_profile:{}}};
    state.fragmentGroups=new Map([['b1',[replacement]]]);
    loadAllPayload=function(){};
    isPdfPageMarkerBlock=function(){return false;};
    isStandaloneHtmlCommentBlock=function(){return false;};
    fragmentSpeechText=function(fragment){return fragment.markdown_body;};
    originalSourceSpeechText=function(block){return block.payload.text;};
    assert.deepEqual(buildSpeechQueue(new Set(['source'])).map(item=>item.text),['Corrected']);
    replacement.deleted=true;
    assert.deepEqual(buildSpeechQueue(new Set(['source'])),[]);
    replacement.deleted=false;
    state.speechSupported=true;
    state.speechVoices=[{}];
    refreshSpeechVoices=function(){};
    speechSegmentText=function(segment){return segment.text;};
    let spoken=-1;
    speakSpeechIndex=function(index){spoken=index;};
    playSpeechFromCard('source','b1','r');
    assert.equal(spoken,0);
    const old={...replacement,semantic_digest:'old'};
    const deleted1={...replacement,deleted:true,semantic_digest:'d1',parent_semantic_digest:'old'};
    const deleted2={...replacement,deleted:true,semantic_digest:'d2',parent_semantic_digest:'d1'};
    state.revisions=new Map([['r',[old,deleted1,deleted2]]]);
    assert.equal(earlierVisibleSourceRevision(deleted2).semantic_digest,'old');
    state.selected.set('t',{...translation,priority:50,deleted:true});
    assert.equal(translationWasDeleted('b1'),true);
    state.selected.set('r2',revision('r2','replace','conflict'));
    assert.throws(()=>sourceReplacement('b1'),/Conflicting/);
    console.log('source revision projection passed');
}());
'''
    result = subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_first_delete_cancel_failure_and_newer_storage_leave_no_hidden_draft():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    const block={block_id:'b1'};
    let saved=0, connected=0, latest=null;
    sourceReplacement=function(){return latest;};
    prepareForDraftSwitch=function(){return !state.activeDraft;};
    labels=function(){return {sourceDeleteConfirm:'Confirm',sourceChangedBeforeDelete:'Changed'};};
    setStatus=function(){};
    confirmReaderAction=async function(){return true;};
    prepareSourceDraft=function(){state.activeDraft={sourceEdit:{operation:'replace'}};return true;};
    connectDirectory=async function(){assert.equal(state.activeDraft,null);connected++;return false;};
    persistEditor=async function(){saved++;};
    (async function(){
      await removeReaderContent(block,null);
      assert.equal(connected,1);assert.equal(saved,0);assert.equal(state.activeDraft,null);
      connectDirectory=async function(){assert.equal(state.activeDraft,null);state.directory={};return true;};
      // Save failures may return without throwing; both paths must clean up.
      await removeReaderContent(block,null);
      assert.equal(saved,1);assert.equal(state.activeDraft,null);
      assert.equal(state.editorAnchor,null);
      persistEditor=async function(){throw new Error('write failed');};
      await assert.rejects(removeReaderContent(block,null),/write failed/);
      assert.equal(state.activeDraft,null);
      state.directory=null;
      connectDirectory=async function(){state.directory={};latest={semantic_digest:'new'};return true;};
      await removeReaderContent(block,null);
      assert.equal(state.activeDraft,null);assert.equal(saved,1);
      latest=null;
      persistEditor=async function(){saved++;state.activeDraft=null;};
      await removeReaderContent(block,null);
      assert.equal(saved,2);assert.equal(state.activeDraft,null);
      console.log('direct delete lifecycle passed');
    }()).catch(error=>{console.error(error);process.exitCode=1;});
}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_source_delete_writes_verified_revision_and_reloads():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    globalThis.window=globalThis;
    globalThis.document={getElementById:()=>null,querySelectorAll:()=>[]};
    const block={block_id:'b1',kind:'paragraph',ordinal:0,locator:{line_start:1},payload:{text:'OCR'}};
    const source={source_format:'markdown',media_type:'text/markdown',artifact_digest:'a'.repeat(64),rich_document_digest:'b'.repeat(64),size:3};
    state.payload={source_identity:source,block_fingerprints:{b1:'c'.repeat(64)},resources:[],publication:{source_document:{blocks:[block],sections:[]},reader_profile:{source_language:'en',target_language:'zh-CN'},bibliography:[],glossary:[]}};
    state.sourceIdentityJson=stableStringify(source);
    let status='';setStatus=function(text){status=text;};
    confirmReaderAction=async()=>true;
    sourceEditorMarkdown=()=> 'OCR';
    refreshFragmentGroup=()=>{};refreshChunkForAnchor=()=>{};syncVisibilityRoles=()=>{};
    const files=new Map();
    const folder={getFileHandle:async(name,options)=>{
      if(!files.has(name)){
        if(!options||!options.create)throw Object.assign(new Error('missing'),{name:'NotFoundError'});
        files.set(name,'');
      }
      return {getFile:async()=>({size:files.get(name).length,text:async()=>files.get(name)}),createWritable:async()=>({write:async(text)=>files.set(name,text),close:async()=>{}})};
    }};
    connectDirectory=async()=>{assert.equal(state.activeDraft,null);state.directory={getDirectoryHandle:async()=>folder};return true;};
    (async()=>{
      await removeReaderContent(block,null);
      assert.equal(files.size,1,status);
      assert.equal(state.activeDraft,null);
      assert.equal(state.saveInProgress,false);
      const [filename,encoded]=Array.from(files)[0];
      const revision=await parseRevisionFile(encoded,filename);
      assert.equal(revision.deleted,true);
      assert.equal(revision.role,'source');
      assert.equal(revision.provenance.source_edit.operation,'replace');
      state.selected=new Map([[revision.fragment_id,revision]]);
      assert.equal(sourceReplacement('b1').deleted,true);
      assert.equal(exportSourceBlockMarkdown(block,{},new Map()),'');
      assert.equal(block.payload.text,'OCR');
      assert.equal(deletedContentEntries().length,1);
      assert.equal(await restoreDeletedContent(revision),true);
      assert.equal(files.size,2);
      assert.equal(deletedContentEntries().length,0);
      assert.equal(sourceReplacement('b1').markdown_body,'OCR');
      updateGlossaryMentionProvenance=()=>{};
      const translation=metadataOnly(sourceReplacement('b1'));
      translation.fragment_id='translation-test';translation.role='translation';
      translation.provenance={producer:'test'};translation.revision=1;
      translation.parent_semantic_digest=null;
      const translated={...translation,markdown_body:'译文内容',semantic_digest:await semanticDigest(translation,'译文内容')};
      state.activeFragmentIds.add(translated.fragment_id);
      addRevision(translated);resolveOne(translated.fragment_id);
      await removeReaderContent(null,translated);
      const removed=state.selected.get(translated.fragment_id);
      assert.equal(removed.deleted,true,status);
      assert.equal(await restoreDeletedContent(removed),true,status);
      assert.equal(state.selected.get(translated.fragment_id).markdown_body,'译文内容');

      assert.equal(state.activeDraft,null);
      const savedSource=sourceReplacement('b1');
      const fileCount=files.size;
      state.directory=null;
      state.revisions=new Map();state.selected=new Map();state.revisionDigests=new Map();
      assert.equal(prepareSourceDraft(block,false),true);
      state.activeDraft.markdown_body='New disconnected correction';
      const pendingDraft=state.activeDraft;
      // Load the entire lineage, as a real directory connection would.
      const savedFiles=Array.from(files.entries());
      connectDirectory=async()=>{
        state.directory={getDirectoryHandle:async()=>folder};
        for (const [name,text] of savedFiles) addRevision(await parseRevisionFile(text,name));
        resolveAll();
        return true;
      };
      await persistEditor(null,false);
      assert.equal(files.size,fileCount,'stale initial save wrote a second root');
      assert.equal(state.activeDraft,pendingDraft,'stale initial save discarded the draft');
      assert.equal(state.activeDraft.markdown_body,'New disconnected correction');
      assert.equal(sourceReplacement('b1').semantic_digest,savedSource.semantic_digest);
      assert.equal(status,labels().historyChanged);
      await persistEditor(null,false);
      assert.equal(files.size,fileCount,'retry bypassed the stale initial-base guard');
    })().catch(error=>{console.error(error);process.exitCode=1;});
}());
'''
    result = subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_translation_only_fallback_preserves_source_list_ownership():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    rewriteMarkdownResourceTargets=text=>text;
    const ordered={ordered:true,item_index:1,continuation:false};
    const bullet={ordered:false,item_index:0,continuation:false};
    const blocks=[
      {block_id:'ordered',kind:'paragraph',payload:{text:'Ordered'},list_path:[ordered]},
      {block_id:'nested',kind:'paragraph',payload:{text:'Nested'},list_path:[ordered,bullet]},
      {block_id:'continued',kind:'paragraph',payload:{text:'Continuation'},list_path:[ordered,{...bullet,continuation:true}]}
    ];
    state.payload={publication:{source_document:{blocks},reader_profile:{},glossary:[],bibliography:[]}};
    state.selected=new Map([['source-correction',{
      fragment_id:'source-correction',role:'source',priority:50,markdown_body:'Corrected source',
      anchor:{kind:'block',target_id:'ordered'},provenance:{source_edit:{schema_version:'alc.render.source_edit.v1',operation:'replace'}}
    }]]);
    const result=buildCompleteMarkdown(new Map(),new Set(['translation']));
    assert.equal(result.markdown,'2. Ordered\n\n    - Nested\n\n        Continuation\n');
    assert.deepEqual(result.selectedRevisionDigests,[]);
}());
'''
    result = subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_connection_failure_retains_stage_and_releases_busy_state():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    globalThis.window={showDirectoryPicker:async()=>({requestPermission:async()=>{throw new Error('permission error');}})};
    labels=()=>({storageSelect:'select',storagePermission:'permission',storageFailure:' failed: '});
    let message;
    setStatus=(...args)=>{message=args;};updateDirectoryControl=()=>{};
    (async()=>{
      assert.equal(await connectDirectory(),false);
      assert.deepEqual(message,['permission failed: permission error','error',true]);
      assert.equal(state.directorySelectionInProgress,false);
      assert.equal(state.directory,null);
    })().catch(error=>{console.error(error);process.exitCode=1;});
}());
'''
    result = subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_unsaved_source_inline_draft_and_deleted_toolbar_visibility():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    const term={closest:selector=>selector.includes('.glossary-term')?term:null};
    state.readerPreferences.glossaryDisplay='hover';
    assert.ok(interactiveFragmentTarget(term));
    state.readerPreferences.glossaryDisplay='none';
    assert.equal(interactiveFragmentTarget(term),false);
    const link={closest:selector=>selector.includes('a,')?link:null};
    assert.ok(interactiveFragmentTarget(link));
    const button={hidden:false};
    globalThis.document={getElementById:()=>button};
    state.readerSettingsReady=true;
    syncDeletedContentControl();assert.equal(button.hidden,true);
    state.selected.set('deleted',{deleted:true});
    syncDeletedContentControl();assert.equal(button.hidden,false);
    state.selected.set('deleted',{deleted:false});
    syncDeletedContentControl();assert.equal(button.hidden,true);
    state.payload={publication:{reader_profile:{source_language:'en'}}};
    state.activeDraft={base:null,inlineFragmentId:'source-draft-heading',anchor:{kind:'block',target_id:'heading'},role:'source',priority:50,markdown_body:'## Heading',sourceEdit:{schema_version:'alc.render.source_edit.v1',operation:'replace'}};
    assert.equal(sourceInlineDraft({block_id:'heading'}).markdown_body,'## Heading');
    assert.equal(sourceInlineDraft({block_id:'other'}),null);
    assert.equal(state.activeDraft.base,null);
    state.activeDraft=null;
    anchorBlock=block=>({block_id:block.block_id});
    sourceEditorMarkdown=()=>"## 1.1 PRELUDE";
    appearanceForGroup=()=>null;
    assert.equal(prepareSourceDraft({block_id:'heading'},false),true);
    state.activeDraft.inlineFragmentId='source-draft-heading';
    assert.equal(activeDraftHasChanges(),false);
    state.activeDraft.markdown_body+=' changed';
    assert.equal(activeDraftHasChanges(),true);
    state.activeDraft.markdown_body='## 1.1 PRELUDE';
    assert.equal(activeDraftHasChanges(),false);
    globalThis.window={};
    const card={contains:()=>false};
    document.querySelector=selector=>selector.includes('source-draft-heading')?card:null;
    document.getElementById=()=>null;
    assert.equal(activeInlineDraftCard(),card);
    let cancelled=false,guarded=false;
    cancelActiveDraft=()=>{cancelled=true;};
    openUnsavedDialog=()=>{guarded=true;};
    const event={target:{},type:'pointerdown',preventDefault(){},stopImmediatePropagation(){}};
    attemptInlineDraftExit(event);
    assert.equal(cancelled,true);assert.equal(guarded,false);
    cancelled=false;state.activeDraft.markdown_body+=' changed';
    attemptInlineDraftExit(event);
    assert.equal(cancelled,false);assert.equal(guarded,true);

}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_term_display_modes_and_hover_bridge():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js=(Path(__file__).parents[1]/'src/alc_render/web_assets/reader.js').read_text()
    script=js[:js.rfind('\n  if (document.readyState')]+r'''
    const assert=require('node:assert/strict');
    const events={},tips={},windowEvents={};let pending=null;
    const tooltip={hidden:true,style:{},classList:{toggle(){}},replaceChildren(){},contains:x=>x===tooltip,getBoundingClientRect:()=>({height:60,width:200,top:38,bottom:98,left:50,right:250}),addEventListener:(n,f)=>tips[n]=f};
    globalThis.document={getElementById:()=>tooltip,documentElement:{clientWidth:800},addEventListener:(n,f)=>events[n]=f};
    globalThis.window={innerHeight:800,addEventListener:(n,f)=>windowEvents[n]=f,setTimeout:f=>{pending=f;return 1;},clearTimeout:()=>{pending=null;}};
    const term={dataset:{glossaryTooltip:'definition'},closest:()=>term,matches:()=>true,contains:x=>x===term,getBoundingClientRect:()=>({bottom:30,top:10,left:50,right:150})};
    setupTooltip();
    state.readerPreferences.glossaryDisplay='hover';
    events.mouseover({target:term});assert.equal(tooltip.hidden,false);
    assert.equal(tooltip.style.pointerEvents,'auto');
    events.mouseout({target:term,relatedTarget:null});assert.equal(typeof pending,'function');
    const staleClose=pending;
    tips.mouseenter();assert.equal(pending,null);assert.equal(tooltip.hidden,false);
    // Selecting panel text can blur the originating term after pointer entry.
    events.focusout({target:term,relatedTarget:null});
    assert.equal(pending,null);
    staleClose();assert.equal(tooltip.hidden,false);
    tips.mouseleave();assert.equal(typeof pending,'function');
    pending();assert.equal(tooltip.hidden,true);
    events.keydown({key:'Escape'});
    // First hover remains open through viewport/background refresh callbacks.
    events.mouseover({target:term,clientX:70,clientY:20});
    windowEvents.scroll();windowEvents.resize();state.closeTooltipIfOutside();
    assert.equal(tooltip.hidden,false);
    events.pointermove({target:tooltip,clientX:80,clientY:60});
    events.focusout({target:term,relatedTarget:null});windowEvents.scroll();
    assert.equal(tooltip.hidden,false);
    events.pointermove({target:{},clientX:400,clientY:400});
    pending();assert.equal(tooltip.hidden,true);
    state.readerPreferences.glossaryDisplay='click';
    events.mouseover({target:term});assert.equal(tooltip.hidden,true);
    events.click({target:term});assert.equal(tooltip.hidden,false);
    events.mouseout({target:term,relatedTarget:null});assert.equal(pending,null);
    events.keydown({key:'Escape'});
    state.readerPreferences.glossaryDisplay='none';
    events.mouseover({target:term});events.click({target:term});events.focusin({target:term});
    assert.equal(tooltip.hidden,true);
}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_deleted_source_has_no_actions_or_edit_listeners():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    element=(tag,cls)=>({tag,cls,dataset:{},children:[],events:[],
      classList:{add(){},toggle(){}},appendChild(x){this.children.push(x);},
      addEventListener(x,callback){this.events.push(x);this[x]=callback;}});
    globalThis.document={documentElement:{lang:'en'}};
    state.payload={publication:{source_document:{},reader_profile:{}}};
    state.sourceStructuralIndex={blockIds:new Set()};
    sourcePresentationBlock=()=>null;
    sourceBibliographyItemIndexes=()=>new Set();
    sourceReplacement=()=>({deleted:true});
    sourceInlineDraft=()=>null;
    listPathEntries=()=>[];
    let additions=[];
    sourceInsertions=()=>additions;
    renderFragment=()=>element('section','insertion');
    renderSourceNoteGroup=()=>null;
    markDeliveryState=()=>{};
    syncSourceBibliographyAlignment=()=>{};
    sourceActions=()=>{throw Error('Deleted original must not have actions');};
    const row=renderSourceRow({block_id:'b',kind:'paragraph'},[]);
    const source=row.children[0].children[0];
    assert.deepEqual(source.events,[]);
    assert.equal(source.children.length,1);
    assert.equal(source.children[0].cls,'alc-source-deleted');
    parallelGroups=()=>[{id:'added',source:{role:'source'}}];
    renderParallelGroup=()=>element('div','paired-row');
    const withAddition=renderSourceRow({block_id:'b',kind:'paragraph'},[]);
    assert.equal(withAddition.children[1].cls,'paired-row');
    assert.equal(withAddition.children[0].children[0].children.length,1);
    sourceReplacement=()=>null;sourceActions=()=>element('div','actions');
    renderSourceBlock=()=>element('p','body');setupTouchCardActions=()=>{};
    const normal=renderSourceRow({block_id:'b',kind:'paragraph'},[]).children[0].children[0];
    let edits=0;editSourceBlock=()=>edits++;
    const term={closest:selector=>selector.includes('.glossary-term')?term:null};
    const event={target:term,preventDefault(){},stopPropagation(){}};
    state.readerPreferences.editActivation='double';state.readerPreferences.glossaryDisplay='hover';
    normal.click(event);assert.equal(edits,0);
    normal.dblclick(event);assert.equal(edits,1);
    state.readerPreferences.glossaryDisplay='click';
    normal.dblclick(event);assert.equal(edits,2);
    event.target={closest:()=>({})};
    normal.dblclick(event);assert.equal(edits,2);

}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_figure_natural_size_handles_loaded_and_loading_copies():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    function image(width,dataset={}) {
      return {naturalWidth:width,dataset,style:{},addEventListener(name,callback){this[name]=callback;}};
    }
    const cached=image(615);
    setupFigurePanelNaturalSize(cached);
    assert.equal(cached.style.maxWidth,'615px');
    const copy=image(0);
    setupFigurePanelNaturalSize(copy);
    assert.equal(copy.style.maxWidth,undefined);
    copy.naturalWidth=615;copy.load();
    assert.deepEqual(copy.style,cached.style);
    const sized=image(615,{panelDisplayWidth:'400'});
    sized.style.maxWidth='400px';
    setupFigurePanelNaturalSize(sized);sized.load();
    assert.equal(sized.style.maxWidth,'400px');
}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_contents_titles_follow_saved_source_and_visible_translation():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    element=()=>({set innerHTML(value){this.firstElementChild={tagName:value.startsWith('#')?'H2':'P',textContent:value};}});
    state.md={render:x=>x};projectGlossaryMarkdown=x=>x;
    fragmentTargetId=x=>x.anchor.target_id;
    const source={fragment_id:'s',role:'source',priority:50,anchor:{target_id:'b'},markdown_body:'## New source'};
    const translation={fragment_id:'t',role:'translation',priority:10,anchor:{target_id:'b'},markdown_body:'## 新译文'};
    state.payload={selected_heading_fragments:[{...source,target_id:'b',markdown_body:'## Stale source'}]};
    state.selected=new Map([['s',source],['t',translation]]);
    state.sourceVisible=true;
    assert.equal(visibleHeadingForBlock('b').textContent,'## New source');
    source.markdown_body='## Restored source';
    assert.equal(visibleHeadingForBlock('b').textContent,'## Restored source');
    state.activeDraft={markdown_body:'## Unsaved title'};
    assert.equal(visibleHeadingForBlock('b').textContent,'## Restored source');
    state.sourceVisible=false;
    assert.equal(visibleHeadingForBlock('b').textContent,'## 新译文');
    state.hiddenRoles.add('translation');
    assert.equal(visibleHeadingForBlock('b'),null);
    state.sourceVisible=true;source.deleted=true;
    assert.equal(visibleHeadingForBlock('b'),null);
    state.selected.delete('s');state.revisions.set('s',[source]);
    assert.equal(visibleHeadingForBlock('b'),null);
    state.revisions.clear();
    assert.equal(visibleHeadingForBlock('b').textContent,'## Stale source');
    state.payload.publication={outline:[{anchor_block_id:"b"}]};
    let updates=0;
    state.readerShellReady=true;updateFragmentGroup=()=>{};syncPromotedTitleSurface=()=>{};
    updateContentsTitles=()=>updates++;
    refreshFragmentGroup('s',{target_id:'b'});
    assert.equal(updates,1);
}());
'''
    result = subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_parallel_additions_bind_by_id_not_position_and_survive_deletion():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    fragmentTargetId=x=>x.anchor.target_id;
    function revision(id,role,pair,priority=110) {
      return {fragment_id:id,role,priority,markdown_body:id,anchor:{kind:'block',target_id:'b'},provenance:{
        ...(role==='source'?{source_edit:{schema_version:'alc.render.source_edit.v1',operation:'insert'}}:{}),
        ...(pair?{parallel_edit:{schema_version:'alc.render.parallel_edit.v1',pair_id:pair}}:{})}};
    }
    const a=revision('a','source','pair-a'), b=revision('b','source','pair-b');
    const translated=revision('t','translation','pair-a',115);
    const unrelated=revision('legacy','translation',null);
    state.selected=new Map([['b',b],['t',translated],['legacy',unrelated],['a',a]]);
    let rows=parallelGroups('b');
    assert.equal(rows.length,3);
    assert.equal(rows.find(x=>x.id==='pair-a').translation.fragment_id,'t');
    assert.equal(rows.find(x=>x.id==='pair-b').translation,undefined);
    a.deleted=true;
    assert.equal(parallelGroups('b').find(x=>x.id==='pair-a').translation.fragment_id,'t');
    translated.deleted=true;
    assert.equal(parallelGroups('b').some(x=>x.id==='pair-a'),false);
    a.deleted=false;
    assert.ok(parallelGroups('b').find(x=>x.id==='pair-a'));
    state.activeDraft={base:a,inlineFragmentId:'a',anchor:a.anchor};
    assert.equal(sourceInlineDraft({block_id:'b'}),null);
    const duplicate=revision('duplicate','source','pair-a');
    state.selected.set('duplicate',duplicate);
    assert.throws(()=>parallelGroups('b'),/Conflicting/);
    assert.equal(draftFromFragment(a).parallelPairId,'pair-a');
}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_source_addition_speech_starts_at_clicked_fragment_and_highlights_it():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    const block={block_id:'b',kind:'paragraph',payload:{text:'Original'}};
    state.payload={publication:{source_document:{blocks:[block]},reader_profile:{}}};
    loadAllPayload=()=>{};fragmentTargetId=x=>x.anchor.target_id;
    originalSourceSpeechText=()=> 'Original';fragmentSpeechText=x=>x.markdown_body;
    function addition(id,priority,body) {return {fragment_id:id,role:'source',priority,
      anchor:{kind:'block',target_id:'b'},markdown_body:body,provenance:{source_edit:{schema_version:'alc.render.source_edit.v1',operation:'insert'}}};}
    const first=addition('first',110,'23423'),second=addition('second',112,'新增一段原文');
    state.selected=new Map([['first',first],['second',second]]);
    state.fragmentGroups=new Map([['b',[first,second]]]);
    state.speechSupported=true;state.speechVoices=[{}];refreshSpeechVoices=()=>{};
    let spoken=-1;speakSpeechIndex=x=>spoken=x;
    playSpeechFromCard('source','b','second');
    assert.equal(spoken,2);
    assert.deepEqual(state.speechQueue.map(speechSegmentText),['Original','23423','新增一段原文']);
    state.chunkByTargetId=new Map();globalThis.window={};
    let selector='';globalThis.document={getElementById:()=>({querySelector:s=>{selector=s;return {};}})};
    speechSegmentNode(state.speechQueue[spoken]);
    assert.ok(selector.includes('data-fragment-id="second"'));
    first.deleted=true;
    assert.deepEqual(buildSpeechQueue(new Set(['source'])).map(speechSegmentText),['Original','新增一段原文']);
}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_deleted_content_order_is_newest_then_document_position():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    function item(id,role,ordinal,provenance={}) { return {fragment_id:id,role,deleted:true,priority:110,provenance,
      anchor:{target_id:'b'+ordinal,related_blocks:[{block_id:'b'+ordinal,ordinal}]}}; }
    const values=[item('late-source','source',9),item('early-target','translation',1),
      item('early-source','source',1),item('newest','translation',99,{deleted_at:'2026-09-10T10:00:00Z'}),
      item('older','source',0,{last_editor:'alc-render-browser',edited_at:'2026-09-09T10:00:00Z'}),
      item('bad','source',10,{deleted_at:'bad'})];
    const expected=['newest','older','early-source','early-target','late-source','bad'];
    state.selected=new Map(values.map(x=>[x.fragment_id,x]));
    assert.deepEqual(deletedContentEntries().map(x=>x.fragment_id),expected);
    state.selected=new Map(values.slice().reverse().map(x=>[x.fragment_id,x]));
    assert.deepEqual(deletedContentEntries().map(x=>x.fragment_id),expected);
    const inherited=item('inherited','source',2,{last_editor:'alc-render-browser',edited_at:'2026-09-08T10:00:00Z'});
    inherited.parent_semantic_digest='parent';
    state.revisions.set('inherited',[{semantic_digest:'parent',provenance:{edited_at:inherited.provenance.edited_at}}]);
    assert.equal(deletionTimestamp(inherited),null);
    values[3].deleted=false;
    assert.equal(deletedContentEntries()[0].fragment_id,'older');
}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_restoring_deleted_content_closes_without_reopening_dialog():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    js = (Path(__file__).parents[1] / 'src/alc_render/web_assets/reader.js').read_text()
    script = js[:js.rfind('\n  if (document.readyState')] + r'''
    const assert=require('node:assert/strict');
    let opened=0,closed=0,restored=0,restoreButton;
    element=(tag,cls,text)=>({children:[],setAttribute(){},replaceChildren(){},appendChild(x){this.children.push(x);},
      addEventListener(event,callback){if(text==='Restore')restoreButton=callback;},
      showModal(){opened++;this.open=true;},close(){closed++;this.open=false;}});
    iconButton=()=>element('button');
    globalThis.document={getElementById:()=>null,body:{appendChild(){}}};
    prepareForDraftSwitch=()=>true;loadAllPayload=()=>{};
    labels=()=>({deletedContents:'Deleted',restoreContent:'Restore'});
    deletedContentEntries=()=>[{fragment_id:'x',role:'source'}];
    earlierVisibleSourceRevision=()=>({markdown_body:'Original'});
    ensureSourceIndexes=()=>({blocksById:new Map()});fragmentTargetId=()=>null;roleLabel=x=>x;
    restoreDeletedContent=async()=>{restored++;return true;};
    (async()=>{showDeletedContents();await restoreButton();
      assert.equal(opened,1);assert.equal(closed,1);assert.equal(restored,1);
    })().catch(error=>{console.error(error);process.exitCode=1;});
}());
'''
    result=subprocess.run([node, '-'], input=script, capture_output=True, text=True)
    assert result.returncode==0,result.stderr


def test_dismissed_and_corrected_translation_clear_quality_stripe():
    import shutil, subprocess
    from pathlib import Path
    if not shutil.which('node'):
        pytest.skip('Node unavailable')
    js=(Path(__file__).parents[1]/'src/alc_render/web_assets/reader.js').read_text()
    script=js[:js.rfind('\n  if (document.readyState')]+r'''
    const assert=require('node:assert/strict');
    const classes=new Set(['alc-source-text-fallback']);
    const row={dataset:{},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)}};
    const fragment={fragment_id:'t',role:'translation',priority:50,anchor:{target_id:'b'},provenance:{}};
    state.selected=new Map([['t',fragment]]);
    deliveryIssueForBlock=()=>({source_preserved:true,category:'translation_source_text'});
    markDeliveryState(row,'b');assert(classes.has('alc-source-text-fallback'));
    const notice={closest:s=>s==='[data-fragment-id]'?{dataset:{fragmentId:'t'}}:row};
    dismissTranslationQuality(notice);assert(notice.hidden);assert(!classes.has('alc-source-text-fallback'));
    markDeliveryState(row,'b');assert(!classes.has('alc-source-text-fallback'));
    dismissedQualityFragments.clear();fragment.provenance.translation_quality_resolved={by:'user_edit'};
    markDeliveryState(row,'b');assert(!classes.has('alc-source-text-fallback'));
    }());'''
    subprocess.run(['node', '-'], input=script, check=True, capture_output=True, text=True)


def test_selection_drag_does_not_close_inline_editor():
    import shutil, subprocess
    from pathlib import Path
    if not shutil.which('node'):
        pytest.skip('Node unavailable')
    js=(Path(__file__).parents[1]/'src/alc_render/web_assets/reader.js').read_text()
    script=js[:js.rfind('\n  if (document.readyState')]+r'''
    const assert=require('node:assert/strict');
    const inside={},outside={};let dirty=false,cancelled=0,prompted=0;
    activeInlineDraftCard=()=>({contains:target=>target===inside});
    global.document={getElementById:()=>({open:false})};
    activeDraftHasChanges=()=>dirty;
    cancelActiveDraft=()=>cancelled++;
    openUnsavedDialog=()=>prompted++;
    const event=(type,target,detail=0)=>({type,target,detail,preventDefault(){},stopImmediatePropagation(){}});
    for (const changed of [false,true]) {
      dirty=changed;
      attemptInlineDraftExit(event('pointerdown',inside));
      attemptInlineDraftExit(event('click',outside,1));
      attemptInlineDraftExit(event('click',outside,2));
      assert.equal(cancelled,0);assert.equal(prompted,0);
    }
    dirty=false;attemptInlineDraftExit(event('pointerdown',outside));assert.equal(cancelled,1);
    dirty=true;attemptInlineDraftExit(event('pointerdown',outside));assert.equal(prompted,1);
    attemptInlineDraftExit(event('click',outside,0));assert.equal(prompted,2);
    }());'''
    subprocess.run(['node', '-'], input=script, check=True, capture_output=True, text=True)
