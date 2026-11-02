(()=>{
const $=id=>document.getElementById(id);
let modelBusy=false,activeModelDirectory=null;
async function api(url,options={}){
 const response=await fetch(url,options);const result=await response.json();
 if(!response.ok)throw Error(result.error||'設定失敗');return result;
}
function message(id,text,error=false){$(id).textContent=text;$(id).className='message'+(error?' error':'')}
function showModel(m){activeModelDirectory=m.requested;$('current-model').textContent=m.backend==='noop'?'未啟用 AI，目前使用差分與人工複判':m.model_id+' · '+(m.providers.includes('CUDAExecutionProvider')?'NVIDIA GPU':'CPU');if(m.error)message('model-message',m.error,true)}
async function loadSettings(){
 try{const s=await api('/api/settings');$('source-enabled').checked=s.acquisition.enabled;$('source-path').value=s.acquisition.source;$('stable-seconds').value=s.acquisition.stable_seconds;$('model-provider').value=s.default_provider;showModel(s.model);await loadModels()}
 catch(e){message('source-message',e.message,true)}
}
$('source-form').onsubmit=async e=>{
 e.preventDefault();$('save-source').disabled=true;message('source-message','儲存中…');
 try{const result=await api('/api/settings/acquisition',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:$('source-enabled').checked,source:$('source-path').value,stable_seconds:Number($('stable-seconds').value)})});message('source-message',result.message)}
 catch(e){message('source-message',e.message,true)}finally{$('save-source').disabled=false}
};
$('browse-source').onclick=async()=>{const path=await window.pickXRayFolder($('source-path').value);if(path)$('source-path').value=path};
$('test-source').onclick=async()=>{message('source-message','正在測試來源連線…');try{if(!$('source-path').value.trim())throw Error('請先指定取圖資料夾');await api('/api/settings/folders?path='+encodeURIComponent($('source-path').value),{signal:AbortSignal.timeout(12000)});message('source-message','連線成功，可讀取此資料夾。')}catch(error){message('source-message',error.message,true)}};
$('model-file').onchange=()=>{$('selected-model').textContent=$('model-file').files[0]?.name||'尚未選擇檔案'};
async function applyModel(disable){
 if(modelBusy)return;
 const file=$('model-file').files[0];if(!disable&&!file){message('model-message','請先選擇 .onnx 模型檔案。',true);return}
 modelBusy=true;$('apply-model').disabled=true;$('disable-model').disabled=true;message('model-message',disable?'正在停用 AI…':'模型檢查中，請稍候…');
 try{const data=new FormData();data.set('provider',$('model-provider').value);data.set('normalization',$('normalization').value);data.set('backend',$('model-backend').value);data.set('classes',$('model-classes').value);data.set('input_size',$('model-size').value);data.set('screw_class_id',$('screw-class-id').value);data.set('confidence',$('model-confidence').value);if(disable)data.set('disable','true');else data.set('model',file);const result=await api('/api/settings/model',{method:'POST',body:data});showModel(result.model);await loadModels();message('model-message',result.message)}
 catch(e){message('model-message',e.message,true)}finally{modelBusy=false;$('apply-model').disabled=false;$('disable-model').disabled=false}
}
async function loadModels(){const data=await api('/api/settings/models');$('installed-model').replaceChildren();for(const m of data.models){const o=document.createElement('option');o.value=m.directory;o.textContent=m.model_id+' · '+m.backend+(m.directory===activeModelDirectory?'（目前）':'');$('installed-model').append(o)}if(activeModelDirectory)$('installed-model').value=activeModelDirectory}
$('model-backend').onchange=()=>{$('yolo-options').hidden=$('model-backend').value!=='yolo_onnx'};
$('select-model').onclick=async()=>{if(modelBusy)return;modelBusy=true;$('select-model').disabled=true;message('model-message','正在驗證並切換模型…');try{const data=await api('/api/settings/models/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({directory:$('installed-model').value})});showModel(data.model);message('model-message',data.message)}catch(e){message('model-message',e.message,true)}finally{modelBusy=false;$('select-model').disabled=false}};
$('model-form').onsubmit=e=>{e.preventDefault();applyModel(false)};
$('disable-model').onclick=()=>applyModel(true);
async function poll(){
 try{const s=await api('/api/station'),a=s.acquisition;$('source-state').textContent=!a.enabled?'自動取圖已關閉':a.state==='online'?'已連線，正在等待新照片':a.state==='offline'?'暫時無法讀取來源：'+a.error:'等待下一次掃描…';const settings=await api('/api/settings');$('saved-source').textContent=settings.acquisition.source?'已儲存來源：'+settings.acquisition.source:'';if(!modelBusy)showModel(s.model)}catch(e){$('source-state').textContent='狀態讀取失敗：'+e.message}setTimeout(poll,5000)
}
loadSettings();poll();

})();
