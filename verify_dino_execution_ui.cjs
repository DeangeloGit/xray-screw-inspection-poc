/* Run the real engineering page handlers, including poll versus unsaved selection. */
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
class Element {constructor(){this.value='';this.children=[];this.files=[]} replaceChildren(){this.children=[]} append(x){this.children.push(x)}}
const nodes=new Map(), get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
const requests=[], timers=[];
const context={document:{getElementById:get,createElement:()=>new Element()},window:{addEventListener(){}},
 fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))},
 setTimeout(fn){timers.push(fn)},FormData,AbortSignal,console};
const model={requested:'r2',backend:'dino_onnx',model_id:'47+65',mode:'auto_filter',decision_policy:'dino-top3-target-and-reference-v1',providers:['CPUExecutionProvider'],execution:'cpu'};
const settings=()=>({model,acquisition:{enabled:true,source:'unchanged',stable_seconds:15},default_provider:'cpu'});
function reply(url,data,ok=true){const i=requests.findIndex(r=>r.url===url);assert(i>=0,url);const r=requests.splice(i,1)[0];r.resolve({ok,json:async()=>data});return r}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/settings.js','utf8'),context);
 reply('/api/settings',settings());reply('/api/station',{model,acquisition:{enabled:true,state:'online'}});await settle();
 reply('/api/settings/models',{models:[]});reply('/api/settings',settings());await settle();
 assert.equal(get('dino-execution').value,'cpu');
 get('dino-execution').value='gpu';get('dino-execution').onchange();
 const poll=timers.shift()();reply('/api/station',{model,acquisition:{enabled:true,state:'online'}});await settle();reply('/api/settings',settings());await poll;
 assert.equal(get('dino-execution').value,'gpu','poll must preserve unsaved choice');
 let apply=get('apply-dino-execution').onclick();assert(get('apply-dino-execution').disabled);
 let request=reply('/api/settings/dino-execution',{error:'GPU cannot start; unchanged'},false);assert.equal(JSON.parse(request.options.body).execution,'gpu');await settle();reply('/api/settings',settings());await apply;
 assert.match(get('current-model').textContent,/CPU/);assert.match(get('dino-execution-message').textContent,/unchanged/);
 apply=get('apply-dino-execution').onclick();const gpu={...model,execution:'gpu',providers:['DmlExecutionProvider','CPUExecutionProvider'],gpu_device:'NVIDIA Quadro RTX 3000'};
 reply('/api/settings/dino-execution',{model:gpu,message:'saved'});await settle();reply('/api/settings',{...settings(),model:gpu});await apply;
 assert.match(get('current-model').textContent,/NVIDIA GPU/);assert.match(get('current-model').textContent,/參照圖＋待測圖/);
 assert.equal(get('dino-execution').value,'gpu');assert(!get('apply-dino-execution').disabled);
 const failedPoll=timers.shift()();reply('/api/station',{model:{...model,backend:'noop',requested_backend:'dino_onnx',error:'GPU unavailable'},acquisition:{enabled:true,state:'online'}});await settle();reply('/api/settings',settings());await failedPoll;
 assert(!get('apply-dino-execution').disabled,'CPU recovery remains available after GPU startup failure');
 assert.equal(requests.filter(r=>/analyze|inspect/.test(r.url)).length,0);
 console.log('PASS: CPU/GPU UI, actual device display, polling preserves pending choice, failure visible, no batch request');
})().catch(e=>{console.error(e);process.exitCode=1});
