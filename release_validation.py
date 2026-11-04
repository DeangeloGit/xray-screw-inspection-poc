"""Explicit one-photo parity diagnostic, usable by source and frozen distributions."""
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def run(config_path):
    import detector
    from model_manager import ModelManager
    from detection_runtime import prepare_reference
    cfg=load(config_path);out=Path(cfg['output']);out.mkdir(parents=True,exist_ok=False)
    snapshot=ModelManager(allow_cpu=True,execution_override=cfg['execution']).snapshot(cfg['model'])
    assert not snapshot.error,snapshot.info()
    calls=[];last=[];session=snapshot.session
    class TimedSession:
        def __getattr__(self,name):return getattr(session,name)
        def run(self,*a,**kw):
            t=time.perf_counter();result=session.run(*a,**kw);calls.append(time.perf_counter()-t);return result
    snapshot=replace(snapshot,session=TimedSession())
    prepare_reference(cfg['reference'],detector.read,detector.structure_mask,detector.machine_mask)
    original=detector.classify_dino_candidate
    def classified(*args):
        value=original(*args);last.append(time.perf_counter());return value
    detector.classify_dino_candidate=classified
    start=time.perf_counter()
    try:result=detector.detect(cfg['reference'],cfg['target'],'release-parity',model_snapshot=snapshot,output_directory=out/'images')
    finally:detector.classify_dino_candidate=original
    saved=time.perf_counter()-start;answer=max(last)-start
    prior_timing=load(cfg['golden']);prior=load(prior_timing['result_path'])
    fields=('matrix','rotation_ccw','mirrored_input','local_alignment','coverage','baseline_candidates','structure_changes','source_machine_bbox')
    changes=[key for key in fields if prior[key]!=result[key]]
    def byid(r):return {c['id']:c for group in ('candidates','filtered_candidates') for c in r[group]}
    a,b=byid(prior),byid(result);assert set(a)==set(b)
    boxes=[];decisions=[];inputs=[]
    golden_inputs={z['id']:z['input_hashes'] for z in prior_timing['candidate_timings']}
    for i in a:
        aa,bb=dict(a[i]),dict(b[i]);ca,cb=aa.pop('classification'),bb.pop('classification')
        if aa!=bb:boxes.append(i)
        pair=cb.get('paired_evidence',{})
        if cb['status']!='active' or cb['action']!=ca['action'] or any((pair.get(side,{}).get('label')=='screw')!=ca[side]['screw'] for side in ('reference','target')):decisions.append(i)
        initial=cb.get('paired_recheck',{}).get('initial',pair)
        hashes={'base_'+side:initial[side]['input_sha256'] for side in ('reference','target')}
        if cb.get('paired_recheck',{}).get('performed'):
            hashes.update({'recheck_'+side:pair[side]['input_sha256'] for side in ('reference','target')})
        if hashes!=golden_inputs[i]:inputs.append(i)
    def pngs(folder):return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(folder).glob('*.png')}
    ai,bi=pngs(Path(prior_timing['result_path']).parent),pngs(out/'images')
    images=[k for k in set(ai)|set(bi) if ai.get(k)!=bi.get(k)]
    report=dict(success=not any((changes,boxes,decisions,inputs,images)),model=snapshot.info(),pipeline=detector.PIPELINE,
                detector_version=detector.DETECTOR_VERSION,candidates=len(a),inferences=len(calls),
                start_to_dino_answer_seconds=answer,start_to_saved_seconds=saved,gpu_or_cpu_inference_calls_seconds=sum(calls),
                registration_or_audit_changes=changes,candidate_changes=boxes,decision_changes=decisions,input_changes=inputs,
                image_changes=images,images=len(bi),scope='One photo, ready reference and model, no folder wait; no production state written')
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    assert report['success'],report
    return report


if __name__=='__main__':
    import sys
    run(sys.argv[1])
