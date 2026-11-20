"""Protect an image-supported screw core before accepting a new parent veto."""
import copy
import hashlib
from pathlib import Path

import numpy as np

VERSION = '5r-parent-veto-core-protection-20261120'


def review(snapshot, reference, target, candidate):
    from correspondence_geometry import contours
    from dino_paired_optimized import classify_candidate
    old=candidate['classification']
    parent=old.get('spatial_review5r',{})
    if old.get('filter_recommendation')!='exclude' or not parent.get('accepted'):
        return old
    checks=[]
    seen=set()
    for shape in contours(target,candidate):
        extent=tuple(shape['box'])
        if shape['coverage']<.5 or max(extent[2:])>32 or extent in seen:
            continue
        seen.add(extent)
        pred=classify_candidate(snapshot,target,reference,dict(zip(('x','y','w','h'),extent)))
        checks.append(dict(core=shape,prediction=pred))
    # A compact object covering most of the query is not demonstrably a
    # detached fragment. Even a negative crop classifier is insufficient to
    # let larger background override the original paired alarm in this case.
    # Keep the original decision conservatively; this is not a new screw label.
    supported=bool(checks)
    evidence=dict(version=VERSION,checks=checks,restored=supported,
                  reason='Compact object makes the fragment assumption uncertain; preserve original paired decision')
    if supported:
        previous=parent['previous']
        if previous.get('filter_recommendation')!='keep':
            raise ValueError('Core protection may only restore an original alarm')
        evidence['parent_veto']=copy.deepcopy(old)
        return dict(copy.deepcopy(previous),fragment_core_guard5r=evidence)
    return dict(old,fragment_core_guard5r=evidence)


def apply(snapshot, result, directory):
    from PIL import Image
    reference,target=[np.asarray(Image.open(Path(directory)/(n+'.png')).convert('L'),np.float32)/255 for n in ('reference','aligned')]
    updated=copy.deepcopy(result)
    candidates=sorted(updated['candidates']+updated['filtered_candidates'],key=lambda c:c['id'])
    updated['candidates'],updated['filtered_candidates']=[],[]
    restored=[]
    for c in candidates:
        pred=review(snapshot,reference,target,c)
        if pred['filter_recommendation']=='keep' and c['classification']['filter_recommendation']=='exclude':
            restored.append(c['id'])
        updated['candidates' if pred['filter_recommendation']=='keep' else 'filtered_candidates'].append(dict(c,classification=pred))
    updated['proposal_count']=len(updated['candidates'])
    updated['filtered_count']=len(updated['filtered_candidates'])
    updated['high_count']=sum(c['priority']=='high' for c in updated['candidates'])
    updated['review_count']=updated['proposal_count']-updated['high_count']
    updated['wire_review_count']=sum(bool(c.get('wire_review')) for c in updated['candidates'])
    updated['fragment_core_guard5r']=dict(version=VERSION,restored=restored,policy_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    # The following enclosure stage renders the final, combined overlay once.
    return updated
