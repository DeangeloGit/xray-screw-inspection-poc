"""Verify cached pixels and CPU/GPU decisions against the fixed59-case experiment."""
import sys,json,hashlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from experiments.dino.prepared_pair import PreparedPair
from experiments.dino.contrast_pair_pilot import adjust
from experiments.dino.recenter_local_pilot import extract
from dino_adapter import input_image

def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--gpu',action='store_true');parser.add_argument('--gpu-api',choices=['cuda','directml'],default='cuda');parser.add_argument('--fixed-shape',action='store_true');parser.add_argument('--output',type=Path);parser.add_argument('--cpu-inference',action='store_true');args=parser.parse_args()
 out=args.output or ROOT/'workspace/dino-speed-verification-20261103';out.mkdir(parents=True,exist_ok=True)
 base=json.loads((ROOT/'workspace/dino-learn-joint-20261103/results.json').read_text(encoding='utf-8'))
 prior=ROOT/'workspace/dino-four-remaining-20261103'
 expected=json.loads((prior/'restricted-results.json').read_text(encoding='utf-8'))
 model=ROOT/'models/dino-paired-47-20261103';m=json.loads((model/'manifest.json').read_text(encoding='utf-8'))
 # Exercise cache boundaries using actual fixed-case photos, with exact pixel equality.
 cache=PreparedPair();pixel_tests=[];last_source=None;frozen_input_changes=[]
 geometry=json.loads((prior/'geometry.json').read_text(encoding='utf-8'))
 for z in base:
  source=z['source']
  if source!=last_source:
   ref,tar=[np.asarray(Image.open(Path(source)/f).convert('L'),np.float32)/255 for f in ['reference.png','aligned.png']];last_source=source
  original=[(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in [ref,tar]]
  prepared=cache.get(ref,tar);reused=cache.get(ref,tar)
  assert prepared is reused
  assert all(np.array_equal(a,b) for a,b in zip(prepared,original))
  x,y,w,h=[z['c'][k] for k in ['x','y','w','h']];region=(slice(max(0,y-12),y+h+12),slice(max(0,x-12),x+w+12))
  for side,a,b in zip(['reference','target'],prepared,original):
   new=adjust(input_image(m,a[region]));old=adjust(input_image(m,b[region]));assert new.tobytes()==old.tobytes()
   e=expected[z['number']-1]
   if e['rechecked']:
    box=geometry[z['number']-1]['crop_box'];new=adjust(input_image(m,a[box[1]:box[3],box[0]:box[2]]))
   if hashlib.sha256(new.tobytes()).hexdigest()!=e['input_hashes'][side]:frozen_input_changes.append(dict(number=z['number'],side=side))
  pixel_tests.append(z['key'])
 # A reused array object after a new-photo reset must not retain stale prepared pixels.
 probe=np.zeros((128,128),np.float32);cache.clear();cache.get(probe,probe);probe[:]=.5;cache.clear()
 assert np.array_equal(cache.get(probe,probe)[0],(np.clip(probe,0,1)*255).astype('uint8').astype('float32')/255)
 proof=dict(cases=len(pixel_tests),prepared_pixels_identical=True,same_pair_reuses_arrays=True,new_photo_and_explicit_reset_verified=True,frozen_final_input_changes=frozen_input_changes)
 (out/'pixel-verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(proof,flush=True)
 assert not frozen_input_changes,frozen_input_changes
 if not args.gpu and not args.cpu_inference:return
 import onnxruntime as ort
 ep=('DmlExecutionProvider' if args.gpu_api=='directml' else 'CUDAExecutionProvider') if args.gpu else 'CPUExecutionProvider';adapter=None;epoptions={}
 options=ort.SessionOptions();options.intra_op_num_threads=4;options.enable_profiling=True;options.profile_file_prefix=str(out/'gpu-placement')
 if args.fixed_shape:
  for dim,value in [('batch_size',1),('num_channels',3),('height',224),('width',224)]:options.add_free_dimension_override_by_name(dim,value)
 if args.gpu and args.gpu_api=='directml':
  from experiments.dino.dxgi_adapters import nvidia_adapter
  adapter=nvidia_adapter();options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;epoptions={'device_id':str(adapter['index'])}
 elif args.gpu:ort.preload_dlls(directory='');epoptions={'use_tf32':'0'}
 assert ep in ort.get_available_providers()
 session=ort.InferenceSession(str(model/'model.onnx'),sess_options=options,providers=[(ep,epoptions),'CPUExecutionProvider'] if args.gpu else ['CPUExecutionProvider']);session.disable_fallback()
 assert session.get_providers()[0]==ep
 name=session.get_inputs()[0].name
 # Profile just one representative pass to prove kernels actually execute on CUDA.
 sample=Image.open(prior/'images/1-final-target.png').convert('RGB');a=np.asarray(sample,np.float32)/255;a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
 session.run(None,{name:a.transpose(2,0,1)[None]});profilepath=session.end_profiling()
 events=json.loads(Path(profilepath).read_text(encoding='utf-8'));placement={};ops={}
 for e in events:
  provider=e.get('args',{}).get('provider')
  if provider:placement[provider]=placement.get(provider,0)+1;ops.setdefault(provider,set()).add(e.get('args',{}).get('op_name',''))
 assert placement.get(ep,0)>0,placement
 bank=np.load(ROOT/'workspace/dino-contrast-pair-20261103/bank-features.npz')['bank'];labels=np.r_[np.ones(47,bool),np.zeros(65,bool)]
 def classify(im):
  a=np.asarray(im,np.float32)/255;a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
  raw=session.run(None,{name:a.transpose(2,0,1)[None]})[0][0];v=np.stack([raw[0],raw[1:].mean(axis=0)]);v/=np.linalg.norm(v,axis=1)[:,None]
  scores=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
  margin=sum(float(np.sort(s[labels])[-3:].mean()-np.sort(s[~labels])[-3:].mean()) for s in scores)/2
  return dict(screw=margin>=0,margin=margin)
 rows=[];input_differences=[]
 for z,b in zip(base,expected):
  n=z['number'];ref,tar=[np.asarray(Image.open(Path(z['source'])/f).convert('L'),np.float32)/255 for f in ['reference.png','aligned.png']]
  cache.clear();arrays=cache.get(ref,tar)
  x,y,w,h=[z['c'][k] for k in ['x','y','w','h']];region=(slice(max(0,y-12),y+h+12),slice(max(0,x-12),x+w+12))
  inputs=[adjust(input_image(m,im[region])) for im in arrays];pair=[classify(im) for im in inputs];recheck=False
  if all(p['screw'] for p in pair):
   ex=extract(*arrays,z['c']);valid=False
   if ex.get('valid'):
    bx,by,s=ex['box'];box=[bx-2,by-2,bx+s+2,by+s+2];e=32
    search=[max(e,x-e),max(e,y-e),min(ref.shape[1]-e,x+w+e),min(ref.shape[0]-e,y+h+e)]
    ox,oy,ow,oh=ex['object_box'];touch=ox<=search[0] or oy<=search[1] or ox+ow>=search[2] or oy+oh>=search[3]
    valid=ex['metrics']['context_reliable'] and ex['area']>=12 and not touch and min(box)>=0 and box[2]<=ref.shape[1] and box[3]<=ref.shape[0]
   if valid:
    inputs=[adjust(input_image(m,im[box[1]:box[3],box[0]:box[2]])) for im in arrays];pair=[classify(im) for im in inputs];recheck=True
  pair=dict(reference=pair[0],target=pair[1],keep=pair[1]['screw'] and not pair[0]['screw'])
  for side,im in zip(['reference','target'],inputs):
   if hashlib.sha256(im.tobytes()).hexdigest()!=b['input_hashes'][side]:input_differences.append(dict(number=n,side=side))
  changed=[s for s in ['reference','target'] if pair[s]['screw']!=b['new'][s]['screw']]
  rows.append(dict(number=n,key=z['key'],group=z['group'],new=pair,rechecked=recheck,baseline=b['new'],changed=changed,max_margin_delta=max(abs(pair[s]['margin']-b['new'][s]['margin']) for s in ['reference','target'])))
 summary=dict(pixel_proof=proof,provider=session.get_providers(),gpu_adapter=adapter,fixed_shape=args.fixed_shape,session_input_shape=session.get_inputs()[0].shape,gpu_kernel_events=placement,ops={k:sorted(v) for k,v in ops.items()},decision_changes=[r['number'] for r in rows if r['changed'] or r['new']['keep']!=r['baseline']['keep']],input_differences=input_differences,max_margin_delta=max(r['max_margin_delta'] for r in rows),normal_false_alarms=sum(r['new']['keep'] for r in rows if r['group']=='normal'),protected_screws={str(n):rows[n-1]['new']['keep'] for n in [1,2,3,4,6,8]},model_sha256=hashlib.sha256((model/'model.onnx').read_bytes()).hexdigest())
 prefix='gpu' if args.gpu else 'cpu'
 (out/f'{prefix}-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');(out/f'{prefix}-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False),flush=True)
 assert not summary['decision_changes'],summary
 assert not input_differences,input_differences
 assert summary['normal_false_alarms']==0 and all(summary['protected_screws'].values())
if __name__=='__main__':main()
