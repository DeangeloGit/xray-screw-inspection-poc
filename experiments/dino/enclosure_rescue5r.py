"""Conservative recovery of excluded new-enclosure objects after all prior stages.

Geometry is chosen before scores. No labels, filenames or answer coordinates
are read. Original retained candidates and exclusions outside this channel
pass through unchanged.
"""
import copy
import hashlib
import json
from pathlib import Path
from PIL import Image

VERSION = '5r-stable-enclosure-rescue-20261120'

import cv2
import numpy as np

def geometry(target,c):
 x,y,w,h=[int(c[k]) for k in ['x','y','w','h']];rows=[]
 for pad in [8,12,20]:
  x0,y0=max(0,x-pad),max(0,y-pad);roi=np.rint(np.clip(target[y0:y+h+pad,x0:x+w+pad],0,1)*255).astype('uint8');level,mask=cv2.threshold(roi,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
  n,labels,stats,centers=cv2.connectedComponentsWithStats(mask);mass=np.bincount(labels[y-y0:y-y0+h,x-x0:x-x0+w].ravel(),minlength=n);mass[0]=0
  if not mass.max():return None
  i=mass.argmax();a,b,u,v,area=map(int,stats[i]);X,Y=a+x0,b+y0
  if a==0 or b==0 or a+u==roi.shape[1] or b+v==roi.shape[0] or max(u,v)>32 or min(u,v)<5 or max(u,v)>3*min(u,v) or area<20:return None
  inter=max(0,min(x+w,X+u)-max(x,X))*max(0,min(y+h,Y+v)-max(y,Y))
  if inter/(w*h)<.5:return None
  rows.append(dict(box=[X,Y,u,v],area=area,pad=pad,threshold=level))
 first=rows[0]['box']
 for z in rows[1:]:
  a,b,u,v=first;X,Y,W,H=z['box'];i=max(0,min(a+u,X+W)-max(a,X))*max(0,min(b+v,Y+H)-max(b,Y));iou=i/(u*v+W*H-i)
  if iou<.8:return None
 return dict(extent=max(rows,key=lambda z:z['area'])['box'],windows=rows)


def review(snapshot, reference, target, candidate):
    old = candidate['classification']
    if (candidate.get('recovery') != '5r_enclosure'
            or old.get('filter_recommendation') != 'exclude'
            or max(candidate['w'], candidate['h']) > 32):
        return old
    shape = geometry(target, candidate)
    if shape is None:
        return old
    x, y, w, h = shape['extent']
    views = []
    for pad in (2, 4):
        region = (slice(max(0,y-pad),y+h+pad),slice(max(0,x-pad),x+w+pad))
        pred = snapshot.classify(target[region], reference_crop=reference[region])
        if pred.get('status') != 'active':
            raise ValueError('Enclosure rescue requires active paired DINO inference')
        views.append(dict(pad=pad,prediction=pred))
    if not all(v['prediction']['filter_recommendation']=='keep' for v in views):
        return old
    from dino_adapter import paired_decision
    pairs = [v['prediction']['paired_evidence'] for v in views]
    target_score = min((v['target'] for v in pairs),key=lambda p:p['screw_margin'])
    reference_score = max((v['reference'] for v in pairs),key=lambda p:p['screw_margin'])
    result = paired_decision(target_score, reference_score)
    if result['filter_recommendation'] != 'keep':
        raise ValueError('Inconsistent paired recovery result')
    result.update(status='active',model_id=snapshot.manifest['model_id'],action='manual_review',
                  enclosure_rescue5r=dict(version=VERSION,geometry=shape,views=views,previous=copy.deepcopy(old)),
                  canonical_object=dict(old.get('canonical_object',{}),previous_box=[candidate[k] for k in ('x','y','w','h')],box=shape['extent'],version=VERSION),
                  decision_reason='5r 外殼補救：三種周圍範圍找到穩定完整物件；兩種貼近物件的雙圖判斷均支持待測螺絲、參照非螺絲，追加警報。')
    return result


def apply(snapshot, result, directory):
    import detector
    directory = Path(directory)
    reference, target = [np.asarray(Image.open(directory/(n+'.png')).convert('L'),np.float32)/255
                         for n in ('reference','aligned')]
    encoded = json.dumps(result,ensure_ascii=False,sort_keys=True).encode('utf8')
    baseline = 'baseline-pre-rescue-'+hashlib.sha256(encoded).hexdigest()[:16]+'.json'
    (directory/baseline).write_bytes(encoded)
    updated = copy.deepcopy(result)
    retained = updated['candidates']
    excluded = []
    promoted = []
    for candidate in updated['filtered_candidates']:
        pred = review(snapshot,reference,target,candidate)
        if pred['filter_recommendation']=='keep':
            retained.append(dict(candidate,classification=pred))
            promoted.append(candidate['id'])
        else:
            excluded.append(candidate)
    updated['filtered_candidates'] = excluded
    updated['proposal_count'] = len(retained)
    updated['filtered_count'] = len(excluded)
    updated['high_count'] = sum(c['priority']=='high' for c in retained)
    updated['review_count'] = len(retained)-updated['high_count']
    updated['wire_review_count'] = sum(bool(c.get('wire_review')) for c in retained)
    updated['enclosure_rescue5r'] = dict(version=VERSION,promoted=promoted,baseline_file=baseline,
                                         policy_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if promoted:
        source=cv2.imdecode(np.fromfile(directory/'source.png',np.uint8),cv2.IMREAD_COLOR)
        high,all_overlay=source.copy(),source.copy()
        for c in retained:
            points=np.rint(np.asarray(c['source_polygon'])*result['preview_scale']).astype('int32')
            color=(60,65,245) if c['priority']=='high' else (0,185,245)
            for canvas in ([high,all_overlay] if c['priority']=='high' else [all_overlay]):
                cv2.polylines(canvas,[points],True,color,2)
                cv2.putText(canvas,str(c['id']),tuple(points.min(axis=0)-[0,6]),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
        detector.write_image(str(directory/'overlay.png'),high)
        detector.write_image(str(directory/'all_overlay.png'),all_overlay)
    return updated
