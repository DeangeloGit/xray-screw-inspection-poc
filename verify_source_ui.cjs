/* Execute the real page handlers with delayed HTTP responses, without a server. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
 constructor(){this.children=[];this.classList={add(){},remove(){},toggle(){}};this.value='';this.open=false}
 replaceChildren(...children){this.children=children} append(...children){this.children.push(...children)}
 setAttribute(){} addEventListener(){} close(){this.open=false} showModal(){this.open=true}
}
const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
const pending=[];const context={document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element(),querySelectorAll:()=>[],body:new Element()},window:{},history:{replaceState(){}},location:{search:''},URLSearchParams,URL,FormData,console,setTimeout(){},Option:Element,
 fetch(url,options){return new Promise(resolve=>pending.push({url,options,resolve}))}};
let source=fs.readFileSync('static/user.js','utf8');
const init=source.indexOf('(async()=>{try{await refresh();const params=');assert(init>0);
source=source.slice(0,init)+'globalThis.page={refresh,get photos(){return photos},get source(){return sourceToken}};})();';
vm.createContext(context);vm.runInContext(source,context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function reply(request,data){request.resolve({ok:true,json:async()=>data})}
function catalog(id,items=[]){return {machine:{id:'MPT12',name:'MPT12',reference_sha256:'ref'},source:{id,path:id},items:items.map(id=>({id,filename:id,is_reference:false})),model_fingerprint:'r2',detector_version:'same',detection_threshold:.13,reference:'ref'}}
(async()=>{
 const first=context.page.refresh();reply(pending.shift(),catalog('A',['old-A']));await first;
 assert.equal(context.page.photos.length,1);
 // A poll starts before a folder change. Its network response arrives last.
 const stale=context.page.refresh();const staleRequest=pending.shift();
 get('inspection-machine').value='MPT12';get('context-source').value='B';get('context-enabled').checked=true;
 const switched=get('context-form').onsubmit({preventDefault(){}});const save=pending.shift();assert.equal(save.url,'/api/inspection/context');
 reply(save,{saved:true,source:{id:'B'}});await settle();
 assert.equal(context.page.photos.length,0,'clear old rows immediately after saving, while B catalog is pending');
 assert.equal(get('file-list').children.length,0);
 const currentRequest=pending.shift();assert.equal(currentRequest.url,'/api/samples');
 reply(currentRequest,catalog('B'));await switched;
 reply(staleRequest,catalog('A',['old-A']));await stale;
 assert.equal(context.page.source,'B','late A response must not restore the old source');
 assert.equal(context.page.photos.length,0,'late A response must not restore old photos');
 // Two polling requests complete out of order within the new source.
 const earlier=context.page.refresh(),earlierRequest=pending.shift();
 const later=context.page.refresh(),laterRequest=pending.shift();
 reply(laterRequest,catalog('B',['new-B']));await later;
 reply(earlierRequest,catalog('B',[]));await earlier;
 assert.equal(context.page.photos[0].id,'new-B','a stale poll must not overwrite a newer list');
 console.log('PASS: immediate clear, delayed old-source response ignored, out-of-order polling, new-source rows only');
})().catch(error=>{console.error(error);process.exitCode=1});
