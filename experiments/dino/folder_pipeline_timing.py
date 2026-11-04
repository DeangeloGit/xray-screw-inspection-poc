"""One-photo folder-to-result profile, real importer and isolated state only."""
import os,sys,json,time,hashlib,inspect,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))

def worker(config_path,stats_path):
 start=time.perf_counter()
 from acquisition import Importer
 c=json.loads(Path(config_path).read_text(encoding='utf-8'))
 imp=Importer(config=c['acquisition'],data=c['data'],state=c['state'],recover=False)
 lines,first=inspect.getsourcelines(Importer.scan_once);code=Importer.scan_once.__code__
 def line(s):return next(first+i for i,v in enumerate(lines) if s in v)
 inventory=line('inventory =');copy_start=line('sha = hashlib.sha256');copy_end=line('after = path.stat')
 validate_end=line('os.replace(partial, local)');commit_end=line('db.commit()')
 stats={};last=[None,None]
 def stage(n):
  if n==inventory:return 'folder_enumeration_and_stat'
  if copy_start<=n<copy_end:return 'copy_and_sha256'
  if copy_end<=n<validate_end:return 'image_integrity_and_decode'
  if validate_end<=n<=commit_end:return 'import_commit'
  return 'inventory_database_and_checks'
 def trace(frame,event,arg):
  if frame.f_code is code and event in ('line','return'):
   now=time.perf_counter()
   if last[0] is not None:
    key=stage(last[0]);stats[key]=stats.get(key,0)+now-last[1]
   last[:]=[frame.f_lineno,now] if event=='line' else [None,None]
  return trace if frame.f_code is code else None
 t=time.perf_counter();sys.settrace(trace)
 try:imp.scan_once()
 finally:sys.settrace(None)
 scan=time.perf_counter()-t
 result=dict(scan_seconds=scan,worker_seconds=time.perf_counter()-start,sections_seconds=stats,status=imp.status)
 Path(stats_path).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(imp.status,ensure_ascii=False))

def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--prepare-once',action='store_true');parser.add_argument('--gpu',action='store_true');parser.add_argument('--gpu-api',choices=['cuda','directml','worker'],default='cuda');parser.add_argument('--fixed-shape',action='store_true');parser.add_argument('--cpu-reuse',choices=['off','cold','warm'],default='off');args=parser.parse_args()
 setup_start=time.perf_counter()
 mode=('gpu-'+args.gpu_api if args.gpu else 'cpu')+('-prepared-once' if args.prepare_once else '-original')
 if args.fixed_shape:mode+='-fixed-shape'
 if args.cpu_reuse!='off':mode+='-cpu-reuse-'+args.cpu_reuse
 OUT=ROOT/'workspace'/('dino-folder-timing-'+time.strftime('%Y%m%d-%H%M%S')+'-'+mode)
 runtime=OUT/'runtime';source=OUT/'source';source.mkdir(parents=True)
 os.environ['XRAY_WORKSPACE']=str(runtime)
 # No production settings/state are loaded into this worker's runtime.
 import numpy as np
 import onnxruntime as ort
 import detector,library
 from acquisition import Importer
 from model_manager import Snapshot
 from dino_adapter import input_image
 from experiments.dino.contrast_pair_pilot import adjust
 from experiments.dino.recenter_local_pilot import extract
 from experiments.dino.prepared_pair import PreparedPair
 MODEL=ROOT/'models/dino-paired-47-20261103'
 ref=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/OK/cnd64409dv.tiff')
 original=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/NG/CND6440DTD_2026_11_03_09_57_57_32.tiff')
 settings=ROOT/'workspace/windows-check/state/ui_settings.json'
 actual=json.loads(settings.read_text(encoding='utf-8')).get('acquisition',{})
 cfg=dict(actual,source=str(source),enabled=True,poll_seconds=float(actual.get('poll_seconds',3)),stable_seconds=float(actual.get('stable_seconds',15)))
 protected=[ROOT/'models/active.json',MODEL/'manifest.json',MODEL/'model.onnx',settings,ref,original]+[ROOT/p for p in ['acquisition.py','library.py','detector.py','dino_adapter.py','static/user.js']]
 before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
 m=json.loads((MODEL/'manifest.json').read_text(encoding='utf-8'))
 t=time.perf_counter();opt=ort.SessionOptions();opt.intra_op_num_threads=4
 if args.fixed_shape:
  for dim,value in [('batch_size',1),('num_channels',3),('height',224),('width',224)]:opt.add_free_dimension_override_by_name(dim,value)
 provider=('DmlExecutionProvider' if args.gpu_api in ('directml','worker') else 'CUDAExecutionProvider') if args.gpu else 'CPUExecutionProvider';adapter=None
 if args.gpu and args.gpu_api=='cuda':
  ort.preload_dlls(directory='')
  if provider not in ort.get_available_providers():raise RuntimeError('CUDA provider unavailable; do not report CPU fallback as GPU')
 if args.gpu and args.gpu_api=='directml':
  from experiments.dino.dxgi_adapters import nvidia_adapter
  adapter=nvidia_adapter();opt.enable_mem_pattern=False;opt.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
  providers=[(provider,{'device_id':str(adapter['index'])}),'CPUExecutionProvider']
 else:providers=[(provider,{'use_tf32':'0'}),'CPUExecutionProvider'] if args.gpu else [provider]
 if args.gpu and args.gpu_api=='worker':
  from gpu_runtime import GpuSession
  session=GpuSession(MODEL/'model.onnx',m['sha256']);adapter=dict(name=session.device)
 else:
  session=ort.InferenceSession(str(MODEL/'model.onnx'),sess_options=opt,providers=providers);session.disable_fallback()
 assert session.get_providers()[0]==provider,session.get_providers()
 model_load=time.perf_counter()-t
 t=time.perf_counter();bank=np.load(ROOT/'workspace/dino-contrast-pair-20261103/bank-features.npz')['bank'];bank_load=time.perf_counter()-t
 labels=np.r_[np.ones(47,bool),np.zeros(65,bool)];inputname=session.get_inputs()[0].name
 t=time.perf_counter();session.run(None,{inputname:np.zeros((1,3,224,224),np.float32)});warmup=time.perf_counter()-t
 ai={};stages={};counts=dict(inferences=0,geometry_attempts=0,rechecks=0);candidates=[];prepared=PreparedPair();current_inputs={}
 def add(bucket,key,start):bucket[key]=bucket.get(key,0)+time.perf_counter()-start
 def classify(crop,side,phase):
  t=time.perf_counter();im=adjust(input_image(m,crop));a=np.asarray(im,np.float32)/255
  current_inputs[phase+'_'+side]=hashlib.sha256(im.tobytes()).hexdigest()
  a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32);a=a.transpose(2,0,1)[None];add(ai,'crop_resize_contrast_normalize',t)
  t=time.perf_counter();raw=session.run(None,{inputname:a})[0][0];elapsed=time.perf_counter()-t
  key=phase+'_'+side+'_inference';ai[key]=ai.get(key,0)+elapsed;counts['inferences']+=1
  t=time.perf_counter();v=np.stack([raw[0],raw[1:].mean(axis=0)]);v/=np.linalg.norm(v,axis=1)[:,None]
  scores=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
  margin=sum(float(np.sort(s[labels])[-3:].mean()-np.sort(s[~labels])[-3:].mean()) for s in scores)/2;add(ai,'feature_pool_and_example_comparison',t)
  return dict(screw=margin>=0,margin=margin)
 def experiment(snapshot,target,reference,c):
  current_inputs.clear()
  start=time.perf_counter();t=time.perf_counter()
  arrays=prepared.get(reference,target) if args.prepare_once else [(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in [reference,target]]
  x,y,w,h=[c[k] for k in ['x','y','w','h']];region=(slice(max(0,y-12),y+h+12),slice(max(0,x-12),x+w+12));add(ai,'full_frame_quantization_per_candidate',t)
  pair=[classify(im[region],side,'base') for im,side in zip(arrays,['reference','target'])];recheck=False
  if all(p['screw'] for p in pair):
   t=time.perf_counter();counts['geometry_attempts']+=1;ex=extract(*arrays,c);valid=False
   if ex.get('valid'):
    bx,by,s=ex['box'];box=[bx-2,by-2,bx+s+2,by+s+2];e=32
    search=[max(e,x-e),max(e,y-e),min(reference.shape[1]-e,x+w+e),min(reference.shape[0]-e,y+h+e)]
    ox,oy,ow,oh=ex['object_box'];touch=ox<=search[0] or oy<=search[1] or ox+ow>=search[2] or oy+oh>=search[3]
    valid=ex['metrics']['context_reliable'] and ex['area']>=12 and not touch and min(box)>=0 and box[2]<=reference.shape[1] and box[3]<=reference.shape[0]
   add(ai,'local_geometry_checks',t)
   if valid:
    pair=[classify(im[box[1]:box[3],box[0]:box[2]],side,'recheck') for im,side in zip(arrays,['reference','target'])];recheck=True;counts['rechecks']+=1
  keep=pair[1]['screw'] and not pair[0]['screw'];candidates.append(dict(id=c['id'],seconds=time.perf_counter()-start,recheck=recheck,input_hashes=dict(current_inputs)))
  if len(candidates)%30==0:print(f'AI completed {len(candidates)} candidates',flush=True)
  return dict(action='manual_review' if keep else 'discard',label='screw' if keep else 'non_screw',status='active',reference=pair[0],target=pair[1],rechecked=recheck,offline_experiment=True)
 def timed(name,fn):
  def call(*a,**kw):
   t=time.perf_counter()
   try:return fn(*a,**kw)
   finally:add(stages,name,t)
  return call
 reuse=None;reference_preparation_seconds=0.
 if args.cpu_reuse!='off':
  from experiments.dino.cpu_reuse_pilot import CpuReuse
  reuse=CpuReuse(detector,ref).install()
  if args.cpu_reuse=='warm':
   t=time.perf_counter();reuse.prepare_reference();reference_preparation_seconds=time.perf_counter()-t
 for name in ['read','register','refine','proposals','legacy_proposals','write_image']:
  setattr(detector,name,timed(name,getattr(detector,name)))
 detector.classify_dino_candidate=timed('ai_total',experiment)
 library.detect=timed('detector_total',detector.detect)
 for name in ['digest','save_result','remember_result','record_analysis_failure']:
  setattr(library,name,timed('library_'+name,getattr(library,name)))
 snap=Snapshot(dict(m,model_id='offline-contrast-restricted-recheck'),'offline-profile-folder-latest',session)
 library.manager.snapshot=lambda *a,**k:snap
 profile=dict(id='MPT12-timing',name='MPT12',reference=str(ref),reference_sha256=before[str(ref)])
 configfile=OUT/'worker-config.json';configfile.write_text(json.dumps(dict(acquisition=cfg,data=str(runtime/'data'),state=str(runtime/'state'))),encoding='utf-8')
 result_box={};events=[];scans=[];sleeps=[]
 def analyze(path,filename):
  prepared.clear()
  begin=time.perf_counter();events.append(dict(event='analysis_start',seconds=begin-origin))
  result_box['result']=library.analyze_file(path,filename,threshold=.13,profile=profile)
  result_box['analysis_seconds']=time.perf_counter()-begin
  events.append(dict(event='result_saved',seconds=time.perf_counter()-origin))
 imp=Importer(config=cfg,data=runtime/'data',state=runtime/'state',analyze=analyze)
 # Stage original bytes before T0, then publish a completed file as an X-ray writer would.
 staged=source/(original.name+'.partial');shutil.copyfile(original,staged)
 setup_seconds=time.perf_counter()-setup_start
 origin=time.perf_counter();os.replace(staged,source/original.name)
 events.append(dict(event='completed_file_available',seconds=time.perf_counter()-origin))
 while not result_box:
  i=len(scans)+1;statsfile=OUT/f'scan-{i}.json';t=time.perf_counter()
  command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(configfile),str(statsfile)]
  run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=float(cfg.get('scan_timeout_seconds',30)),env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8'))
  elapsed=time.perf_counter()-t
  if run.returncode:raise RuntimeError(run.stderr)
  stats=json.loads(statsfile.read_text(encoding='utf-8'));stats.update(parent_wall_seconds=elapsed,start_seconds=t-origin,end_seconds=time.perf_counter()-origin);scans.append(stats)
  events.append(dict(event=f'scan_{i}_complete',seconds=time.perf_counter()-origin))
  imp.process_pending()
  if not result_box:
   if time.perf_counter()-origin>120:raise RuntimeError('Importer did not produce result: '+str(imp.info()))
   t=time.perf_counter();time.sleep(max(1,cfg['poll_seconds']));sleeps.append(time.perf_counter()-t)
 ready=time.perf_counter();t=time.perf_counter();loaded=library.latest_results(profile);retrieve=time.perf_counter()-t
 r=result_box['result'];assert r['source_sha256'] in loaded
 total=time.perf_counter()-origin;events.append(dict(event='saved_result_retrieved',seconds=total))
 assert imp.info()['event_counts']=={'done':1}
 assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items())
 scan_total=sum(s['parent_wall_seconds'] for s in scans);sleep_total=sum(sleeps)
 detail_sum=sum(ai.values());detector_parts=sum(stages.get(k,0) for k in ['read','register','refine','proposals','legacy_proposals','write_image','ai_total'])
 sections=[('資料夾掃描、取圖與匯入（含掃描程序啟動）',scan_total),('等待下一次掃描／檔案穩定',sleep_total),('讀取參照與待測照片',stages['read']),('整張照片對齊',stages['register']),('局部對齊修正',stages['refine']),('差分找候選（含舊版核對候選）',stages['proposals']+stages['legacy_proposals']),('準備AI影像與小圖',ai.get('full_frame_quantization_per_candidate',0)+ai.get('crop_resize_contrast_normalize',0)),('DINO看參照圖',ai.get('base_reference_inference',0)),('DINO看待測圖',ai.get('base_target_inference',0)),('與47＋65張範例比較',ai.get('feature_pool_and_example_comparison',0)),('額外補查：定位與AI',ai.get('local_geometry_checks',0)+ai.get('recheck_reference_inference',0)+ai.get('recheck_target_inference',0)),('AI其他整理',stages['ai_total']-detail_sum),('儲存標示圖與候選圖片',stages['write_image']),('其他檢測整理與結果檔',stages['detector_total']-detector_parts),('登記檢測結果與檢查紀錄',result_box['analysis_seconds']-stages['detector_total']),('取圖佇列收尾與讀回結果',total-scan_total-sleep_total-result_box['analysis_seconds'])]
 assert abs(sum(t for _,t in sections)-total)<.00001
 previous=json.loads((ROOT/'workspace/dino-single-image-timing-20261103/latest_offline_experiment/result.json').read_text(encoding='utf-8'))
 def decisions(z):return {c['id']:c['classification']['action'] for k in ['candidates','filtered_candidates'] for c in z[k]}
 same=decisions(previous)==decisions(r)
 def by_id(z):return {c['id']:c for k in ['candidates','filtered_candidates'] for c in z[k]}
 pmap,rmap=by_id(previous),by_id(r)
 pair_changes=[i for i in pmap if any(pmap[i]['classification'][s]['screw']!=rmap[i]['classification'][s]['screw'] for s in ['reference','target'])]
 max_margin_delta=max(abs(pmap[i]['classification'][s]['margin']-rmap[i]['classification'][s]['margin']) for i in pmap for s in ['reference','target'])
 output=dict(total_seconds=total,analysis_seconds=result_box['analysis_seconds'],folder_to_analysis_seconds=events[next(i for i,e in enumerate(events) if e['event']=='analysis_start')]['seconds'],sections=[dict(name=n,seconds=v) for n,v in sections],events=events,scans=scans,wait_intervals_seconds=sleeps,detector_stage_seconds=stages,ai_stage_seconds=ai,candidate_timings=candidates,counts=counts,candidates=r['pre_ai_count'],retained=r['proposal_count'],source_shape=r['source_shape'],source_file=original.name,original_source=str(original),benchmark_source=str(source),reference=str(ref),poll_seconds=cfg['poll_seconds'],stable_seconds=cfg['stable_seconds'],setup_seconds=setup_seconds,model_load_seconds=model_load,bank_load_seconds=bank_load,warmup_seconds=warmup,result_retrieval_seconds=retrieve,result_path=str(runtime/'outputs'/r['name']/'result.json'),same_decisions_as_previous=same,protected_unchanged=True,model_preloaded=True,cpu_threads=4,provider='CPUExecutionProvider',scope='One completed file in isolated local folder. Actual Importer scan_once and process_pending plus library.analyze_file, latest offline classification, saved result readback. No queue, no network share, no browser repaint, no query feature cache. Includes real stable15s/poll3s waits; prepared example features loaded before arrival. Scan uses narrow Python line tracing, so small measurement overhead is included.')
 output.update(mode=mode,provider=provider,gpu_adapter=adapter,session_providers=session.get_providers(),onnxruntime_version=ort.__version__,prepare_once=args.prepare_once,fixed_shape=args.fixed_shape,session_input_shape=session.get_inputs()[0].shape,frame_conversions=prepared.conversions if args.prepare_once else 2*len(candidates),reference_target_decision_changes=pair_changes,max_margin_delta=max_margin_delta)
 if args.gpu and args.gpu_api=='worker':
  output['parent_onnxruntime_version']=ort.__version__;output['onnxruntime_version']=session.runtime_version
 output.update(cpu_reuse=args.cpu_reuse,reference_preparation_seconds=reference_preparation_seconds,reuse_stats=reuse.stats if reuse else None)
 (OUT/'timing.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'preservation.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(report_directory=str(OUT),total_seconds=total,sections=sections,counts=counts,same_decisions_as_previous=same),ensure_ascii=False),flush=True)

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--worker':worker(sys.argv[2],sys.argv[3])
 else:main()
