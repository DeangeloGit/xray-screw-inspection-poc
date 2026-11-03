"""Install the evaluated DINO example bank without changing active.json."""
import hashlib,json,shutil,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime_paths import MODEL_ROOT
from model_manager import ModelManager
from dino_adapter import POLICY
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def install():
 source=ROOT/'workspace/dino-experiment-20261103';report=read(source/'result.json');features=np.load(source/'features.npz');rows=read(ROOT/'workspace/windows-check/diagnostics/clip-screw-examples/features.json')
 digest=hashlib.sha256((source/'model.onnx').read_bytes()).hexdigest();assert digest==report['model_sha256']
 bank={}
 for label in ('screw','normal'):
  ids=[r['name'] for r in rows if r['split']=='bank' and r['label']==label]
  bank[label]=dict(ids=ids,embeddings=[features[n+'_same_view'].tolist() for n in ids])
 m=dict(schema_version=1,model_id='DINOv2 螺絲範例版（實驗版）',backend='dino_onnx',preprocessing='aligned-gray-tight12-v1',classes=['screw','non_screw'],input_size=[224,224],file='model.onnx',sha256=digest,provider_policy='cpu',mean=[.485,.456,.406],std=[.229,.224,.225],resize_shortest=224,neighbors=3,decision_margin=0,decision_policy=POLICY,example_bank=bank,provenance=dict(repository=report['repository'],revision=report['revision'],experiment='dino-experiment-20261103',mode='same_view',note='Only bank partition; no validation crops. Installed without activation.'))
 payload=json.dumps(m,ensure_ascii=False,sort_keys=True).encode('utf-8');version='dino-examples-'+hashlib.sha256(payload).hexdigest()[:12];directory=MODEL_ROOT/version
 active=MODEL_ROOT/'active.json';before=active.read_bytes() if active.exists() else None
 if directory.exists():assert (directory/'manifest.json').read_bytes()==payload
 else:
  directory.mkdir(parents=True);shutil.copyfile(source/'model.onnx',directory/'model.onnx');(directory/'manifest.json').write_bytes(payload)
 snapshot=ModelManager(MODEL_ROOT,allow_cpu=True).snapshot(version);assert not snapshot.error,snapshot.error
 assert (active.read_bytes() if active.exists() else None)==before
 print(json.dumps(dict(directory=version,model=snapshot.info(),activated=False),ensure_ascii=False))
 return version
if __name__=='__main__':install()
