"""Offline joint-image boundary hypotheses, never a production decision.

Reference pixels participate as evidence, not as permission to delete a seed.
Candidate-only markers cannot establish the physical boundary under occlusion.
"""
import cv2
import numpy as np
from ok_reference_shadow5r import context_match, unit
from structure_shadow5r import RULES

PADS = (12,20,32)


def valid_context(views):
    return (all(v['valid'] and v['score'] >= RULES['minimum_correlation'] and
        max(abs(v['dx']),abs(v['dy'])) < RULES['search'] and
        RULES['gain_bounds'][0] <= v['gain'] <= RULES['gain_bounds'][1] for v in views)
        and all(abs(views[0][k]-views[1][k]) <= RULES['maximum_offset_disagreement'] for k in ('dx','dy')))


def region(reference, target, seed, context, pad, threshold, method='watershed'):
    x,y,w,h=[int(seed[k]) for k in ('x','y','w','h')]
    x0,y0=x-pad,y-pad; X,Y=x+w+pad,y+h+pad
    dx,dy=context['dx'],context['dy']
    if min(x0,y0,x0+dx,y0+dy)<0 or max(X,X+dx)>target.shape[1] or max(Y,Y+dy)>target.shape[0]:
        return dict(valid=False,reason='image_boundary'),None
    t=unit(target[y0:Y,x0:X]); r=unit(reference[y0+dy:Y+dy,x0+dx:X+dx])*context['gain']+context['offset']
    delta=r-t
    n,labels,stats,_=cv2.connectedComponentsWithStats((delta>threshold).astype('uint8'))
    ids,counts=np.unique(labels[pad:pad+h,pad:pad+w],return_counts=True)
    ids,counts=ids[ids!=0],counts[ids!=0]
    if not len(ids):return dict(valid=False,reason='no_corrected_seed'),None
    winners=ids[counts==counts.max()]
    if len(winners)!=1:return dict(valid=False,reason='ambiguous_seed_components'),None
    ident=int(winners[0]); connected=labels==ident
    fg=np.zeros(t.shape,bool)
    fg[pad:pad+h,pad:pad+w]=connected[pad:pad+h,pad:pad+w]
    # Positive-difference core is immutable. Other positive components compete
    # as separate labels, so a nearby seed cannot silently absorb them.
    markers=np.zeros(t.shape,np.int32)
    markers[delta<=0]=1
    markers[(labels>0)&~connected]=3
    markers[fg]=2
    touches=bool(connected[0,:].any() or connected[-1,:].any() or connected[:,0].any() or connected[:,-1].any())
    markers[[0,-1],:]=1;markers[:,[0,-1]]=1
    # Joint features preserve target edges and reference-supported differences.
    features=np.stack([t,np.clip(r,0,1),np.clip(delta,0,1)],axis=-1)
    features=np.rint(np.clip(features,0,1)*255).astype('uint8')
    if method=='watershed':
        watershed=cv2.watershed(features,markers)
        mask=watershed==2
    elif method=='graphcut':
        if fg.sum()<5 or (markers==1).sum()<5:
            return dict(valid=False,reason='insufficient_marker_pixels'),None
        gc=np.full(t.shape,cv2.GC_PR_BGD,np.uint8)
        gc[connected]=cv2.GC_PR_FGD
        gc[(markers==1)|(markers==3)]=cv2.GC_BGD
        gc[fg]=cv2.GC_FGD
        cv2.setRNGSeed(0)
        cv2.grabCut(features,gc,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),5,cv2.GC_INIT_WITH_MASK)
        mask=(gc==cv2.GC_FGD)|(gc==cv2.GC_PR_FGD)
        # Keep only the segment anchored to the original difference core.
        _,components,_,_=cv2.connectedComponentsWithStats(mask.astype('uint8'))
        core_ids=np.unique(components[fg]);core_ids=core_ids[core_ids!=0]
        mask=np.isin(components,core_ids)
    else:raise ValueError(method)
    yy,xx=np.where(mask)
    if not len(xx):return dict(valid=False,reason='empty_segmentation'),None
    bx,by,bw,bh=int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)
    closed=bx>1 and by>1 and bx+bw<t.shape[1]-1 and by+bh<t.shape[0]-1
    # Pixels assigned along a shared dark boundary are uncertain, not invented.
    border=cv2.dilate(mask.astype('uint8'),np.ones((3,3),np.uint8))>mask
    shared=(np.abs(delta)<=threshold)&(r<.5)&(t<.5)
    contact=int((border&shared).sum())
    return dict(valid=True,pad=pad,context_pad=context['pad'],box=[bx+x0,by+y0,bw,bh],
        area=int(mask.sum()),core_area=int(fg.sum()),core_preserved=bool(mask[fg].all()),
        original_difference_leaks_window=touches,
        closed=closed,shared_dark_boundary_pixels=contact,
        visible_difference_only=True), (mask,(x0,y0))


def mask_iou(a,b):
    am,(ax,ay)=a;bm,(bx,by)=b
    x,y=max(ax,bx),max(ay,by);X,Y=min(ax+am.shape[1],bx+bm.shape[1]),min(ay+am.shape[0],by+bm.shape[0])
    inter=int((am[y-ay:Y-ay,x-ax:X-ax]&bm[y-by:Y-by,x-bx:X-bx]).sum()) if X>x and Y>y else 0
    return inter/max(1,int(am.sum()+bm.sum())-inter)


def analyze_seed(reference,target,seed,threshold=.13,method='watershed',contexts=None):
    views=contexts if contexts is not None else [context_match(reference,target,seed,p) for p in RULES['pads']]
    result=dict(seed=seed,contexts=views,status='uncertain_correspondence',hypothesis_box=None,
                complete_object_verified=False,official_alarm=False,dino_evaluated=False)
    if not valid_context(views):return result,None
    segments=[region(reference,target,seed,v,p,threshold,method) for v in views for p in PADS]
    result['segments']=[s for s,_ in segments]
    if not all(s['valid'] and s['closed'] and s['core_preserved'] for s,_ in segments):
        result['status']='unstable_or_open_boundary';return result,None
    overlaps=[mask_iou(segments[0][1],z[1]) for z in segments[1:]]
    result['mask_iou_to_first']=overlaps
    if min(overlaps)<.8:
        result['status']='context_or_window_sensitive';return result,None
    # No score or answer chooses a preferred segmentation; first fixed view is
    # deterministic and the complete set remains in the evidence.
    s,mask=segments[0]
    result.update(status='stable_visible_difference_hypothesis',hypothesis_box=s['box'],
                  shared_dark_boundary=any(z['shared_dark_boundary_pixels'] for z,_ in segments))
    return result,mask
