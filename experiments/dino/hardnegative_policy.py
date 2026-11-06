"""Experimental image-only rescue. No photo IDs or evaluation answers at runtime."""
import copy,hashlib
import cv2
import numpy as np
import correspondence_policy as base
from blackblock_ablation import cut,score
Objects=base.Objects
box=base.box
VERSION='4r-hardnegative-reference-difference-20261106'
BANK=None
CONFIG=None

def difference(ref,target,extent,offset=(0,0)):
    x,y,w,h=map(int,extent);dx,dy=map(int,offset)
    # A reference dark pixel anywhere within 3 px explains motion at that pixel.
    # A local background offset is measured outside the object, not on its core.
    pad=12;X,Y=x+w,y+h
    r=ref[max(0,y-pad+dy):Y+pad+dy,max(0,x-pad+dx):X+pad+dx]
    t=target[max(0,y-pad):Y+pad,max(0,x-pad):X+pad]
    if r.shape!=t.shape or min(r.shape)<7:return dict(valid=False,area=0,share=0)
    ring=np.ones(r.shape,bool);a=min(pad,y);b=min(pad,x);ring[a:a+h,b:b+w]=False
    brightness=float(np.median((r-t)[ring])) if ring.any() else 0.
    rmin=cv2.erode(r,np.ones((7,7),np.uint8));delta=rmin[a:a+h,b:b+w]-t[a:a+h,b:b+w]-brightness
    dark=t[a:a+h,b:b+w]<.45;novel=dark&(delta>.15)
    _,_,stats,_=cv2.connectedComponentsWithStats(novel.astype('uint8'))
    return dict(valid=True,area=int(max(stats[1:,4],default=0)),share=float(novel.sum()/max(1,dark.sum())),brightness_offset=brightness,delta_p80=float(np.quantile(delta,.8)))

def gate(pair,diff,config):
    return bool(pair['target']['margin']>=config['target_min'] and pair['reference']['margin']<0 and diff['valid'] and diff['area']>=16 and diff['share']>=.5)

def configure(bank,config):
    global BANK,CONFIG
    BANK=bank;CONFIG=config

def classify(snapshot,ref,target,query,objects):
    result=base.classify(snapshot,ref,target,query,objects)
    rules=result.get('overkill_pilot',{}).get('rules',[])+result.get('r4_experiment',{}).get('rules',[])
    if result['filter_recommendation']=='keep' or rules or result['paired_evidence']['target']['label']=='screw':return result
    assert BANK is not None and CONFIG is not None
    from detection_runtime import CURRENT
    from dino_paired_optimized import adjusted_image,features
    from dino_adapter import paired_decision
    context=CURRENT.get();qr,qt=context.arrays(ref,target) if context else [(np.clip(a,0,1)*255).astype('uint8').astype('float32')/255 for a in (ref,target)]
    extent=result['canonical_object']['box'];offset=result['correspondence_experiment']['reference_offset'];pair={}
    for side,im in [('reference',qr),('target',qt)]:
        view=adjusted_image(snapshot.manifest,cut(im,extent,'original',offset if side=='reference' else (0,0)))
        v=features(snapshot.manifest,snapshot.session,view)
        pair[side]=dict(score(v,BANK,50),input_sha256=hashlib.sha256(view.tobytes()).hexdigest())
    diff=difference(qr,qt,extent,offset);accept=gate(pair,diff,CONFIG)
    result['hardnegative_experiment']=dict(version=VERSION,pair=pair,difference=diff,config=CONFIG,accepted=accept,baseline_pair=copy.deepcopy(result['paired_evidence']),fresh_inference=True)
    if accept:
        sides={k:dict(label='screw' if v['margin']>=0 else 'non_screw',screw_margin=v['margin'],whole_margin=v['whole'],local_margin=v['local'],input_sha256=v['input_sha256'],score_kind='experimental_50_positive_hardnegative_bank') for k,v in pair.items()}
        result.update(paired_decision(sides['target'],sides['reference']))
        result['action']='manual_review';result['decision_reason']='4r 困難正常範例與參照差異複核：待測支持螺絲、參照不支持；容許3像素位移與背景亮度差後，仍有連續新增深色物件，保留警報。'
    return result
