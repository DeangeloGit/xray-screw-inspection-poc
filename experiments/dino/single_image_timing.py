"""Isolated full-image timing; no production activation or stored-result reuse."""
import time
START=time.perf_counter()
import sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import onnxruntime as ort
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import detector
from model_manager import Snapshot
from dino_adapter import input_image
from experiments.dino.contrast_pair_pilot import adjust
from experiments.dino.recenter_local_pilot import extract
OUT=ROOT/'workspace/dino-single-image-timing-20261103'
MODEL=ROOT/'models/dino-paired-47-20261103'

def main():
 OUT.mkdir(exist_ok=True)
 protected=[ROOT/'models/active.json',MODEL/'manifest.json',MODEL/'model.onnx',ROOT/'detector.py',ROOT/'dino_adapter.py']
 hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
 m=json.loads((MODEL/'manifest.json').read_text(encoding='utf-8'))
 t=time.perf_counter();opts=ort.SessionOptions();opts.intra_op_num_threads=4
 session=ort.InferenceSession(str(MODEL/'model.onnx'),sess_options=opts,providers=['CPUExecutionProvider']);load=time.perf_counter()-t
 t=time.perf_counter();bank=np.load(ROOT/'workspace/dino-contrast-pair-20261103/bank-features.npz')['bank'];bankload=time.perf_counter()-t
 labels=np.r_[np.ones(47,bool),np.zeros(65,bool)]
 inpname=session.get_inputs()[0].name
 t=time.perf_counter();session.run(None,{inpname:np.zeros((1,3,224,224),np.float32)});warmup=time.perf_counter()-t
 counts={};stages={}
 def classify(crop):
  im=adjust(input_image(m,crop));a=np.asarray(im,np.float32)/255
  a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
  raw=session.run(None,{inpname:a.transpose(2,0,1)[None]})[0][0]
  counts['inferences']+=1
  v=np.stack([raw[0],raw[1:].mean(axis=0)]);v/=np.linalg.norm(v,axis=1)[:,None]
  scores=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
  margin=sum(float(np.sort(s[labels])[-3:].mean()-np.sort(s[~labels])[-3:].mean()) for s in scores)/2
  return dict(screw=margin>=0,margin=margin)
 def experiment(snapshot,target,reference,c):
  # Match saved PNG preprocessing in the offline experiments.
  arrays=[(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in [reference,target]]
  x,y,w,h=[c[k] for k in ['x','y','w','h']];region=(slice(max(0,y-12),y+h+12),slice(max(0,x-12),x+w+12))
  pair=[classify(im[region]) for im in arrays];recheck=False
  if all(p['screw'] for p in pair):
   counts['geometry_attempts']+=1;ex=extract(*arrays,c)
   if ex.get('valid'):
    bx,by,s=ex['box'];box=[bx-2,by-2,bx+s+2,by+s+2];e=32
    search=[max(e,x-e),max(e,y-e),min(reference.shape[1]-e,x+w+e),min(reference.shape[0]-e,y+h+e)]
    ox,oy,ow,oh=ex['object_box'];touch=ox<=search[0] or oy<=search[1] or ox+ow>=search[2] or oy+oh>=search[3]
    valid=ex['metrics']['context_reliable'] and ex['area']>=12 and not touch and min(box)>=0 and box[2]<=reference.shape[1] and box[3]<=reference.shape[0]
    if valid:
     pair=[classify(im[box[1]:box[3],box[0]:box[2]]) for im in arrays];recheck=True;counts['rechecks']+=1
  keep=pair[1]['screw'] and not pair[0]['screw']
  return dict(action='manual_review' if keep else 'discard',label='screw' if keep else 'non_screw',status='active',reference=pair[0],target=pair[1],rechecked=recheck,offline_experiment=True)
 originals={n:getattr(detector,n) for n in ['read','register','refine','proposals','legacy_proposals','write_image','classify_dino_candidate']}
 def timed(name,fn):
  def call(*a,**kw):
   t=time.perf_counter()
   try:return fn(*a,**kw)
   finally:stages[name]=stages.get(name,0)+time.perf_counter()-t
  return call
 for name,fn in originals.items():setattr(detector,name,timed(name,fn))
 reference=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/OK/cnd64409dv.tiff')
 target=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/NG/CND6440DTD_2026_11_03_09_57_57_32.tiff')
 hashes.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [reference,target]})
 setup=time.perf_counter()-START
 output=dict(reference=str(reference),target=str(target),provider='CPUExecutionProvider',threads=4,model_load_seconds=load,precomputed_bank_load_seconds=bankload,warmup_seconds=warmup,setup_seconds=setup,runs=[],scope='Full detector read-align-difference-classify-render-write on one photo per method, uncached query inference, model warmed; excludes UI/network/acquisition and initial example-bank generation.')
 for method in ['formal_r2','latest_offline_experiment']:
  stages.clear();counts.clear();counts.update(inferences=0,geometry_attempts=0,rechecks=0)
  detector.classify_dino_candidate=timed('classify_dino_candidate', originals['classify_dino_candidate'] if method=='formal_r2' else experiment)
  snap=Snapshot(dict(m,model_id=m['model_id'] if method=='formal_r2' else 'offline-contrast-restricted-recheck'),method,session)
  t=time.perf_counter();r=detector.detect(reference,target,method,.13,model_snapshot=snap,output_directory=OUT/method);elapsed=time.perf_counter()-t
  if method=='formal_r2':counts['inferences']=2*r['pre_ai_count']
  record=dict(method=method,total_seconds=elapsed,stages_seconds=dict(stages),counts=dict(counts),inference_count_basis='two per candidate from formal classify_pair' if method=='formal_r2' else 'counted at session.run',candidates=r['pre_ai_count'],retained=r['proposal_count'],source_shape=r['source_shape'])
  output['runs'].append(record);print(json.dumps(record),flush=True)
  (OUT/'timing.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
 assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
 output['protected_unchanged']=True
 (OUT/'timing.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(setup_seconds=setup,model_load_seconds=load,protected_unchanged=True)),flush=True)
if __name__=='__main__':main()
