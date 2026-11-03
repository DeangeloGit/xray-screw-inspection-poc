"""Real DINO inference parity and isolated UI selection/persistence tests."""
import os,json,sys,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def child():
 import shutil,copy,numpy as np
 from PIL import Image
 from runtime_paths import MODEL_ROOT
 from model_manager import ModelManager,Snapshot
 from app import app
 source=ROOT/'models';version='dino-examples-a3b8c97aa539';clip='clip-examples-916f8a7fd458'
 for name in (version,clip):
  dest=MODEL_ROOT/name;dest.mkdir(parents=True)
  shutil.copyfile(source/name/'manifest.json',dest/'manifest.json');os.link(source/name/'model.onnx',dest/'model.onnx')
 m=ModelManager(MODEL_ROOT,allow_cpu=True);snap=m.snapshot(version);assert not snap.error,snap.error
 report=json.loads((ROOT/'workspace/dino-experiment-20261103/result.json').read_text(encoding='utf-8'))
 for r in report['results']:
  im=Image.open(r['source']).convert('L');p=snap.classify(np.asarray(im,np.float32)/255)
  assert p['status']=='active',(r['name'],p)
  assert (p['action']!='discard')==r['same_view']['keep'],r['name']
  assert abs(p['screw_margin']-r['same_view']['margin'])<1e-5,r['name']
 print('PASS: all 114 cached test crops match offline DINO decisions',flush=True)
 bad=MODEL_ROOT/'invalid-bank';bad.mkdir();invalid=copy.deepcopy(snap.manifest);invalid['example_bank']['screw']['embeddings'][0]=[0]*384
 (bad/'manifest.json').write_text(json.dumps(invalid),encoding='utf-8');os.link(source/version/'model.onnx',bad/'model.onnx')
 with app.test_client() as client:
  models=client.get('/api/settings/models').json['models'];assert any(x['backend']=='dino_onnx' for x in models)
  a=client.post('/api/settings/models/select',json={'directory':version});assert a.status_code==200,a.json;assert a.json['model']['mode']=='auto_filter'
  fresh=ModelManager(MODEL_ROOT).snapshot();assert not fresh.error and fresh.requested==version
  pointer=(MODEL_ROOT/'active.json').read_bytes()
  failure=client.post('/api/settings/models/select',json={'directory':'invalid-bank'});assert failure.status_code==400
  assert (MODEL_ROOT/'active.json').read_bytes()==pointer
  assert client.post('/api/settings/models/select',json={'directory':clip}).status_code==200
  assert ModelManager(MODEL_ROOT).snapshot().requested==clip
  assert 'dino_onnx' in client.get('/static/settings.js').text
  assert 'DINO' in client.get('/engineer?tab=ai').text
 failed=Snapshot(snap.manifest,'broken',object()).classify(np.ones((40,40),np.float32));assert failed['status']=='error' and failed['action']=='manual_review'
 print('PASS: UI listing/select, reload persistence, CLIP switch-back, invalid bank rollback, inference failure retains candidate',flush=True)
if __name__=='__main__':
 if '--child' in sys.argv:child()
 else:
  pointer=ROOT/'models/active.json';before=pointer.read_bytes()
  with tempfile.TemporaryDirectory(prefix='xray-dino-verify-') as tmp:
   root=Path(tmp);config=root/'station.json';config.write_text(json.dumps(dict(workspace=str(root/'work'),model_root=str(root/'models'),allow_cpu_fallback=True,default_provider='cpu')),encoding='utf-8')
   env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'work'))
   subprocess.run([sys.executable,__file__,'--child'],env=env,cwd=ROOT,check=True)
  assert pointer.read_bytes()==before
