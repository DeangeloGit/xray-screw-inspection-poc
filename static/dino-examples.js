(()=>{
const root=document.getElementById('dino-examples-root')||(location.pathname==='/engineer/dino-examples'?document.querySelector('main'):null);if(!root)return;
if(new URLSearchParams(location.search).has('embedded')){document.querySelector('header')?.remove();const main=document.querySelector('main');if(main){main.style.padding='0';main.style.maxWidth='none'}}
const $=id=>root.querySelector('#'+id);let data,category='screw',keep=new Set(),uploads=[],busy=false,built=null;
const names={screw:'螺絲',normal:'非螺絲'};
async function api(url,opts={}){const r=await fetch(url,opts);const d=await r.json().catch(()=>({}));if(!r.ok){const e=Error(d.error||'操作失敗');e.status=r.status;throw e}return d}
function msg(t,error=false){$('message').textContent=t;$('message').className='message'+(error?' error':'')}
function lock(on){busy=on;root.querySelectorAll('button,input,select').forEach(e=>e.disabled=on)}
function counts(){if(!data)return;$('counts').textContent=['screw','normal'].map(l=>`${names[l]}：沿用 ${data.examples.filter(e=>e.label===l&&keep.has(e.id)).length} 張＋新增 ${uploads.filter(u=>u.label===l).length} 張`).join('　／　')}
function pic(src,title){const box=document.createElement('div'),im=document.createElement('img'),cap=document.createElement('span');im.src=src;im.loading='lazy';im.alt=title;cap.textContent=title;box.append(cap,im);return box}
function render(){
 $('category-title').textContent=names[category]+'範例';$('gallery').replaceChildren();
 for(const [i,e] of data.examples.filter(e=>e.label===category).entries()){
  const card=document.createElement('article');card.className='example'+(keep.has(e.id)?'':' off');
  const label=document.createElement('label'),cb=document.createElement('input');cb.type='checkbox';cb.checked=keep.has(e.id);cb.onchange=()=>{cb.checked?keep.add(e.id):keep.delete(e.id);card.classList.toggle('off',!cb.checked);counts()};label.append(cb,document.createTextNode(` 使用第 ${i+1} 張`));
  const p=document.createElement('p');p.className='hint';p.textContent=e.name;card.append(label,p);
  if(e.available){const ps=document.createElement('div');ps.className='pics';const url='/api/dino/image?model='+encodeURIComponent(data.selected)+'&id='+encodeURIComponent(e.id);ps.append(pic(url,'原始範例'),pic(url+'&view=input','DINO 實際看到'));card.append(ps)}else{const p=document.createElement('p');p.textContent='此舊版缺少原始範例圖片；無法沿用建立新版。';card.append(p)}
  $('gallery').append(card);
 }counts();
}
function clearUploads(){uploads.forEach(u=>URL.revokeObjectURL(u.preview));uploads=[];$('uploads').replaceChildren()}
async function load(model){lock(true);msg('讀取範例中…');try{data=await api('/api/dino/examples'+(model?'?model='+encodeURIComponent(model):''));clearUploads();keep=new Set(data.examples.map(e=>e.id));$('version').replaceChildren();for(const v of data.versions){const o=document.createElement('option');o.value=v.directory;o.textContent=v.name+(v.directory===data.active?'（目前使用）':'');$('version').append(o)}$('version').value=data.selected;$('active').textContent=data.active===data.selected?'這是目前使用的版本。':'目前只在查看此版本，尚未切換。';render();msg('已載入；取消勾選與上傳都只修改草稿。')}catch(e){if(e.status===404&&root.closest('#dino-section')&&['127.0.0.1','localhost'].includes(location.hostname)){embedLegacy();return}msg(e.message,true)}finally{lock(false)}}
root.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{category=b.dataset.category;root.querySelectorAll('[data-category]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));render()});
$('all').onclick=()=>{data.examples.filter(e=>e.label===category).forEach(e=>keep.add(e.id));render()};$('none').onclick=()=>{data.examples.filter(e=>e.label===category).forEach(e=>keep.delete(e.id));render()};
$('version').onchange=()=>{if(uploads.length||keep.size!==data.examples.length){if(!confirm('切換查看版本會清除尚未建立的草稿，是否繼續？')){$('version').value=data.selected;return}}load($('version').value)};
function renderUploads(){$('uploads').replaceChildren();for(const u of uploads){const card=document.createElement('article');card.className='example';const p=document.createElement('p');p.textContent=names[u.label]+'：'+u.file.name;const img=pic(u.preview,'DINO 實際看到');img.className='pics';const del=document.createElement('button');del.type='button';del.textContent='取消這張';del.onclick=()=>{URL.revokeObjectURL(u.preview);uploads=uploads.filter(x=>x!==u);renderUploads()};card.append(p,img,del);$('uploads').append(card)}counts()}
for(const label of ['screw','normal'])$(label+'-upload').onchange=async e=>{
 const files=[...e.target.files];e.target.value='';lock(true);
 try{if(uploads.length+files.length>100)throw Error('每次最多新增 100 張');if([...uploads.map(x=>x.file),...files].reduce((s,f)=>s+f.size,0)>39*1024*1024)throw Error('圖片合計請小於 39 MB');
 for(const file of files){if(file.size>8*1024*1024)throw Error(file.name+' 超過 8 MB');msg('產生實際輸入預覽：'+file.name);const fd=new FormData();fd.set('model',data.selected);fd.set('image',file);const r=await fetch('/api/dino/preview',{method:'POST',body:fd});if(!r.ok)throw Error((await r.json()).error);uploads.push({label,file,preview:URL.createObjectURL(await r.blob())})}
 msg('已加入草稿，請檢查預覽是否完整。');}catch(err){msg(err.message,true)}finally{renderUploads();lock(false)}
};
$('build').onclick=async()=>{if(busy||!data)return;lock(true);msg('正在建立新版範例庫，請稍候…');try{const fd=new FormData();fd.set('model',data.selected);fd.set('name',$('new-name').value);fd.set('keep',JSON.stringify([...keep]));for(const u of uploads)fd.append(u.label,u.file);const r=await api('/api/dino/build',{method:'POST',body:fd});built=r.directory;$('built').hidden=false;$('built-message').textContent=r.message;msg(r.message)}catch(e){msg(e.message,true)}finally{lock(false)}};
$('inspect').onclick=()=>load(built);
$('activate').onclick=async()=>{if(busy||!data)return;if(uploads.length||keep.size!==data.examples.length){msg('請先建立新版並查看新版，再切換使用。',true);return}lock(true);msg('正在驗證並切換模型…');try{const r=await api('/api/settings/models/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({directory:data.selected})});await load(data.selected);msg(r.message);window.dispatchEvent(new Event('dino-model-changed'));if(parent!==window)parent.postMessage({type:'dino-model-changed'},location.origin.replace(':18767',':18766'))}catch(e){msg(e.message,true)}finally{lock(false)}};
function embedLegacy(){
 const frame=document.createElement('iframe');frame.id='dino-examples-frame';frame.title='DINO 螺絲範例管理';const url=new URL('/engineer/dino-examples?embedded=1',location);url.port='18767';const requested=new URLSearchParams(location.search).get('dino_model');if(requested)url.searchParams.set('dino_model',requested);frame.src=url.href;root.replaceChildren(frame);
 window.addEventListener('message',e=>{if(e.origin!==url.origin||e.source!==frame.contentWindow)return;if(e.data?.type==='dino-height'&&Number.isFinite(e.data.height))frame.style.height=Math.max(1000,Math.min(30000,e.data.height+20))+'px';if(e.data?.type==='dino-model-changed')window.dispatchEvent(new Event('dino-model-changed'))});
}
if(parent!==window){new ResizeObserver(()=>parent.postMessage({type:'dino-height',height:document.body.scrollHeight},location.origin.replace(':18767',':18766'))).observe(document.body)}
const section=root.closest('#dino-section');let started=false;
function start(){if(!started){started=true;load(new URLSearchParams(location.search).get('dino_model'))}}
function openManager(){if(!section)return;section.open=true;start();section.scrollIntoView({block:'start',behavior:'smooth'})}
document.getElementById('manage-dino-examples')?.addEventListener('click',openManager);
if(section){section.addEventListener('toggle',()=>{if(section.open)start()});window.addEventListener('hashchange',()=>{if(location.hash==='#dino-examples')openManager()});if(location.hash==='#dino-examples')openManager();else if(section.open)start()}else start();
})();
