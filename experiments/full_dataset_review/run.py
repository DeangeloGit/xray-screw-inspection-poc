"""Frozen full V10 production-pipeline evaluation, with no station mutations."""
import sys,os,json,hashlib,subprocess,traceback,time
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ProcessPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import cv2
from detector import detect,DETECTOR_VERSION
from model_manager import ModelManager

PROJECT=Path(__file__).resolve().parents[2]
SOURCE=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray')
OUT=PROJECT/'workspace/windows-check/diagnostics/v10-full-evaluation-20261103'
MODEL='clip-tight-bf6e136950a6'
_snapshot=None

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def worker(item):
    global _snapshot
    cv2.setNumThreads(2)
    folder=OUT/'photos'/item['sha256'];folder.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    try:
        if _snapshot is None:
            _snapshot=ModelManager(PROJECT/'models',allow_cpu=True).snapshot(MODEL)
            if _snapshot.error or _snapshot.manifest['backend']!='clip_onnx':raise RuntimeError('Pinned CLIP model unavailable: '+str(_snapshot.info()))
        if _snapshot.identity!=item['model_fingerprint']:raise RuntimeError('Model changed during batch')
        if digest(item['path'])!=item['sha256'] or digest(item['reference'])!=item['reference_sha256']:raise RuntimeError('Input changed during batch')
        result=detect(item['reference'],item['path'],'evaluation_'+item['sha256'][:16],.13,
                      model_snapshot=_snapshot,output_directory=folder)
        classes=[c['classification'] for c in result['candidates']]
        row=dict(item,success=True,seconds=round(time.monotonic()-started,2),
                 count=result['proposal_count'],high=result['high_count'],review=result['review_count'],
                 wire=result['wire_review_count'],alignment_warning=result['alignment_warning'],
                 mirrored=result['mirrored_input'],structure_changes=result['structure_change_count'],
                 ai_screw=sum(c.get('label')=='screw' and c.get('status')=='shadow' for c in classes),
                 ai_uncertain=sum(c.get('filter_recommendation')=='review' for c in classes),
                 ai_non_screw=sum(c.get('filter_recommendation')=='non_screw_suggestion' for c in classes),
                 ai_error=sum(c.get('status')=='error' for c in classes))
    except Exception as error:
        row=dict(item,success=False,seconds=round(time.monotonic()-started,2),error=str(error))
        (folder/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
    (folder/'evaluation.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    return row

def main():
    assert DETECTOR_VERSION==10,'This evaluation is pinned to V10'
    OUT.mkdir(parents=True,exist_ok=True)
    old=json.loads((PROJECT/'workspace/windows-check/diagnostics/collected-data/benchmark-plan.json').read_text(encoding='utf-8'))
    refs={model:Path(row['path']) for model,row in old['references'].items()}
    refs['MPT12']=SOURCE/'MPT12/OK/cnd64409qy.tiff'
    model=ModelManager(PROJECT/'models',allow_cpu=True).snapshot(MODEL)
    if model.error:raise RuntimeError(model.error)
    code={name:digest(PROJECT/name) for name in ['detector.py','registration_candidate.py','single_reference_evidence.py','wire_review.py','model_manager.py','model_adapters.py']}
    refrows={model:dict(path=str(path),sha256=digest(path)) for model,path in refs.items()}
    items=[]
    for path in sorted(SOURCE.rglob('*')):
        if path.suffix.lower() not in ('.png','.tif','.tiff','.jpg','.jpeg'):continue
        relative=path.relative_to(SOURCE);machine,label,*_=relative.parts
        if label not in ('OK','NG'):raise ValueError('Unrecognized dataset label: '+str(path))
        sha=digest(path);reference=refrows[machine]
        items.append(dict(path=str(path),relative=relative.as_posix(),machine=machine,label=label,
            sha256=sha,reference=reference['path'],reference_sha256=reference['sha256'],
            is_reference=sha==reference['sha256'],model_fingerprint=model.identity,
            previously_deferred=path.name=='CND6440DTD_2026_11_02_17_14_35_98.tiff'))
    identity=dict(code=code,model=model.info(),references=refrows,threshold=.13,version=10,
                  inputs=[(r['relative'],r['sha256']) for r in items])
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    plan=dict(identity,run_fingerprint=fingerprint,created_utc=datetime.now(timezone.utc).isoformat(),
              git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT).decode().strip(),
              source=str(SOURCE),items=items)
    if (OUT/'plan.json').exists():
        previous=json.loads((OUT/'plan.json').read_text(encoding='utf-8'))
        if previous['run_fingerprint']!=fingerprint:raise RuntimeError('Frozen batch differs; use a new output directory')
    else:(OUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    pending=[r for r in items if not (OUT/'photos'/r['sha256']/'evaluation.json').exists()]
    # Expensive NG photos start early; reference self-checks remain labeled separately.
    pending.sort(key=lambda r:(r['label']!='NG',r['relative']))
    print('START',len(items),'images;',len(pending),'pending;',model.info(),flush=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(worker,item):item for item in pending}
        for n,future in enumerate(as_completed(tasks),1):
            row=future.result()
            print(n,'/',len(pending),row['relative'],'candidates='+str(row.get('count')),'high='+str(row.get('high')),'seconds='+str(row['seconds']),row.get('error',''),flush=True)
    records=[json.loads((OUT/'photos'/r['sha256']/'evaluation.json').read_text(encoding='utf-8')) for r in items]
    assert all(digest(PROJECT/name)==value for name,value in code.items()),'Code changed during batch'
    assert all(digest(r['path'])==r['sha256'] for r in items),'Dataset changed during batch'
    (OUT/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('COMPLETE',len(records),'success',sum(r['success'] for r in records),'failed',sum(not r['success'] for r in records),flush=True)

if __name__=='__main__':main()
