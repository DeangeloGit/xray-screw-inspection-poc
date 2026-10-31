const $=id=>document.getElementById(id);
let folderPath='',folderParent='',modelBusy=false,folderSequence=0;
async function api(url,options={}){
 const response=await fetch(url,options);const result=await response.json();
 if(!response.ok)throw Error(result.error||'設定失敗');return result;
}
function message(id,text,error=false){$(id).textContent=text;$(id).className='message'+(error?' error':'')}
function showModel(m){$('current-model').textContent=m.backend==='noop'?'未啟用 AI，目前使用差分與人工複判':m.model_id+' · '+(m.providers.includes('CUDAExecutionProvider')?'NVIDIA GPU':'CPU');if(m.error)message('model-message',m.error,true)}
async function loadSettings(){
 try{const s=await api('/api/settings');$('source-enabled').checked=s.acquisition.enabled;$('source-path').value=s.acquisition.source;$('stable-seconds').value=s.acquisition.stable_seconds;$('model-provider').value=s.default_provider;showModel(s.model)}
 catch(e){message('source-message',e.message,true)}
}
$('source-form').onsubmit=async e=>{
 e.preventDefault();$('save-source').disabled=true;message('source-message','儲存中…');
 try{const result=await api('/api/settings/acquisition',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:$('source-enabled').checked,source:$('source-path').value,stable_seconds:Number($('stable-seconds').value)})});message('source-message',result.message)}
 catch(e){message('source-message',e.message,true)}finally{$('save-source').disabled=false}
};
async function browse(path){
 const sequence=++folderSequence;
 message('folder-message','正在讀取資料夾…');$('confirm-folder').disabled=true;
 try{const data=await api('/api/settings/folders'+(path?'?path='+encodeURIComponent(path):''),{signal:AbortSignal.timeout(12000)});if(sequence!==folderSequence)return;folderPath=data.path;folderParent=data.parent;$('folder-location').value=folderPath;$('folder-list').replaceChildren();for(const folder of data.directories){const button=document.createElement('button');button.textContent='📁 '+folder.name;button.onclick=()=>browse(folder.path);$('folder-list').append(button)}message('folder-message',data.directories.length?'點選資料夾進入，或選用目前資料夾。':'這個資料夾沒有其他子資料夾。');$('confirm-folder').disabled=false}
 catch(e){if(sequence!==folderSequence)return;message('folder-message',e.name==='TimeoutError'?'資料夾讀取逾時，請確認網路分享已連線。':e.message,true)}
}
$('browse-source').onclick=()=>{$('folder-dialog').showModal();browse($('source-path').value)};
$('folder-navigation').onsubmit=e=>{e.preventDefault();browse($('folder-location').value)};
$('folder-parent').onclick=()=>browse(folderParent);
$('confirm-folder').onclick=()=>{$('source-path').value=folderPath;folderSequence++;$('folder-dialog').close()};
$('cancel-folder').onclick=()=>{folderSequence++;$('folder-dialog').close()};
$('model-file').onchange=()=>{$('selected-model').textContent=$('model-file').files[0]?.name||'尚未選擇檔案'};
async function applyModel(disable){
 if(modelBusy)return;
 const file=$('model-file').files[0];if(!disable&&!file){message('model-message','請先選擇 .onnx 模型檔案。',true);return}
 modelBusy=true;$('apply-model').disabled=true;$('disable-model').disabled=true;message('model-message',disable?'正在停用 AI…':'模型檢查中，請稍候…');
 try{const data=new FormData();data.set('provider',$('model-provider').value);data.set('normalization',$('normalization').value);if(disable)data.set('disable','true');else data.set('model',file);const result=await api('/api/settings/model',{method:'POST',body:data});showModel(result.model);message('model-message',result.message)}
 catch(e){message('model-message',e.message,true)}finally{modelBusy=false;$('apply-model').disabled=false;$('disable-model').disabled=false}
}
$('model-form').onsubmit=e=>{e.preventDefault();applyModel(false)};
$('disable-model').onclick=()=>applyModel(true);
async function poll(){
 try{const s=await api('/api/station'),a=s.acquisition;$('source-state').textContent=!a.enabled?'自動取圖已關閉':a.state==='online'?'已連線，正在等待新照片':a.state==='offline'?'暫時無法讀取來源：'+a.error:'等待下一次掃描…';const settings=await api('/api/settings');$('saved-source').textContent=settings.acquisition.source?'已儲存來源：'+settings.acquisition.source:'';if(!modelBusy)showModel(s.model)}catch(e){$('source-state').textContent='狀態讀取失敗：'+e.message}setTimeout(poll,5000)
}
loadSettings();poll();
