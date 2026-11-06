"""4r-only integration fix: mixed contour votes must not disable existing review."""
import copy
import example_audit_policy as base
from dino_adapter import paired_decision
VERSION='4r-integrated-bank-mixed-contour-review-20261106'

def classify(snapshot,ref,target,query,objects):
    pred=base.classify(snapshot,ref,target,query,objects)
    if pred['filter_recommendation']=='keep' or query.get('recovery')=='r4_visible_part':return pred
    meta=pred.get('correspondence_experiment',{})
    if meta.get('recheck')!='complete_contour' or not meta.get('inconclusive'):return pred
    # A weak-consensus flag concerns the earlier fragment. Actual structural
    # vetoes remain vetoes. Review the already found complete contour using the
    # unchanged 47+65 four-view secondary bank and unchanged paired criteria.
    if set(pred.get('r4_experiment',{}).get('rules',[]))-{'r4_no_consensus'}:return pred
    if pred.get('overkill_pilot',{}).get('rules'):return pred
    extent=meta['contour']['box']
    from detection_runtime import CURRENT
    import numpy as np
    ctx=CURRENT.get();qr,qt=ctx.arrays(ref,target) if ctx else [(np.clip(a,0,1)*255).astype('uint8').astype('float32')/255 for a in (ref,target)]
    checked=base.review(snapshot,qr,qt,extent)
    if not checked['keep']:return dict(pred,integrated_contour_review=dict(version=VERSION,performed=True,accepted=False,box=extent,views=checked['views']))
    result=paired_decision(checked['pair']['target'],checked['pair']['reference']);canonical=copy.deepcopy(pred['canonical_object']);canonical.update(previous_box=canonical['box'],box=list(extent),version=VERSION)
    result.update(status='active',model_id=snapshot.manifest['model_id'],action='manual_review',canonical_object=canonical,correspondence_experiment=copy.deepcopy(meta),integrated_contour_review=dict(version=VERSION,performed=True,accepted=True,box=extent,views=checked['views'],previous=pred,rule='Existing secondary-bank four-view target mean >=0 and every reference margin <0; no thresholds or source examples changed'),decision_reason='4r 整合複核：完整輪廓的三種範圍意見不一致，仍執行既有四範圍雙圖複核；待測平均支持螺絲、每個參照皆不支持，保留。')
    objects.old_kept.append(list(extent))
    return result
