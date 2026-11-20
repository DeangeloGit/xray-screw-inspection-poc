"""Observation only: surrounding-structure correspondence, never a decision veto.

Parameters are frozen before dataset evaluation. No filename, bank score, answer
or candidate ID selects eligibility. Registration excludes the candidate itself.
"""
import copy
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

VERSION = '5r-structure-shadow-20261120'
RULES = dict(pads=[16, 32], search=12, exclude_border=4,
             minimum_correlation=.75, maximum_offset_disagreement=2,
             gain_bounds=[.5, 2.], residual_threshold=.13,
             maximum_remaining_fraction=.2, minimum_component_area=20,
             maximum_candidate_side=80)


def match(reference, target, candidate, pad):
    x,y,w,h = [int(candidate[k]) for k in ('x','y','w','h')]
    radius=RULES['search']; border=RULES['exclude_border']
    x0,y0=x-pad,y-pad; X,Y=x+w+pad,y+h+pad
    if min(x0-radius,y0-radius)<0 or X+radius>reference.shape[1] or Y+radius>reference.shape[0]:
        return dict(valid=False,reason='image_boundary',pad=pad)
    patch=target[y0:Y,x0:X]
    ring=np.ones(patch.shape,bool)
    ring[pad-border:pad+h+border,pad-border:pad+w+border]=False
    b=patch[ring].astype(np.float64); centered=b-b.mean(); norm=np.linalg.norm(centered)
    if b.std()<.025:
        return dict(valid=False,reason='insufficient_surrounding_texture',pad=pad)
    best=None
    for dy in range(-radius,radius+1):
        for dx in range(-radius,radius+1):
            a=reference[y0+dy:Y+dy,x0+dx:X+dx][ring].astype(np.float64)
            ac=a-a.mean(); score=float(ac@centered/max(np.linalg.norm(ac)*norm,1e-12))
            if best is None or score>best[0]:best=(score,dx,dy,a)
    score,dx,dy,a=best
    gain=float(((a-a.mean())@centered)/max(((a-a.mean())**2).sum(),1e-12));offset=float(b.mean()-gain*a.mean())
    before=np.maximum(reference[y:y+h,x:x+w]-target[y:y+h,x:x+w],0)
    predicted=reference[y+dy:y+h+dy,x+dx:x+w+dx]*gain+offset
    residual=np.maximum(predicted-target[y:y+h,x:x+w],0)
    active=before>RULES['residual_threshold']
    fraction=float(residual[active].sum()/max(float(before[active].sum()),1e-12)) if active.any() else None
    _,_,stats,_=cv2.connectedComponentsWithStats((residual>RULES['residual_threshold']).astype('uint8'))
    largest=int(stats[1:,4].max()) if len(stats)>1 else 0
    return dict(valid=True,pad=pad,score=score,dx=dx,dy=dy,gain=gain,offset=offset,
                original_active_pixels=int(active.sum()),remaining_fraction=fraction,
                largest_residual_component=largest,registration_uses_candidate=False)


def review(reference,target,candidate):
    from enclosure_rescue5r import geometry
    row=dict(candidate_id=candidate['id'],recommendation='retain',reason='insufficient_evidence')
    if max(candidate['w'],candidate['h'])>RULES['maximum_candidate_side']:
        return dict(row,reason='outside_review_size')
    core=geometry(target,candidate)
    if core is not None:
        return dict(row,reason='independent_object_protected',core=core)
    views=[match(reference,target,candidate,pad) for pad in RULES['pads']]
    row['views']=views
    if not all(v['valid'] for v in views):return row
    correspondence=all(v['score']>=RULES['minimum_correlation'] and
                       max(abs(v['dx']),abs(v['dy']))<RULES['search'] and
                       RULES['gain_bounds'][0]<=v['gain']<=RULES['gain_bounds'][1] for v in views)
    consistent=all(abs(views[0][k]-views[1][k])<=RULES['maximum_offset_disagreement'] for k in ('dx','dy'))
    explained=all(v['remaining_fraction'] is not None and
                  v['remaining_fraction']<=RULES['maximum_remaining_fraction'] and
                  v['largest_residual_component']<RULES['minimum_component_area'] for v in views)
    row.update(correspondence_passed=correspondence,offset_consistent=consistent,residual_explained=explained)
    if correspondence and consistent and explained:
        row.update(recommendation='exclude_suggestion',reason='existing_structure_explains_difference')
    return row


def apply(result,directory):
    """Adds separate evidence only; candidate dictionaries/overlays are untouched."""
    from PIL import Image
    directory=Path(directory)
    reference,target=[np.asarray(Image.open(directory/(n+'.png')).convert('L'),np.float32)/255 for n in ('reference','aligned')]
    rows=[review(reference,target,c) for c in result['candidates']]
    evidence=dict(version=VERSION,mode='shadow_only',official_decisions_changed=False,
                  policy_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),rules=RULES,rows=rows)
    filename='structure-shadow.json'
    (directory/filename).write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    updated=copy.deepcopy(result)
    updated['structure_shadow5r']=dict(version=VERSION,mode='shadow_only',evidence_file=filename,
                                     suggested_exclusions=[r['candidate_id'] for r in rows if r['recommendation']=='exclude_suggestion'])
    return updated
