"""Image-derived object normalization BEFORE inference, without answers or verdicts."""
import copy
import hashlib
import json
import math
import cv2
import numpy as np
from improvement_policy import extra_geometry
import overkill_pilot
ORIGINAL_PILOT_APPLY=overkill_pilot.apply

VERSION='4r-canonical-object-20261106'


def box(c):return tuple(c[k] for k in ('x','y','w','h'))


def overlap(a,b):
    x,y,w,h=a;X,Y,W,H=b
    inter=max(0,min(x+w,X+W)-max(x,X))*max(0,min(y+h,Y+H)-max(y,Y))
    return inter/max(1,min(w*h,W*H)),inter/max(1,w*h+W*H-inter)


def clean(c):
    # Excludes prior inference, ids, paths, and evaluation labels by construction.
    allowed=('x','y','w','h','area','score','normal_support','aspect','fill','bipolar','contrast','shape_similarity','recovery','change_type','wire_review','change_evidence','single_reference_evidence','pilot_context')
    return {k:copy.deepcopy(c[k]) for k in allowed if k in c}


class Objects:
    def __init__(self,ref,target,candidates):
        self.candidates=[clean(c) for c in sorted(candidates,key=box)]
        parents=list(range(len(candidates)))
        def root(i):
            while parents[i]!=i:
                parents[i]=parents[parents[i]];i=parents[i]
            return i
        for i,c in enumerate(self.candidates):
            for j in range(i):
                if overlap(box(c),box(self.candidates[j]))[0]>=.8:
                    parents[root(i)]=root(j)
        groups={}
        for i,c in enumerate(self.candidates):groups.setdefault(root(i),[]).append(c)
        self.objects=[];self.by_box={}
        local_groups=[]
        for members in groups.values():
            x=min(c['x'] for c in members);y=min(c['y'] for c in members)
            w=max(c['x']+c['w'] for c in members)-x;h=max(c['y']+c['h'] for c in members)-y
            # A large board may contain unrelated fragments. Do not turn its
            # verdict into the verdict of every small object inside it.
            if w*h>1600 or max(w,h)>80:local_groups.extend([[c] for c in members])
            else:local_groups.append(members)
        for members in local_groups:
            geometries=[extra_geometry(ref,target,c)[0] for c in members] if len(members)>1 else [{}]
            compact=[c for c,g in zip(members,geometries) if g and g['near_share']>=.8
                     and max(g['box'][2:])<=2*max(c['w'],c['h']) and max(c['w'],c['h'])<=3*min(c['w'],c['h'])]
            if compact:
                chosen=min(compact,key=lambda c:(c['w']*c['h'],box(c)))
                reason='compact_object_contour'
            else:
                chosen=max(members,key=lambda c:(c['w']*c['h'],box(c)))
                reason='connected_structure_context' if len(members)>1 else 'single_proposal'
            ident=hashlib.sha256(json.dumps([box(c) for c in members]).encode()).hexdigest()[:16]
            record=dict(object_id=ident,canonical=chosen,members=members,geometry=geometries,reason=reason)
            self.objects.append(record)
            for c in members:self.by_box[box(c)]=record

    def resolve(self,query):
        if box(query) in self.by_box:return self.by_box[box(query)]
        # Proposals are search windows, never the DINO crop. Compare to all
        # image-derived support windows so both large and small seeds resolve.
        best=None
        for obj in self.objects:
            scores=[]
            for c in obj['members']:
                contain,iou=overlap(box(query),box(c))
                if contain<.25:continue
                qx,qy,qw,qh=box(query);x,y,w,h=box(c)
                distance=math.hypot(qx+qw/2-x-w/2,qy+qh/2-y-h/2)/max(8,math.hypot(w,h))
                scores.append(iou+.05*contain-.05*distance)
            if scores:
                candidate=(max(scores),obj['object_id'],obj)
                if best is None or candidate[:2]>best[:2]:best=candidate
        return best[2] if best else None


def classify(snapshot,ref,target,query,objects):
    """Always perform new inference on the canonical image crop; no result cache."""
    from dino_paired_optimized import classify_candidate
    from improvement_policy import improve
    from detection_runtime import CURRENT
    obj=objects.resolve(query)
    if obj is None:raise ValueError('No image object supports this candidate window')
    canonical=copy.deepcopy(obj['canonical'])
    initial=classify_candidate(snapshot,target,ref,canonical)
    context=CURRENT.get()
    quantized=context.arrays(ref,target) if context else [(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in (ref,target)]
    result=improve(snapshot,*quantized,canonical,initial,ORIGINAL_PILOT_APPLY)
    result['canonical_object']=dict(version=VERSION,object_id=obj['object_id'],query_box=list(box(query)),box=list(box(canonical)),reason=obj['reason'],member_boxes=[list(box(c)) for c in obj['members']],fresh_inference=True)
    return result
