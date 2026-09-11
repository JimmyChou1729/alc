"""Offline Node behavioral checks for the Reader's local audio lifecycle."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_local_tts_reader_lifecycle():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for Reader lifecycle verification")
    reader = Path(__file__).parents[1] / "src/alc_render/web_assets/reader.js"
    script = r'''
const fs = require('fs'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
for (const name of ['localTtsText', 'speechAvailable', 'readLocalTtsEndpoint',
  'stripLocalTtsRuntime', 'cancelLocalTts', 'playLocalTtsAudio', 'speakLocalTts',
  'toggleSpeechPause', 'stopSpeech', 'finishSpeech', 'localTtsFailure',
  'speakSpeechIndex', 'refreshLocalTtsStatus', 'chooseSpeechVoice', 'localSpeechIdentity', 'decodeLocalSpeechIdentity',
  'speechChoiceForLanguage', 'speechSelection', 'speechRateLimit', 'displayedSpeechRate',
  'selectedSpeechVoice', 'speechVoiceIdentity', 'voiceMatchesLanguage',
  'updateSpeechAvailabilityStatus', 'renderSpeechVoiceOptions',
  'applyLocalTtsRate', 'cancelLocalTtsBuffer', 'localTtsAudioResult', 'cacheLocalTtsAudio', 'fillLocalTtsBuffer',
  'releaseLocalTtsAudio', 'localTtsChunk', 'localTtsSentenceBoundary', 'localTtsPart', 'nextLocalTtsPart', 'requestLocalTtsPart', 'setSpeechRate']) {
  const match = source.match(new RegExp('  (?:async )?function ' + name + '\\([^]*?\\n  }'));
  assert(match, name);
  eval(match[0]);
}
let state, requests, audio, revoked, statuses, config, spoken;
const labels = () => ({speechPlay:'Play', speechReady:'Ready', speechFinished:'Done', speechError:'Error: ', speechUnavailable:'Unavailable'});
const speechProfileLanguage = kind => kind === 'source' ? 'en' : 'zh';
const primaryLanguageTag = s => s.toLowerCase().split('-')[0];
const speechSegmentText = segment => segment.text;
const speechSegmentNode = () => null;
const setSpeechActiveNode = () => {};
const updateSpeechControls = () => {};
const syncSpeechPlayers = () => {};
const syncCustomSelect = () => {};
const automaticSpeechVoice = language => state.speechVoices.find(voice=>voiceMatchesLanguage(voice,language)) || null;
const speechVoiceDescription = voice => voice ? voice.name : "";
const refreshSpeechVoices = () => {};
const setSpeechStatus = (text, error) => statuses.push({text,error});
const readableSpeechIndex = index => index;
const document = {getElementById:id => id === 'alc-tts-config' ? config : null};
const window = {SpeechSynthesisUtterance: class {constructor(text){this.text=text;}},
  speechSynthesis:{cancel(){},speak(utterance){spoken.push(utterance);},pause(){},resume(){}},
  location: new URL('http://127.0.0.1:8888/cap/reader'), localStorage:{setItem(){}},
  Audio: class {constructor(url) {this.url=url; this.plays=0; this.pauses=0; this.currentTime=0; audio.push(this);}
    play(){this.plays++; return Promise.resolve();} pause(){this.pauses++;}
    removeAttribute(){} load(){} }};
URL.createObjectURL = () => 'blob:' + audio.length;
URL.revokeObjectURL = url => revoked.push(url);
const fetch = (url, options) => new Promise((resolve, reject) => requests.push({url,options,resolve,reject,resolved:false}));
const flush = async () => {for(let i=0;i<30;i++) await Promise.resolve();};
function wav(duration=10, size) {
 const buffer=new ArrayBuffer(44+Math.round(duration*20));const v=new DataView(buffer);
 const tag=(offset,text)=>Array.from(text).forEach((c,i)=>v.setUint8(offset+i,c.charCodeAt(0)));
 tag(0,'RIFF');v.setUint32(4,buffer.byteLength-8,true);tag(8,'WAVE');tag(12,'fmt ');v.setUint32(16,16,true);
 v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,10,true);v.setUint32(28,20,true);v.setUint16(32,2,true);v.setUint16(34,16,true);
 tag(36,'data');v.setUint32(40,buffer.byteLength-44,true);
 return {size:size||buffer.byteLength,arrayBuffer:async()=>buffer};
}
const respond = async (i, ok=true, duration=10, size) => {assert(requests[i], 'request '+i+' exists');requests[i].resolved=true;requests[i].resolve({ok,status:503,blob:async()=>wav(duration,size)});await flush();};
function reset() {
 requests=[]; audio=[]; revoked=[]; statuses=[];config=null;spoken=[];
 state={speechVoiceChoices:{},speechActiveProvider:'local',speechSupported:false,
   speechVoiceIdentities:{source:'',target:''},speechVoiceIdentity:'',speechVoices:[],speechRoles:new Set(['source']),
   localTtsEndpoint:'/cap/tts', localTtsStatus:{enabled:false,installed:false,selections:{en:{model_id:'english',voice:'0'},zh:{model_id:'chinese',voice:'0'}},
     models:[{id:'english',name:'English Model',installed:true,voices:[{id:'0',name:'EN Zero',language:'en'}]},
       {id:'chinese',name:'Chinese Model',installed:true,voices:[{id:'0',name:'ZH Zero',language:'zh'},{id:'new-voice',name:'New Voice',language:'zh'}]}]},
   localTtsStatusGeneration:0,localTtsBuffer:[],localTtsBuffering:null,localTtsCurrentPart:null,localTtsCache:new Map(),
   speechQueue:[{text:'First',language:'en',role:'source'},{text:'第二段',language:'zh',role:'target'}],
   speechGeneration:0,speechLoopMode:'none',speechRate:1};
}
(async () => {
 reset();state.speechQueue=[{text:'First sentence. Second sentence. Third sentence.',language:'en',role:'source'}];
 speakSpeechIndex(0);assert.equal(requests.length,1);assert.equal(audio.length,0,'wait for complete first paragraph');
 assert.equal(JSON.parse(requests[0].options.body).text,state.speechQueue[0].text);
 assert.equal(JSON.parse(requests[0].options.body).rate,1);await respond(0);
 assert.equal(audio[0].plays,1);audio[0].currentTime=4.2;const generation=state.speechGeneration;
 setSpeechRate(3);assert.equal(audio[0].playbackRate,3);assert.equal(audio[0].currentTime,4.2);
 assert.equal(audio[0].preservesPitch,true);assert.equal(requests.length,1);assert.equal(state.speechGeneration,generation);
 toggleSpeechPause();setSpeechRate(1.5);assert.equal(audio[0].currentTime,4.2);assert(state.speechPaused);
 toggleSpeechPause();assert.equal(audio[0].plays,2);assert.equal(requests.length,1);
 speakSpeechIndex(0);await flush();assert.equal(requests.length,1,'replay reuses completed audio');
 assert.equal(audio[1].playbackRate,1.5);assert.equal(revoked.length,1);stopSpeech(false);
 for(const language of ['en','zh']) {
   const text=language==='zh'?('这是需要完整保留的中文段落，包含标点和数字3.14。'.repeat(45)):('This longer paragraph includes Dr. Smith and the value 3.14. '.repeat(85));
   let rest=text,pieces=[];
   while(rest){const chunk=localTtsChunk(rest,language);assert(chunk.text.trim());assert(Array.from(chunk.text).length<=(language==='zh'?400:1600));pieces.push(chunk.text);rest=chunk.rest;}
   assert.equal(pieces.join('').replace(/\s/g,''),text.replace(/\s/g,''));assert(pieces.length>1);
 }
 for(const text of ['First item.\nSecond item.','第一项。\n第二项。','The value is 3.14. Use 127.0.0.1.','Dr. Smith and the U.S. team use e.g. this case.']) {
   assert.equal(localTtsChunk(text,'en').text,text);assert.equal(localTtsChunk(text,'en').rest,'');
 }
 reset();state.speechQueue=Array.from({length:8},(_,i)=>({text:'Paragraph '+i+'.',language:'en',role:'source'}));
 speakSpeechIndex(0);await respond(0,true,20);
 assert.equal(requests.length,2,'background starts once complete current paragraph is ready');
 await respond(1,true,20);assert.equal(requests.length,3);
 await respond(2,true,20);assert.equal(requests.length,4);
 await respond(3,true,20);assert.equal(requests.length,4);assert.equal(state.localTtsBuffer.length,3);
 assert.equal(state.localTtsBuffer.reduce((sum,e)=>sum+e.result.duration,0),60);
 audio[0].onended();await flush();assert.equal(audio[1].plays,1);assert.equal(requests.length,5,'continuously refill as queue advances');
 assert.equal(state.localTtsBuffer.length,3);assert.equal(requests.filter(r=>!r.resolved&&!r.options.signal.aborted).length,1,'only one inference request in flight');
 stopSpeech(false);assert(requests[4].options.signal.aborted);await respond(4);assert.equal(audio.length,2,'cancelled result does not play');
 reset();state.speechQueue=Array.from({length:5},(_,i)=>({text:'Long paragraph '+i+'.',language:'en',role:'source'}));
 speakSpeechIndex(0);await respond(0);await respond(1,true,60);
 assert.equal(requests.length,2,'duration target stops prefetch before count limit');assert.equal(state.localTtsBuffer.length,1);stopSpeech(false);
 reset();state.speechQueue=Array.from({length:5},(_,i)=>({text:'Large audio '+i+'.',language:'en',role:'source'}));
 speakSpeechIndex(0);await respond(0);await respond(1,true,5,20*1024*1024);await respond(2,true,5,20*1024*1024);
 assert(state.localTtsBuffer.reduce((sum,e)=>sum+(e.result?e.result.bytes:0),0)<=32*1024*1024);assert.equal(requests.length,3);
 assert([...state.localTtsCache.values()].reduce((sum,e)=>sum+e.bytes,0)<=32*1024*1024);stopSpeech(false);
 reset();speakSpeechIndex(0);setSpeechRate(3);toggleSpeechPause();setSpeechRate(1.2);
 assert.equal(requests.length,1,'speed changes while first paragraph generates must not start parallel inference');
 await respond(0);assert.equal(audio[0].plays,0);
 await respond(1);assert(state.speechPaused);toggleSpeechPause();audio[0].onended();await flush();assert.equal(audio[1].plays,1);stopSpeech(false);
 reset();state.speechQueue=[{text:'Repeat this paragraph.',language:'en',role:'source'}];state.speechLoopMode='one';
 speakSpeechIndex(0);await respond(0,true,20);assert.equal(requests.length,1);
 assert(state.localTtsBuffer.length<=3);audio[0].onended();await flush();assert.equal(requests.length,1,'loop reuses complete paragraph');
 stopSpeech(false);assert(state.localTtsCache.size>0,'stop keeps bounded reusable audio');
 reset();state.speechLoopMode='all';speakSpeechIndex(0);await respond(0,true,20);await respond(1,true,20);
 assert.equal(requests.length,2);assert(state.localTtsBuffer.length<=3);audio[0].onended();await flush();audio[1].onended();await flush();
 assert.equal(requests.length,2,'repeat all uses bounded cached paragraphs');stopSpeech(false);
 reset();speakSpeechIndex(0);await respond(0,true,5,20*1024*1024);await respond(1,true,5,20*1024*1024);
 speakSpeechIndex(0);await flush();assert.equal(requests.filter(r=>JSON.parse(r.options.body).text==='First').length,1,'current paragraph remains reusable under cache pressure');stopSpeech(false);
 reset();speakSpeechIndex(0);const obsolete=requests[0];speakSpeechIndex(1);assert(obsolete.options.signal.aborted);
 await respond(1);await respond(0);assert.equal(audio.length,1);stopSpeech(false);
 reset();speakSpeechIndex(0);await respond(0);const prefetch=requests[1];
 chooseSpeechVoice('zh',localSpeechIdentity('chinese','new-voice'));await flush();assert(prefetch.options.signal.aborted);
 assert.equal(JSON.parse(requests[2].options.body).voice,'new-voice');await respond(1);assert.equal(audio.length,2);stopSpeech(false);
 reset();speakSpeechIndex(0);await respond(0,false);assert(!state.speechPlaying);assert(statuses.at(-1).text.includes('choose a system voice'));
 reset();speakSpeechIndex(0);await respond(0);await respond(1,false);assert(state.speechPlaying);
 audio[0].onended();await flush();assert(!state.speechPlaying);assert.equal(speechSelection(state.speechQueue[1]).provider,'local');
 reset();state.speechQueue=[{text:'中文原文。',language:'zh',role:'source'},{text:'English translation.',language:'en',role:'translation'}];
 speakSpeechIndex(0);await respond(0);assert.equal(JSON.parse(requests[0].options.body).model_id,'chinese');assert.equal(JSON.parse(requests[1].options.body).model_id,'english');
 await respond(1);audio[0].onended();await flush();assert.equal(audio[1].plays,1);stopSpeech(false);
 reset();state.speechSupported=true;state.speechVoices=[{name:'System English',lang:'en',voiceURI:'sys-en'}];
 state.speechVoiceChoices.en=speechVoiceIdentity(state.speechVoices[0]);state.speechRate=3;
 speakSpeechIndex(0);assert.equal(spoken[0].rate,3);assert.equal(requests.length,0);spoken[0].onend();
 assert.equal(JSON.parse(requests[0].options.body).model_id,'chinese');assert.equal(JSON.parse(requests[0].options.body).rate,1);
 await respond(0);assert.equal(audio[0].playbackRate,3);stopSpeech(false);
 reset();state.speechSupported=true;state.speechVoices=[{name:'System Chinese',lang:'zh',voiceURI:'sys-zh'}];
 state.speechVoiceChoices.zh=speechVoiceIdentity(state.speechVoices[0]);speakSpeechIndex(0);await respond(0);
 assert.equal(requests.length,1,'system successor never triggers local request');audio[0].onended();assert.equal(spoken[0].text,'第二段');stopSpeech(false);
 reset();state.speechQueue=[{text:'First long sentence. '.repeat(100),language:'en',role:'source'},{text:'Next paragraph.',language:'en',role:'source'}];
 state.speechSupported=true;state.speechVoices=[{name:'System English',lang:'en',voiceURI:'sys-en'}];speakSpeechIndex(0);await respond(0,true,60);
 state.localTtsStatus.selections.en=null;await respond(1,true,60);audio[0].onended();await flush();
 assert.equal(spoken.length,0,'default changes retain current paragraph provider');audio[1].onended();assert.equal(spoken[0].text,'Next paragraph.');stopSpeech(false);
 reset();state.speechVoiceChoices.en=localSpeechIdentity('not-installed','0');speakSpeechIndex(0);
 assert.equal(requests.length,0);assert.equal(spoken.length,0);assert(statuses.at(-1).error);
 reset();state.localTtsEndpoint='';state.speechVoiceChoices.en=localSpeechIdentity('english','0');assert.equal(speechSelection({language:'en'}).provider,'system');
 reset();state.speechVoiceIdentities.source=JSON.stringify(['sys-en','Saved English','en']);
 assert.equal(speechChoiceForLanguage('en').identity,state.speechVoiceIdentities.source);
 assert(!decodeLocalSpeechIdentity(JSON.stringify(['local','System voice','en'])));
 reset();config={textContent:JSON.stringify({endpoint:'/cap/tts'})};assert.equal(readLocalTtsEndpoint(),'/cap/tts');
 config.textContent=JSON.stringify({endpoint:'//evil.example/tts'});assert.equal(readLocalTtsEndpoint(),'');
 config.textContent=JSON.stringify({endpoint:'/cap/tts'});window.location=new URL('file:///reader.html');assert.equal(readLocalTtsEndpoint(),'');window.location=new URL('http://127.0.0.1:8888/cap/reader');
 let removed=0,policy="default-src 'none'; connect-src http://127.0.0.1:8888/secret/tts/; media-src blob: data:";
 stripLocalTtsRuntime({querySelector:()=>({}),querySelectorAll:selector=>selector.includes('meta')?[{getAttribute:()=>policy,setAttribute:(_,value)=>policy=value}]:[{remove(){removed++;}}]});
 assert.equal(removed,1);assert(!policy.includes('secret'));assert(policy.includes("connect-src 'none'"));assert(source.includes('stripLocalTtsRuntime(root);'));
 reset();const pending=refreshLocalTtsStatus();chooseSpeechVoice('en','');requests[0].resolve({ok:true,json:async()=>state.localTtsStatus});await pending;
 assert.equal(speechSelection({language:'en'}).provider,'system');
 reset();const unavailable=refreshLocalTtsStatus();requests[0].reject(new Error('offline'));await unavailable;assert(!speechAvailable());assert(statuses.at(-1).error);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", script, str(reader)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_unified_voice_groups_refresh_and_keyboard():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for Reader control verification")
    reader = Path(__file__).parents[1] / "src/alc_render/web_assets/reader.js"
    script = r'''
const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
for(const name of ['localSpeechIdentity','decodeLocalSpeechIdentity','speechChoiceForLanguage',
 'renderSpeechVoiceOptions','syncCustomSelect','customSelectOptions','refreshLocalTtsStatus','setupLocalTts']) {
 eval(source.match(new RegExp('  (?:async )?function '+name+'\\([^]*?\\n  }'))[0]);
}
let focused=null;
class Node {
 constructor(tag,css='',text=''){this.tagName=tag.toUpperCase();this.className=css;this.textContent=text;this.children=[];this.attributes={};this.events={};this.dataset={};this.value='';this.disabled=false;}
 appendChild(node){this.children.push(node);node.parentElement=this;return node;}
 replaceChildren(){this.children=[];}
 setAttribute(key,value){this.attributes[key]=value;}
 getAttribute(key){return this.attributes[key];}
 addEventListener(key,fn){this.events[key]=fn;}
 dispatchEvent(event){if(this.events[event.type])this.events[event.type](event);}
 focus(){focused=this;}
 get options(){return this.children.flatMap(n=>n.tagName==='OPTION'?[n]:n.options);}
 get selectedIndex(){return this.options.findIndex(n=>n.value===this.value);}
 querySelectorAll(selector){const nodes=this.children.flatMap(n=>[n,...n.querySelectorAll('*')]);return selector==='*'?nodes:nodes.filter(n=>n.getAttribute('role')==='option'&&(!selector.includes(':disabled')||!n.disabled));}
}
const element=(...args)=>new Node(...args);
const customSelectRegistry=new Map();
const selectListbox=wrapper=>wrapper.listbox;
const closeCustomSelect=()=>{};
function wrapperFor(select){const wrapper={listbox:new Node('div'),trigger:new Node('button'),value:new Node('span'),querySelector(selector){return selector==='.alc-select-trigger'?this.trigger:this.value;}};customSelectRegistry.set(select,wrapper);return wrapper;}
const sourceSelect=new Node('select'),targetSelect=new Node('select');
const controls={'alc-speech-source-voice':sourceSelect,'alc-speech-target-voice':targetSelect};
const document={getElementById:id=>controls[id]||null};
const sourceWrapper=wrapperFor(sourceSelect);wrapperFor(targetSelect);
const labels=()=>({automaticVoice:'Automatic',automaticVoiceSelection:'Automatic · {voice}'});
const localTtsText=english=>english;
const speechProfileLanguage=kind=>kind==='source'?'zh':'en';
const primaryLanguageTag=lang=>lang.split('-')[0];
const voiceMatchesLanguage=(voice,lang)=>primaryLanguageTag(voice.lang)===primaryLanguageTag(lang);
const speechVoiceIdentity=voice=>JSON.stringify([voice.voiceURI,voice.name,voice.lang]);
const speechVoiceDescription=voice=>voice?voice.name:'';
const automaticSpeechVoice=lang=>state.speechVoices.find(v=>v.lang===lang);
const updateSpeechAvailabilityStatus=()=>{},updateSpeechControls=()=>{};
const state={speechVoiceChoices:{},speechVoiceIdentities:{source:'',target:''},localTtsEndpoint:'/cap/tts',localTtsStatusGeneration:0,
 speechVoices:[{voiceURI:'sys-en',name:'System English',lang:'en'}],localTtsStatus:{selections:{en:{model_id:'model-a',voice:'0'},zh:null},models:[
 {id:'model-a',name:'Model A',installed:true,voices:[{id:'0',name:'A zero',language:'en'}]},
 {id:'model-b',name:'Model B',installed:true,voices:[{id:'0',name:'B zero',language:'en'}]},
 {id:'new-model',name:'New Model',installed:false,voices:[{id:'voice',name:'New voice',language:'en'}]}
 ]}};
let responseStatus=state.localTtsStatus;
const fetch=async()=>({ok:true,json:async()=>responseStatus});
const window={Event:class{constructor(type){this.type=type;}},localStorage:{getItem(){return null;}},addEventListener(type,fn){this.listeners[type]=fn;},listeners:{}};
const readLocalTtsEndpoint=()=>'/cap/tts';
(async()=>{
 renderSpeechVoiceOptions();
 assert.deepEqual(sourceSelect.children.map(n=>n.label),['Model A','Model B','System voices']);
 assert(sourceSelect.options.some(n=>n.textContent==='System English'),'English control stays tied to English');
 assert.equal(sourceSelect.value,localSpeechIdentity('model-a','0'));
 const identities=sourceSelect.options.filter(n=>n.textContent.includes('zero')).map(n=>n.value);
 assert.notEqual(identities[0],identities[1],'same voice id from different models must not collide');
 assert.deepEqual(sourceWrapper.listbox.children.map(n=>n.getAttribute('aria-label')),['Model A','Model B','System voices']);
 state.speechVoiceChoices.en=localSpeechIdentity('new-model','voice');renderSpeechVoiceOptions();
 const unavailable=sourceSelect.options.find(n=>n.value===state.speechVoiceChoices.en);
 assert(unavailable.disabled);assert(sourceWrapper.listbox.querySelectorAll('[role="option"]').some(n=>n.disabled));
 state.localTtsStatus.models[2].installed=true;await refreshLocalTtsStatus();
 assert(sourceSelect.children.some(n=>n.label==='New Model'),'installation refresh must expose new group');
 assert.equal(sourceSelect.value,state.speechVoiceChoices.en);
 assert(!sourceSelect.options.find(n=>n.value===state.speechVoiceChoices.en).disabled);
 state.localTtsStatus.models[2].installed=false;await refreshLocalTtsStatus();
 assert.equal(sourceSelect.value,state.speechVoiceChoices.en,'removed selection remains visible rather than changing provider');
 const plain=new Node('select');for(let i=0;i<3;i++){const option=new Node('option','',String(i));option.value=String(i);option.disabled=i===1;plain.appendChild(option);}plain.value='0';
 const plainWrapper=wrapperFor(plain);syncCustomSelect(plain);
 assert.equal(plainWrapper.listbox.children.length,3);assert(plainWrapper.listbox.children.every(n=>n.getAttribute('role')==='option'),'ungrouped select retains flat options');
 const options=customSelectOptions(plainWrapper);assert.deepEqual(options.map(n=>n.dataset.value),['0','2']);
 options[0].events.keydown({key:'ArrowDown',preventDefault(){}});assert.equal(focused,options[1]);
 options[1].events.click();assert.equal(plain.value,'2');
 state.speechVoiceChoices={};window.localStorage.getItem=key=>key==='alc.reader.speech-engine'?'system':null;
 setupLocalTts();assert.deepEqual(state.speechVoiceChoices,{en:'',zh:''});
 assert.equal(typeof window.listeners.focus,'function');
 await window.listeners.focus();
 assert(!source.includes('function selectSpeechEngine('));assert(!source.includes('alc-tts-system-fallback'));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", script, str(reader)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
