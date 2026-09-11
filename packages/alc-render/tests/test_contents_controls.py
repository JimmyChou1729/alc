"""Exercise independent contents language and Reader section visibility in Node."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_contents_language_and_section_visibility():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for Reader controls verification")
    reader = Path(__file__).parents[1] / "src/alc_render/web_assets/reader.js"
    script = r'''
const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
for(const name of ['renderVisibilityOptions','visibilityOption','visibleRoleCount','applyVisibility',
 'updateVisibilityStyles','renderSpeechRoleOptions','speechRoleOption','renderContents',
 'setupContentsLanguage','syncContentsLanguage','updateContentsTitles','visibleHeadingForBlock','appendContentsLink','renderBibliography','revealAppendixTarget','activateHashTarget']) {
 eval(source.match(new RegExp('  function '+name+'\\([^]*?\\n  }'))[0]);
}
class Node {
 constructor(tag,css='',text=''){this.tagName=tag.toUpperCase();this.className=css;this.text=text;this.children=[];this.dataset={};this.attrs={};this.events={};this.classes=new Set();this.classList={toggle:(key,value)=>value?this.classes.add(key):this.classes.delete(key)};}
 appendChild(child){if(child.parentElement){const siblings=child.parentElement.children;siblings.splice(siblings.indexOf(child),1);}child.parentElement=this;this.children.push(child);return child;}
 insertBefore(child,before){child.parentElement=this;this.children.splice(this.children.indexOf(before),0,child);}
 replaceChildren(){this.children=[];this.text='';}
 setAttribute(key,value){this.attrs[key]=value;}
 addEventListener(key,fn){this.events[key]=fn;}
 querySelectorAll(selector){return this.children.flatMap(n=>[n,...n.querySelectorAll('*')]).filter(n=>selector==='*'||(selector==='button'&&n.tagName==='BUTTON')||(selector==='a[data-block-id]'&&n.tagName==='A'&&n.dataset.blockId));}
 get textContent(){return this.text+this.children.map(n=>n.textContent).join('');}
 set textContent(value){this.text=value;this.children=[];}
 get childNodes(){return this.children;}
 get firstElementChild(){return this.children[0]||null;}
 set innerHTML(value){this.replaceChildren();const match=/^(#{1,6}) (.*)/.exec(value);const heading=new Node(match?'h'+match[1].length:'p');heading.appendChild(new Node('text','',match?match[2]:value));this.appendChild(heading);}
 cloneNode(){const clone=new Node(this.tagName,this.className,this.text);this.children.forEach(child=>clone.appendChild(child.cloneNode()));return clone;}
}
const element=(...args)=>new Node(...args);
const body=new Node('body'),head=new Node('head');
function mount(id,tag='div'){const n=new Node(tag);n.id=id;body.appendChild(n);return n;}
const view=mount('alc-view-options'),speech=mount('alc-speech-role-options'),heading=mount('alc-contents-heading','h2'),list=mount('alc-contents-list','ol');
const document={body,head,getElementById:id=>[body,...body.querySelectorAll('*'),...head.querySelectorAll('*')].find(n=>n.id===id)||null};
const labels=()=>({original:'原文',documentData:'页面信息',glossary:'术语表',references:'References',companionReferences:'伴读参考文献',contents:'目录',contentsSource:'原文',contentsTranslation:'译文',contentsLanguage:'目录语言'});
const roleLabel=role=>role;
const roleSlot=role=>{if(!state.roleSlots.has(role))state.roleSlots.set(role,state.roleSlots.size);return state.roleSlots.get(role);};
const scheduleScrollableTableSync=()=>{};
const updateSpeechControls=()=>{},speechAvailable=()=>true,stopSpeech=()=>{},setSpeechStatus=()=>{};
const safeToken=value=>value;
const window={location:{hash:''},history:{pushState(){},replaceState(){}}};
const hashTargetId=hash=>hash.slice(1),canonicalReaderTargetId=value=>value,chunkForTargetId=()=>({});
const revealSourceTarget=()=>false,renderChunk=()=>{},armHashCalibration=()=>{};
let lastScroll='';const scrollToHashTarget=target=>{lastScroll=target;};
const appendTocTitle=(root,text)=>root.appendChild(new Node('text','',text));
const appendSupplementCoverage=()=>{};
const projectGlossaryMarkdown=text=>text;
const fragmentTargetId=fragment=>fragment.anchor&&fragment.anchor.target_id;
const fragmentIsVisible=fragment=>!fragment.deleted;
const sourceEdits=new Map();const sourceReplacement=id=>sourceEdits.get(id);
const removeVisibleHtmlTags=()=>{},typeset=()=>{};
const decorateGlossary=(node,role)=>{node.dataset.glossaryRole=role;};
function fragment(id,role,text){return{fragment_id:id,role,priority:10,anchor:{target_id:'heading'},markdown_body:'# '+text};}
const sourceHeading=fragment('source-edit','source','Source edited'),translation=fragment('translated','translation','翻译标题');
const state={sourceVisible:true,glossaryVisible:true,referencesVisible:true,pageMarkersVisible:false,roleOrder:['source','translation'],hiddenRoles:new Set(),roleSlots:new Map([['source',0],['translation',1]]),
 visibilityReady:true,contentsLanguage:'source',speechRoles:new Set(['source']),speechPlaying:false,
 selected:new Map([[sourceHeading.fragment_id,sourceHeading],[translation.fragment_id,translation]]),revisions:new Map(),
 payload:{selected_heading_fragments:[],publication:{glossary:[{term:'word'}],bibliography:[{id:'ref-1',title:'Companion source'}]}},md:{render:text=>text}};
renderVisibilityOptions();renderSpeechRoleOptions();
const values=root=>root.children.map(label=>label.children[0].value);
assert.deepEqual(values(view),['source','page-markers','translation','glossary-section','references-section']);
assert.deepEqual(values(speech),['source','translation']);assert.equal(visibleRoleCount(),1);
renderContents(list,[{anchor_block_id:'heading',level:1,title:'Original title'}],labels());
const link=list.children[0].children[0];assert.equal(link.textContent,'Source edited');
const group=document.getElementById('alc-contents-language');assert(group);assert.equal(group.parentElement.children[0],heading);
assert.equal(group.children[0].attrs['aria-pressed'],'true');
view.children[0].children[0].checked=false;view.children[0].children[0].events.change();
assert.equal(state.sourceVisible,false);assert(body.classes.has('alc-focused-reading'));
assert(state.visibilityStyle.textContent.includes('.alc-fragment[data-role-slot="0"]{display:none}'));
assert.equal(link.textContent,'Source edited','body source visibility cannot select translated contents');
const sourceBefore=state.sourceVisible,hiddenBefore=Array.from(state.hiddenRoles);
group.children[1].events.click();assert.equal(state.contentsLanguage,'translation');assert.equal(link.textContent,'翻译标题');
assert.equal(state.sourceVisible,sourceBefore);assert.deepEqual(Array.from(state.hiddenRoles),hiddenBefore);
state.hiddenRoles.add('translation');applyVisibility();updateContentsTitles();assert.equal(link.textContent,'翻译标题','hidden translated body still provides translated contents');
assert(body.classes.has('alc-no-visible-content'),'source role is not double-counted as body channel');
state.selected.delete(translation.fragment_id);updateContentsTitles();assert.equal(link.textContent,'Source edited','missing translated title falls back to source edit');
state.payload.selected_heading_fragments=[{...translation,target_id:'heading',markdown_body:'# Unloaded translation'}];
updateContentsTitles();assert.equal(link.textContent,'Unloaded translation');
state.selected.set(translation.fragment_id,{...translation,markdown_body:'# Newly edited title'});updateContentsTitles();assert.equal(link.textContent,'Newly edited title');
state.selected.set(translation.fragment_id,{...translation,deleted:true});updateContentsTitles();assert.equal(link.textContent,'Source edited','deleted selected title does not revive embedded stale translation');
state.selected.delete(translation.fragment_id);state.revisions.set(translation.fragment_id,[]);updateContentsTitles();assert.equal(link.textContent,'Source edited');
sourceEdits.set('heading',{deleted:true});updateContentsTitles();assert.equal(link.parentElement.hidden,true);group.children[0].events.click();assert.equal(link.parentElement.hidden,true);
sourceEdits.delete('heading');updateContentsTitles();assert.equal(link.parentElement.hidden,false);
const glossaryToggle=view.children.find(n=>n.children[0].value==='glossary-section').children[0];const bodyRoles=Array.from(state.hiddenRoles),audioRoles=Array.from(state.speechRoles),channels=visibleRoleCount();
glossaryToggle.checked=false;glossaryToggle.events.change();assert.equal(state.glossaryVisible,false);
assert(state.visibilityStyle.textContent.includes('#alc-glossary,[data-contents-entry="glossary"]{display:none}'));
assert.equal(list.children[1].dataset.contentsEntry,'glossary');assert.equal(visibleRoleCount(),channels);
assert.deepEqual(Array.from(state.hiddenRoles),bodyRoles);assert.deepEqual(Array.from(state.speechRoles),audioRoles);
glossaryToggle.checked=true;glossaryToggle.events.change();assert(!state.visibilityStyle.textContent.includes('#alc-glossary'));
const referencesToggle=view.children.find(n=>n.children[0].value==='references-section').children[0];
const bibliographyBefore=JSON.stringify(state.payload.publication.bibliography);
referencesToggle.checked=false;referencesToggle.events.change();assert.equal(state.referencesVisible,false);
assert(state.visibilityStyle.textContent.includes('#alc-references,[data-contents-entry="references"]{display:none}'));
assert.equal(list.children[2].dataset.contentsEntry,'references');assert.equal(list.children[2].textContent,'伴读参考文献');
assert.equal(visibleRoleCount(),channels);assert.deepEqual(Array.from(state.hiddenRoles),bodyRoles);assert.deepEqual(Array.from(state.speechRoles),audioRoles);
assert.equal(JSON.stringify(state.payload.publication.bibliography),bibliographyBefore,'hiding references preserves reference data and numbering');
referencesToggle.checked=true;referencesToggle.events.change();assert(!state.visibilityStyle.textContent.includes('#alc-references'));
const bibliographyIndex=()=>({groups:[{targetId:'ref-1',entry:state.payload.publication.bibliography[0]}]});
const appendix=new Node('main');renderBibliography(appendix,state.payload.publication.bibliography,labels());
assert.equal(appendix.children[0].children[0].textContent,'伴读参考文献');assert.equal(appendix.children[0].children[1].children[0].id,'reference-ref-1');
assert(source.includes('references: "References"'),'source references label remains separate');
state.referencesVisible=false;applyVisibility();activateHashTarget('#reference-ref-1',true);
assert.equal(state.referencesVisible,true);assert.equal(lastScroll,'reference-ref-1');
assert(view.children.find(n=>n.children[0].value==='references-section').children[0].checked);
state.referencesVisible=false;applyVisibility();scrollToHashTarget('reference-ref-1');assert.equal(state.referencesVisible,false,'ordinary scroll does not reveal appendix');
activateHashTarget('#alc-references',true);assert.equal(state.referencesVisible,true);
state.glossaryVisible=false;applyVisibility();activateHashTarget('#alc-glossary',true);assert.equal(state.glossaryVisible,true);
assert(view.children.find(n=>n.children[0].value==='glossary-section').children[0].checked);
assert.deepEqual(Array.from(state.hiddenRoles),bodyRoles);assert.deepEqual(Array.from(state.speechRoles),audioRoles);
state.sourceVisible=true;state.hiddenRoles.add('source');applyVisibility();assert(!state.visibilityStyle.textContent.includes('data-role-slot="0"'),'source master switch overrides stale role visibility');
state.roleOrder.push('glossary');renderVisibilityOptions();assert(values(view).includes('glossary'));assert(values(view).includes('glossary-section'),'section toggle does not collide with real role');
state.payload.publication.glossary=[];state.payload.publication.bibliography=[];list.replaceChildren();renderContents(list,[],labels());assert.equal(list.children.length,0);
renderVisibilityOptions();const emptyToggle=view.children.find(n=>n.children[0].value==='glossary-section').children[0];emptyToggle.checked=false;emptyToggle.events.change();emptyToggle.checked=true;emptyToggle.events.change();
assert.equal(state.glossaryVisible,true);assert.equal(body.children.filter(n=>n.className==='alc-contents-heading-row').length,1,'rerender does not duplicate controls');
'''
    result = subprocess.run([node, "-e", script, str(reader)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
