"""4r-only complete-contour review with uncropped, consistently prepared examples."""
import copy,hashlib
import numpy as np
import visible_screw_policy_v3 as base
from dino_paired_optimized import adjusted_image,features
from dino_adapter import paired_decision
VERSION='4r-complete-contour-letterbox-mean4-20261106'
Objects=base.Objects;box=base.box;geometry=base.geometry
BANK=None;PADS=(2,4,8,12)
def configure(part_bank,part_config,review_bank):
    global BANK
    base.configure(part_bank,part_config);BANK=review_bank
    assert BANK.shape==(112,8,2,384)
def square_crop(a,b,pad):
    x,y,w,h=b;crop=a[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad];hh,ww=crop.shape;s=max(hh,ww)
    image=np.ones((s,s),np.float32);yy=(s-hh)//2;xx=(s-ww)//2;image[yy:yy+hh,xx:xx+ww]=crop;return image
def review(snapshot,ref,target,extent):
    views=[]
    for pad in PADS:
        pair={}
        for side,a in [('reference',ref),('target',target)]:
            image=adjusted_image(snapshot.manifest,square_crop(a,extent,pad));v=features(snapshot.manifest,snapshot.session,image)
            sims=[(BANK[:,:,0]@v[0]).max(axis=1),BANK[:,0,1]@v[1]];margins=[float(np.sort(s[:47])[-3:].mean()-np.sort(s[47:])[-3:].mean()) for s in sims]
            pair[side]=dict(screw_margin=sum(margins)/2,whole_margin=margins[0],local_margin=margins[1],input_sha256=hashlib.sha256(image.tobytes()).hexdigest())
        views.append(dict(pad=pad,**pair))
    sides={}
    for side in ('reference','target'):
        scores={k:float(np.mean([v[side][k] for v in views])) for k in ('screw_margin','whole_margin','local_margin')}
        sides[side]=dict(scores,label='screw' if scores['screw_margin']>=0 else 'non_screw',score_kind='47_65_letterbox_four_view_mean',input_sha256=hashlib.sha256(''.join(v[side]['input_sha256'] for v in views).encode()).hexdigest())
    return dict(pair=sides,views=views,keep=sides['target']['screw_margin']>=0 and all(v['reference']['screw_margin']<0 for v in views))
def eligible(pred):
    return (pred['filter_recommendation']!='keep' and pred.get('correspondence_experiment',{}).get('recheck')=='complete_contour'
            and pred['paired_evidence']['target']['label']=='non_screw'
            and not pred.get('r4_experiment',{}).get('rules') and not pred.get('overkill_pilot',{}).get('rules'))
def classify(snapshot,ref,target,query,objects):
    previous=base.classify(snapshot,ref,target,query,objects)
    if query.get('recovery')=='r4_visible_part' or not eligible(previous):return previous
    from detection_runtime import CURRENT
    context=CURRENT.get();qr,qt=context.arrays(ref,target) if context else [(np.clip(a,0,1)*255).astype('uint8').astype('float32')/255 for a in (ref,target)]
    extent=previous['canonical_object']['box'];checked=review(snapshot,qr,qt,extent)
    if not checked['keep']:return previous
    pred=paired_decision(checked['pair']['target'],checked['pair']['reference'])
    pred.update(status='active',model_id=snapshot.manifest['model_id'],action='manual_review',canonical_object=copy.deepcopy(previous['canonical_object']),correspondence_experiment=copy.deepcopy(previous['correspondence_experiment']),example_crop_review=dict(version=VERSION,bank='same47+65_sources_letterboxed_for_both_classes',views=checked['views'],target_rule='mean of four margins >= 0',reference_rule='every margin < 0',previous=previous),decision_reason='4r 完整輪廓複核：螺絲與正常範例均保留完整比例；參照／待測各以2、4、8、12像素背景補成方形重新推論。待測四範圍平均支持螺絲，四個參照皆不支持，保留警報。')
    pred['canonical_object']['version']=VERSION;objects.old_kept.append(extent)
    return pred
