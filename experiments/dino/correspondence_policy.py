"""Isolated image-only correspondence and complete-contour rechecks."""
import copy,hashlib
import numpy as np
from PIL import Image
import stability_policy
from correspondence_geometry import template_matches,strong_match,contours
box=stability_policy.box
VERSION='4r-reference-shared-contrast-20261106'

class Objects(stability_policy.Objects):
    def __init__(self,ref,target,candidates):
        super().__init__(ref,target,candidates)
        self.contour_support=[]
        for obj in self.objects:
            c=obj['canonical']
            if max(c['w'],c['h'])<=32:
                for g in contours(target,c):
                    if g['coverage']>=.5 and max(g['box'][2:])<=32:
                        self.contour_support.append((g['box'],obj))
    def resolve(self,query):
        obj=super().resolve(query)
        if obj is not None:return obj
        # A shifted tiny search window can leave the original partial box.
        # Recover only via overlapping image-derived complete contours.
        choices=[]
        for extent,record in self.contour_support:
            containment,iou=stability_policy.overlap(box(query),extent)
            if containment>=.5:choices.append((iou,record['object_id'],record))
        return max(choices,key=lambda z:z[:2])[2] if choices else None

def crop(im,c,pad,dx=0,dy=0):
    x,y,w,h=box(c);x+=dx;y+=dy
    return im[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad]

def shared_pair(snapshot,ref,target,c,pad):
    from dino_adapter import input_image,paired_decision
    from dino_paired_optimized import features
    images=[np.asarray(input_image(snapshot.manifest,crop(im,c,pad)).convert('L'),np.float32) for im in (ref,target)]
    low,high=np.percentile(images[1],[1,99]);sides={}
    for side,a in zip(('reference','target'),images):
        im=Image.fromarray(np.rint(np.clip((a-low)/max(1,high-low),0,1)*255).astype('uint8')).convert('RGB')
        v=features(snapshot.manifest,snapshot.session,im);bank=snapshot.feature_bank;n=len(snapshot.manifest['example_bank']['screw']['ids'])
        vals=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]];margins=[float(np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean()) for s in vals];margin=sum(margins)/2
        sides[side]=dict(label='screw' if margin>=0 else 'non_screw',screw_margin=margin,whole_margin=margins[0],local_margin=margins[1],input_sha256=hashlib.sha256(im.tobytes()).hexdigest(),score_kind='shared_contrast_cosine_margin',normalization=dict(low=float(low),high=float(high),source='target_applied_to_both'))
    return dict(paired_decision(sides['target'],sides['reference']),status='active',model_id=snapshot.manifest['model_id'])

def classify(snapshot,ref,target,query,objects):
    result=stability_policy.classify(snapshot,ref,target,query,objects)
    canonical=copy.deepcopy(objects.resolve(query)['canonical'])
    from detection_runtime import CURRENT
    context=CURRENT.get();qref,qtar=context.arrays(ref,target) if context else [(np.clip(a,0,1)*255).astype('uint8').astype('float32')/255 for a in (ref,target)]
    meta=dict(version=VERSION,original_decision=result['filter_recommendation'],original_pair=result['paired_evidence'],reference_offset=[0,0],recheck=None)
    def replace(pred,reason,newbox=None):
        nonlocal result
        result=dict(pred,canonical_object=copy.deepcopy(result['canonical_object']),decision_reason=reason)
        result['action']='manual_review' if pred['filter_recommendation']=='keep' else 'discard'
        if newbox:
            result['canonical_object']['previous_box']=result['canonical_object']['box']
            result['canonical_object']['box']=list(newbox)
        result['canonical_object']['version']=VERSION
    if result['filter_recommendation']=='keep':
        matches=template_matches(qref,qtar,canonical);meta['matches']=matches
        if strong_match(matches):
            dx,dy=matches[0]['dx'],matches[0]['dy']
            left=crop(qref,canonical,12,dx,dy);right=crop(qtar,canonical,12)
            if left.shape==right.shape:
                checked=snapshot.classify(right,reference_crop=left)
                meta['matched_pair']=checked
                if all(checked['paired_evidence'][s]['label']=='screw' for s in ('reference','target')):
                    meta.update(reference_offset=[dx,dy],recheck='matched_reference_object')
                    replace(checked,'4r 參照物件配對：三種範圍皆找到一致位移的高相似物件；重新跑雙圖後兩邊都像螺絲，排除。')
    else:
        pair=result['paired_evidence'];rs=float(crop(qref,canonical,0).std());ts=float(crop(qtar,canonical,0).std())
        meta.update(reference_std=rs,target_std=ts)
        if all(pair[s]['label']=='screw' for s in ('reference','target')) and rs<.025 and ts>.12:
            views={str(p):shared_pair(snapshot,qref,qtar,canonical,p) for p in (4,8,12)}
            meta.update(recheck='shared_contrast_reference',shared_views=views)
            reference=sorted((v['paired_evidence']['reference'] for v in views.values()),key=lambda s:s['screw_margin'])[1]
            target_side=min((v['paired_evidence']['target'] for v in views.values()),key=lambda s:s['screw_margin'])
            if reference['screw_margin']<=-.02 and target_side['screw_margin']>=.04:
                from dino_adapter import paired_decision
                checked=dict(paired_decision(target_side,reference),status='active',model_id=snapshot.manifest['model_id'])
                meta['consensus']=dict(reference='median_of_three',target='minimum_of_three',reference_max=-.02,target_min=.04)
                replace(checked,'4r 低對比參照複核：兩圖共用待測明暗尺度，避免放大參照空白紋理；三種取圖的待測皆支持螺絲，參照中位分數支持不像螺絲，保留警報。')
        elif max(canonical['w'],canonical['h'])<=32:
            candidates=contours(qtar,canonical)
            eligible=[g for g in candidates if g['coverage']>=.5 and max(g['box'][2:])<=32 and (g['box'][2]*g['box'][3]>=1.5*canonical['w']*canonical['h'] or g['box'][2]>=1.4*canonical['w'] or g['box'][3]>=1.4*canonical['h'])]
            if eligible:
                selected=max(eligible,key=lambda g:(g['box'][2]*g['box'][3],g['cutoff']));c=dict(canonical,**dict(zip(('x','y','w','h'),selected['box'])))
                views={str(p):snapshot.classify(crop(qtar,c,p),reference_crop=crop(qref,c,p)) for p in (4,8,12)}
                meta.update(recheck='complete_contour',contour=selected,contour_views=views)
                if all(v['paired_evidence']['target']['label']=='non_screw' for v in views.values()):
                    replace(views['12'],'4r 完整輪廓重看：分離細線／邊界後，以完整物件及三種背景重新跑雙圖；待測仍皆判不像螺絲，維持自動排除，並保留複核證據。',selected['box'])
                else:meta['inconclusive']=True
    result['correspondence_experiment']=meta
    return result
