"""Final guard for newly inspected enclosure bands, never for original alarms."""
import copy
import hashlib
from pathlib import Path

import cv2
import numpy as np

VERSION = '5r-enclosure-compact-support-20261120'


def review(snapshot, reference, target, candidate):
    old = candidate['classification']
    if candidate.get('recovery') != '5r_enclosure' or old.get('filter_recommendation') != 'keep':
        return old
    extent = [int(candidate[k]) for k in ('x','y','w','h')]
    w,h = extent[2:]
    # Use the same compactness definition as the existing local-core guard.
    # A long residual may still contain a real screw: classify its stable core
    # before rejecting it. This is not a ban on wire-adjacent or long screws.
    if max(w,h) <= 3*min(w,h):
        return old
    from local_object5r import compact_cores
    from dino_paired_optimized import classify_candidate
    checks=[]
    for core in compact_cores(target,extent):
        pred=classify_candidate(snapshot,target,reference,dict(zip(('x','y','w','h'),core['box'])))
        checks.append(dict(core=core,prediction=pred))
    supported=any(c['prediction']['filter_recommendation']=='keep' for c in checks)
    evidence=dict(version=VERSION,checks=checks,supported=supported,query=extent)
    if supported:
        return dict(old,enclosure_guard5r=evidence)
    evidence['previous']=copy.deepcopy(old)
    return dict(old,action='discard',filter_recommendation='exclude',enclosure_guard5r=evidence,
                decision_reason='5r 外殼新增通道：細長差分沒有跨尺寸穩定且雙圖支持的螺絲核心，不升為警報；候選及原 DINO 分數保留供複核。')


def apply(snapshot, result, directory):
    from PIL import Image
    import detector
    directory=Path(directory)
    reference,target=[np.asarray(Image.open(directory/(name+'.png')).convert('L'),np.float32)/255 for name in ('reference','aligned')]
    updated=copy.deepcopy(result)
    candidates=sorted(updated['candidates']+updated['filtered_candidates'],key=lambda c:c['id'])
    updated['candidates'],updated['filtered_candidates']=[],[]
    removed=[]
    for candidate in candidates:
        old=candidate['classification']
        pred=review(snapshot,reference,target,candidate)
        if old['filter_recommendation']=='keep' and pred['filter_recommendation']=='exclude':
            removed.append(candidate['id'])
        updated['candidates' if pred['filter_recommendation']=='keep' else 'filtered_candidates'].append(dict(candidate,classification=pred))
    updated['proposal_count']=len(updated['candidates'])
    updated['filtered_count']=len(updated['filtered_candidates'])
    updated['high_count']=sum(c['priority']=='high' for c in updated['candidates'])
    updated['review_count']=updated['proposal_count']-updated['high_count']
    updated['wire_review_count']=sum(bool(c.get('wire_review')) for c in updated['candidates'])
    updated['enclosure_guard5r']=dict(version=VERSION,removed=removed,policy_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    source=cv2.imdecode(np.fromfile(directory/'source.png',np.uint8),cv2.IMREAD_COLOR)
    high,all_overlay=source.copy(),source.copy()
    for c in updated['candidates']:
        points=np.rint(np.asarray(c['source_polygon'])*result['preview_scale']).astype('int32')
        color=(60,65,245) if c['priority']=='high' else (0,185,245)
        for canvas in ([high,all_overlay] if c['priority']=='high' else [all_overlay]):
            cv2.polylines(canvas,[points],True,color,2)
            cv2.putText(canvas,str(c['id']),tuple(points.min(axis=0)-[0,6]),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
    detector.write_image(str(directory/'overlay.png'),high)
    detector.write_image(str(directory/'all_overlay.png'),all_overlay)
    return updated
