"""Time existing alignment/difference calls without changing their calculations."""
import contextlib
import hashlib
import inspect
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import cv2
import numpy as np
import detector
import single_reference_evidence
import wire_review
from experiments.dino.cpu_reuse_pilot import CpuReuse
from experiments.dino.cpu_reuse_runs import protected

OUT=ROOT/'workspace/dino-alignment-difference-profile-20261104'


class Profiler:
    def __init__(self):
        self.stack=[];self.rows=defaultdict(lambda:dict(calls=0,inclusive=0.,exclusive=0.))
        self.undo=[];self.matches=[];self.orientations=[]

    def blocks(self,obj,name,source,groups):
        for first,last,label in groups:
            lines=source.splitlines(keepends=True)
            a=next(i for i,line in enumerate(lines) if line.strip()==first)
            b=next(i for i in range(a,len(lines)) if lines[i].strip()==last)
            indent=lines[a][:len(lines[a])-len(lines[a].lstrip())]
            lines[a:b+1]=[indent+f'with _step_profile.scope("{label}"):\n']+['    '+line for line in lines[a:b+1]]
            source=''.join(lines)
        old=getattr(obj,name)
        exec(compile(source,f'<step-timer:{name}>','exec'),obj.__dict__)
        self.undo.append((obj,name,old))

    @contextlib.contextmanager
    def scope(self,name):
        frame=dict(name=name,start=time.perf_counter(),children=0.)
        self.stack.append(frame)
        try:yield
        finally:
            elapsed=time.perf_counter()-frame['start'];self.stack.pop()
            row=self.rows[name];row['calls']+=1;row['inclusive']+=elapsed;row['exclusive']+=elapsed-frame['children']
            if self.stack:self.stack[-1]['children']+=elapsed

    def patch(self,obj,name,replacement):
        self.undo.append((obj,name,getattr(obj,name)));setattr(obj,name,replacement)

    def function(self,obj,name,label):
        fn=getattr(obj,name)
        def run(*args,**kwargs):
            with self.scope(label):
                answer=fn(*args,**kwargs)
            if name=='_register_orientation':
                self.orientations.append(dict(rotation=answer['rotation'],inliers=answer['inliers']))
            return answer
        self.patch(obj,name,run)

    def operation(self,obj,name):
        fn=getattr(obj,name)
        def run(*args,**kwargs):
            if not self.stack:return fn(*args,**kwargs)
            owner=self.stack[-1]['name']
            with self.scope(owner+' / '+name):
                return fn(*args,**kwargs)
        self.patch(obj,name,run)

    def factory(self,name,method):
        create=getattr(cv2,name);profiler=self
        class Proxy:
            def __init__(self,instance):self.instance=instance
            def __getattr__(self,attr):
                fn=getattr(self.instance,attr)
                if attr!=method:return fn
                def run(*args,**kwargs):
                    owner=profiler.stack[-1]['name'] if profiler.stack else 'setup'
                    with profiler.scope(owner+' / '+method):
                        result=fn(*args,**kwargs)
                    if method=='knnMatch':
                        profiler.matches.append(dict(query_features=len(args[0]),reference_features=len(args[1]),
                            pair_distance_upper_bound=len(args[0])*len(args[1]),nearest_neighbor_rows=len(result)))
                    return result
                return run
        self.patch(cv2,name,lambda *a,**k:Proxy(create(*a,**k)))

    def install(self,reuse):
        detector._step_profile=self;wire_review._step_profile=self
        source=inspect.getsource(reuse.original['_register_orientation']).replace(
            "kr, dr = orb.detectAndCompute((ref * 255).astype('uint8'), None)",
            'kr, dr = _cpu_reuse.reference_features(orb, ref)')
        self.blocks(detector,'_register_orientation',source,[
            ('rotated = np.rot90(raw, rotation).copy()','target = cv2.resize(rotated, None, fx=s, fy=s)','orientation_image_preparation'),
            ('good = [m for pair in pairs if len(pair) == 2','for m, n in [pair] if m.distance < 0.72 * n.distance]','filter_feature_pairs'),
            ('src = np.float32([kt[m.queryIdx].pt for m in good])','dst = np.float32([kr[m.trainIdx].pt for m in good])','matched_point_arrays')])
        self.blocks(detector,'compensate_brightness',inspect.getsource(detector.compensate_brightness),[
            ('mass = np.maximum(average(weights), .01)','covariance = average(weights * ref * target) / mass - mean_ref * mean_target','brightness_local_statistics'),
            ('gain = np.clip((covariance + .002) / (variance + .002), .6, 1.6)','predicted = np.clip(gain * ref + offset, 0, 1)','brightness_correction'),
            ('error = np.abs(predicted - target)','weights = np.minimum(1, .04 / np.maximum(error, .0001)) ** 2','brightness_reweight')])
        overlap='overlaps=[int(((labels==i)&core).sum()) for i in range(1,n)]'
        self.blocks(wire_review,'review_evidence',inspect.getsource(wire_review.review_evidence),[(overlap,overlap,'wire_component_overlap')])
        for name in ('register','_register_orientation','refine','legacy_proposals','proposals',
                     'compensate_brightness','candidates_from_residual','matching_structure','structure_change_evidence'):
            self.function(detector,name,name)
        self.function(single_reference_evidence,'explain','context_explain')
        self.function(wire_review,'review_evidence','wire_review')
        for name in ('resize','estimateAffinePartial2D','warpAffine','findTransformECC','GaussianBlur','remap',
                     'boxFilter','erode','dilate','morphologyEx','connectedComponentsWithStats','Canny',
                     'matchTemplate','minAreaRect','distanceTransform'):
            self.operation(cv2,name)
        self.operation(np,'rot90')
        self.factory('ORB_create','detectAndCompute')
        self.factory('BFMatcher','knnMatch')
        return self

    def uninstall(self):
        for obj,name,old in reversed(self.undo):setattr(obj,name,old)
        detector.__dict__.pop('_step_profile',None);wire_review.__dict__.pop('_step_profile',None)


def frame_hash(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def serialize(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,default=lambda x:x.item())


def measure(r,raw):
    stages={}
    def call(name,fn,*args):
        t=time.perf_counter();result=fn(*args);stages[name]=time.perf_counter()-t;return result
    begin=time.perf_counter()
    reg=call('register',detector.register,r,raw)
    mask=detector.machine_mask(r)&reg['valid']
    structural=detector.structure_mask(r)&reg['valid']
    old,_=call('legacy_proposals',detector.legacy_proposals,r,reg['aligned'],structural,.13)
    corrected,flow,regions=call('refine',detector.refine,r,reg['aligned'],structural)
    changes=[]
    candidates,residual=call('proposals',detector.proposals,r,corrected,mask,.13,changes)
    stages['total']=time.perf_counter()-begin
    # Outside timing: reconstruct the actual candidate identities/coordinates for verification.
    for c in candidates:
        c['reasons']=detector.prioritize(c);c['priority']='review' if c['reasons'] else 'high'
    candidates.sort(key=lambda c:(c['priority']!='high',-c['score']))
    for i,c in enumerate(candidates,1):
        c['id']=i;x,y,w,h=[c[k] for k in ('x','y','w','h')]
        points=detector.source_points([[x-5,y-5],[x+w+5,y-5],[x+w+5,y+h+5],[x-5,y+h+5]],reg,flow,raw.shape)
        c['source_polygon']=np.round(points,2).tolist()
        a=np.floor(points.min(axis=0)).astype(int);b=np.ceil(points.max(axis=0)).astype(int)
        c['source_bbox']=[int(a[0]),int(a[1]),int(b[0]),int(b[1])]
    signature=dict(matrix=reg['matrix'].tolist(),rotation=reg['rotation'],mirrored=reg.get('mirrored',False),
        inliers=reg['inliers'],regions=regions,legacy=old,candidates=candidates,structure_changes=changes,
        aligned_sha256=frame_hash(reg['aligned']),corrected_sha256=frame_hash(corrected),
        residual_sha256=frame_hash(residual),flow_sha256=frame_hash(flow),reference_sha256=frame_hash(r))
    return stages,signature


def main():
    OUT.mkdir(exist_ok=True)
    before=protected()
    reference=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/OK/cnd64409dv.tiff')
    target=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/NG/CND6440DTD_2026_11_03_09_57_57_32.tiff')
    before.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (reference,target)})
    (OUT/'preservation-before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
    reuse=CpuReuse(detector,reference).install()
    t=time.perf_counter();reuse.prepare_reference();raw=detector.read(target);setup=time.perf_counter()-t
    rows=[];baseline=None
    try:
        # Uninstrumented controls bracket two profiled runs to expose measurement overhead/load variation.
        for i,profiled in enumerate((False,True,True,False),1):
            p=Profiler().install(reuse) if profiled else None
            try:stages,signature=measure(reuse.small,raw)
            finally:
                if p:p.uninstall()
            if baseline is None:baseline=signature
            assert serialize(signature)==serialize(baseline),f'Output changed in run {i}'
            rows.append(dict(run=i,profiled=profiled,stages=stages,details=dict(p.rows) if p else {},
                feature_matches=p.matches if p else [],orientations=p.orientations if p else [],outputs_identical=True))
            print(f'Run {i}: profiled={profiled}, '+', '.join(f'{k}={v:.3f}s' for k,v in stages.items()),flush=True)
        # Compare all 137 candidates with the preceding full end-to-end experimental result.
        previous_runs=load(ROOT/'workspace/dino-cpu-reuse-20261104/runs.json')
        timing=load(next(r['path'] for r in previous_runs if r['mode']=='warm'))
        previous=load(timing['result_path'])
        prior={c['id']:c for key in ('candidates','filtered_candidates') for c in previous[key]}
        differences=[]
        for c in baseline['candidates']:
            if any(serialize(c[k])!=serialize(prior[c['id']][k]) for k in c):differences.append(c['id'])
        assert len(prior)==len(baseline['candidates'])==137 and not differences,differences
        assert baseline['matrix']==previous['matrix'] and baseline['regions']==previous['local_alignment']
        result=dict(reference=str(reference),target=str(target),threshold=.13,reference_prepared=True,
            reference_and_raw_setup_seconds=setup,opencv_version=cv2.__version__,opencv_threads=cv2.getNumThreads(),
            mode='same latest offline pipeline with previous CPU reuse; DINO not executed in this internal timing study',
            counts=dict(candidates=len(prior),legacy=len(baseline['legacy']),structure_changes=len(baseline['structure_changes'])),
            candidate_changes_from_full_run=differences,output_signature=baseline,runs=rows)
        (OUT/'profile.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=lambda x:x.item()),encoding='utf-8')
    finally:reuse.uninstall()
    after=protected();after.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (reference,target)})
    changes=[p for p,h in before.items() if after.get(p)!=h]
    assert not changes,changes
    (OUT/'preservation-after.json').write_text(json.dumps(dict(files=len(before),changes=changes),indent=2),encoding='utf-8')
    print('PASS: all profiling outputs identical, 137 prior candidates identical; production files unchanged',flush=True)


if __name__=='__main__':main()
