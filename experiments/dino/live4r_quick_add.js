(()=>{
const form=document.getElementById('quick-example-form');if(!form)return;
const status=document.getElementById('quick-example-status'),current=document.getElementById('quick-example-current'),button=document.getElementById('quick-example-submit');
const notice=sessionStorage.getItem('xray4r-added-notice');if(notice){status.textContent=notice;sessionStorage.removeItem('xray4r-added-notice')}
async function refresh(){const r=await fetch('/api/4r/examples/status',{cache:'no-store'}),d=await r.json();if(!r.ok)throw Error(d.error||'讀取目前圖庫失敗');current.textContent=`目前生效：${d.name}；螺絲 ${d.screw} 張、正常 ${d.normal} 張`}
refresh().catch(e=>{status.textContent=e.message});
form.addEventListener('submit',async e=>{e.preventDefault();const files=[...document.getElementById('quick-example-files').files];if(!files.length){status.textContent='請先選擇圖片。';return}button.disabled=true;status.textContent='正在建立並啟用圖庫，請稍候…';try{
 const fd=new FormData();fd.set('kind',document.getElementById('quick-example-kind').value);for(const file of files)fd.append('images',file);
 const r=await fetch('/api/4r/examples/add-and-activate',{method:'POST',body:fd}),d=await r.json();if(!r.ok)throw Error(d.error||'新增失敗');
 sessionStorage.setItem('xray4r-added-notice',`${d.message} 目前螺絲 ${d.screw} 張、正常 ${d.normal} 張。`);location.reload();
 }catch(err){status.textContent=err.message;button.disabled=false}});
})();
