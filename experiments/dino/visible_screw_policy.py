"""Runtime B-part rescue. Opaque rectangles are proposal context, never model input."""
import hashlib,json,copy
import numpy as np
import correspondence_policy as base
import visible_screw_geometry_v2 as geometry
from dino_adapter import paired_decision
from dino_paired_optimized import adjusted_image,features
VERSION='4r-visible-screw-part-v2-20261106';BANK=None;CONFIG=None
def configure(bank,config):
    global BANK,CONFIG
    BANK=bank;CONFIG=config
def box(c):return tuple(c[k] for k in ('x','y','w','h'))
def score(v):
    sims=[(BANK[:,:,0]@v[0]).max(axis=1),BANK[:,0,1]@v[1]];m=[float(np.sort(s[:50])[-3:].mean()-np.sort(s[50:])[-3:].mean()) for s in sims]
    return dict(screw_margin=sum(m)/2,whole_margin=m[0],local_margin=m[1])
class Objects:
    def __init__(self,ref,target,candidates):
        self.base=base.Objects(ref,target,[c for c in candidates if c.get('recovery')!='r4_visible_part']);self.parts=[c for c in candidates if c.get('recovery')=='r4_visible_part'];self.old_kept=[]
    def resolve_part(self,query):
        if any(box(c)==box(query) for c in self.parts):return next(c for c in self.parts if box(c)==box(query))
        choices=[]
        for c in self.parts:
            contain,iou=base.stability_policy.overlap(box(query),box(c))
            if contain>=.25:choices.append((iou,contain,box(c),c))
        return max(choices,key=lambda z:z[:3])[-1] if choices else None

def classify_part(snapshot,ref,target,extent):
    pair={}
    for side,a in [('reference',ref),('target',target)]:
        crop=geometry.part_image(a,extent);im=adjusted_image(snapshot.manifest,crop);v=features(snapshot.manifest,snapshot.session,im);s=score(v)
        pair[side]=dict(s,label='screw' if s['screw_margin']>=0 else 'non_screw',input_sha256=hashlib.sha256(im.tobytes()).hexdigest(),score_kind='exposed_part_50_positive_77_normal')
    return pair

def classify(snapshot,ref,target,query,objects):
    if query.get('recovery')!='r4_visible_part':
        pred=base.classify(snapshot,ref,target,query,objects.base)
        if pred['filter_recommendation']=='keep':objects.old_kept.append(pred['canonical_object']['box'])
        return pred
    from detection_runtime import CURRENT
    context=CURRENT.get();qr,qt=context.arrays(ref,target) if context else [(np.clip(a,0,1)*255).astype('uint8').astype('float32')/255 for a in (ref,target)]
    canonical=objects.resolve_part(query)
    if canonical is None:raise ValueError('No image-derived exposed part supports this query')
    extent=box(canonical);pair=classify_part(snapshot,qr,qt,extent);pred=paired_decision(pair['target'],pair['reference']);rules=[]
    if pair['target']['screw_margin']<CONFIG['target_min']:rules.append('r4_visible_confidence')
    if any(base.stability_policy.overlap(extent,b)[0]>=.8 for b in objects.old_kept):rules.append('r4_visible_duplicate')
    if rules:pred['filter_recommendation']='exclude'
    ident=hashlib.sha256(json.dumps([extent,canonical['visible_part']['occluder_box']]).encode()).hexdigest()[:16]
    pred.update(status='active',model_id=snapshot.manifest['model_id'],action='manual_review' if pred['filter_recommendation']=='keep' else 'discard',canonical_object=dict(version=VERSION,box=list(extent),query_box=list(box(query)),object_id=ident,reason='exposed_part_outside_occluder',fresh_inference=True),r4_experiment=dict(rules=rules),visible_part_experiment=dict(geometry=canonical['visible_part'],target_min=CONFIG['target_min'],occluder_pixels_in_input=0,uses_context_pixels=False,bank='47+3 B parts /65+12 reference normal parts'),decision_reason='4r 可見螺絲部位複核：模型只看遮擋物外側的局部與同位置參照，黑塊本體不輸入；'+('待測支持螺絲、參照不支持，保留。' if pred['filter_recommendation']=='keep' else '局部雙圖／信心條件未通過，或已有同物件警報，排除。'))
    return pred
