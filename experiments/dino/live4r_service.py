"""Launch the versioned 4r DINO reference service in a separate workspace."""
import os,sys,hashlib,threading,json
from pathlib import Path
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(os.environ.get('XRAY_4R_HOME', ROOT/'workspace/4r-live-20261110')).expanduser().resolve()
if not (BASE/'settings.json').is_file():raise RuntimeError('缺少 4r settings.json；請先依移交文件還原並設定資料')
config=json.loads((BASE/'settings.json').read_text(encoding='utf8'))
os.environ.setdefault('XRAY_4R_ASSET_ROOT',config.get('asset_root',str(ROOT)))
os.environ['XRAY_CONFIG']=str(BASE/'settings.json')
os.environ['XRAY_WORKSPACE']=str(BASE/'station')
os.environ['XRAY_OVERKILL_PILOT']='1'
os.environ['XRAY_NO_BROWSER']='1'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'experiments/dino'))
import cv2,detector,overkill_pilot as pilot
import new_model_run as experiment
experiment.ROOT=Path(os.environ.get('XRAY_4R_ASSET_ROOT',ROOT)).expanduser().resolve()
from model_manager import manager, ModelManager
manager.execution_override=os.environ.get('XRAY_4R_PROVIDER','gpu' if sys.platform=='win32' else 'cpu')
if manager.execution_override not in ('cpu','gpu'):raise ValueError('XRAY_4R_PROVIDER 必須為 cpu 或 gpu')
original=manager.snapshot()
if original.error or original.session is None:raise RuntimeError('DINO model unavailable: '+str(original.info()))
manifest,bank,review,normal,details=experiment.load_banks(original)
cache=experiment.TensorCache(original.session,original.identity)
fingerprint=hashlib.sha256(('4r-live-'+original.identity+''.join(sorted(details['hashes'].values()))).encode()).hexdigest()
snapshot=replace(original,session=cache,manifest=manifest,feature_bank=bank,identity=fingerprint)
assert pilot.enabled(snapshot)
import detection_runtime
detection_runtime.PIPELINE='dino-4r-curated-v5-review-experimental'
import library
from app import app
orig_detect=library.detect
lock=threading.RLock()
from live4r_examples import LiveBanks
banks=LiveBanks(BASE,original,snapshot,details,lock)
banks.register(app,manager)
from flask import jsonify
def immutable_service_settings():
 return jsonify(error='此 4r 實驗服務固定使用 GPU 與 4r 模型；可在範例管理切換已建立的 4r 範例庫。'),409
app.view_functions['settings_api.apply_model']=immutable_service_settings
app.view_functions['settings_api.set_dino_execution']=immutable_service_settings
def detect_4r(*args,**kwargs):
 with lock:
  cache.clear();selected=kwargs.get('model_snapshot') or manager.snapshot();kwargs['model_snapshot']=selected
  with experiment.four_r(detector,pilot,selected,review,normal):
   result=orig_detect(*args,**kwargs)
  result['experimental_policy']='4r curated_v5_review + connector';result['experimental_main_bank']={'screw':len(selected.manifest['example_bank']['screw']['ids']),'normal':len(selected.manifest['example_bank']['normal']['ids']),'version':selected.requested,'fingerprint':selected.identity};result['production_changed']=False
  directory=kwargs.get('output_directory')
  if directory is not None:
   import json
   path=Path(directory)/'result.json';temporary=path.with_suffix('.verified.tmp')
   temporary.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8');temporary.replace(path)
  return result
library.detect=detect_4r
import machine_tuning
machine_tuning.detect=detect_4r
@app.after_request
def banner(response):
 if response.content_type and response.content_type.startswith('text/html'):
  html=response.get_data(as_text=True)
  marker='<section class="settings-panel" data-engineer-panel="ai" hidden><h2>AI 辨識模型（選用）</h2>'
  quick='''<section class="current" id="quick-example-panel"><h2>新增 DINO 參考案例</h2><p id="quick-example-current">正在讀取目前圖庫…</p><form id="quick-example-form"><label for="quick-example-kind">圖片類型</label><select id="quick-example-kind"><option value="screw">有掉落螺絲</option><option value="normal">正常、沒有螺絲</option></select><label for="quick-example-files">選擇裁好的圖片</label><input id="quick-example-files" type="file" accept=".png,.jpg,.jpeg,.tif,.tiff,.bmp" multiple required><button id="quick-example-submit" class="primary" type="submit">上傳並啟用</button><p id="quick-example-status" class="message" role="status"></p><p class="hint">按下後保留原範例，立即讓新圖參與 4r；重啟後仍使用。既有照片需重新試算，新增版本尚未完成回歸驗證。下方可查看或切回舊版。</p></form></section>'''
  if marker in html:html=html.replace(marker,marker+quick,1).replace('</body>','<script src="/4r/quick-add.js"></script></body>',1)
  html=html.replace('按下後才切換正式模型。' ,'按下後切換 4r 實驗範例庫，不改正式模型；新版本尚未回歸驗證。')
  html=html.replace('打勾＝新版會使用；取消勾選＝新版停用這張。舊版不受影響。','原有範例必須保留；這個實驗版本只支援新增。')
  html=html.replace('兩類各至少保留 3 張。','此 4r 實驗必須保留原有全部範例，目前只支援新增。')
  if '<body' in html:
   i=html.find('>',html.find('<body'))+1
   html=html[:i]+'<div style="background:#e5f0ff;color:#172c49;padding:10px;text-align:center;font-weight:bold">4r 實驗服務｜'+('原始 51＋90' if banks.active=='4r-curated-v5-review' else '新增範例版本：尚未回歸驗證')+'｜隔離工作區</div>'+html[i:]
   response.set_data(html)
 return response
print('4R READY',banks.current.info(),flush=True)
@app.before_request
def protect_old_tuning():
 from flask import request,jsonify
 if request.path.endswith('/tuning/apply') and request.method=='POST':
  body=request.get_json(silent=True) or {};token=body.get('preview_id','')
  if not isinstance(token,str) or len(token)!=32 or any(ch not in '0123456789abcdef' for ch in token):return jsonify(error='請先完成 4r 調校試算'),400
  path=BASE/'station/state/tuning-previews'/token/'result.json'
  try:
   import json
   result=json.loads(path.read_text(encoding='utf8'))
   if result.get('experimental_policy')!='4r curated_v5_review + connector':return jsonify(error='這份預覽不是完整 4r，請重新試算後再套用'),409
   if result.get('experimental_main_bank',{}).get('fingerprint')!=banks.current.identity:return jsonify(error='範例庫版本已變更，請重新試算後再套用'),409
  except (OSError,ValueError):return jsonify(error='找不到完整 4r 預覽，請重新試算'),409
import launch
launch.main()
