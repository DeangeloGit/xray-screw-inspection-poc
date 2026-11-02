"""Explain local displacement using only the supplied reference and target.

Candidate pixels cannot choose the displacement or fit the exposure model.
Uncertain matches are retained, never treated as evidence of normality.
"""
import cv2
import numpy as np


def explain(ref, target, candidate, threshold):
    x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
    padding,radius=16,8
    x0,y0=max(radius,x-padding),max(radius,y-padding)
    x1,y1=min(ref.shape[1]-radius,x+w+padding),min(ref.shape[0]-radius,y+h+padding)
    if x0>x-3 or y0>y-3 or x1<x+w+3 or y1<y+h+3:return None
    patch=target[y0:y1,x0:x1].astype('float32')
    context=np.ones(patch.shape,np.uint8)
    context[y-y0-3:y+h-y0+3,x-x0-3:x+w-x0+3]=0
    outside=context>0
    if outside.sum()<400 or patch[outside].std()<.025:return None
    search=ref[y0-radius:y1+radius,x0-radius:x1+radius].astype('float32')
    choices=[]
    for sigma in (0.,.7,1.2,2.,3.):
        blurred=cv2.GaussianBlur(search,(0,0),sigma) if sigma else search
        scores=cv2.matchTemplate(blurred,patch,cv2.TM_CCOEFF_NORMED,mask=context)
        scores[~np.isfinite(scores)]=-1
        _,score,_,point=cv2.minMaxLoc(scores)
        choices.append((score,sigma,point,blurred,scores))
    score,sigma,point,blurred,scores=max(choices,key=lambda t:t[0])
    dx,dy=point[0]-radius,point[1]-radius
    before=float(choices[0][4][radius,radius])
    uniqueness=0.
    if score<.90 or sigma==0 or score<choices[0][0]+.005:return None
    if max(abs(dx),abs(dy))==radius:return None
    normal=blurred[point[1]:point[1]+patch.shape[0],point[0]:point[0]+patch.shape[1]]
    weights=context.astype('float32')
    for _ in range(4):
        mass=max(float(weights.sum()),.001)
        mx=float((weights*normal).sum()/mass);my=float((weights*patch).sum()/mass)
        gain=float(np.clip((weights*(normal-mx)*(patch-my)).sum()/max(float((weights*(normal-mx)**2).sum()),.001),.6,1.6))
        offset=float(np.clip(my-gain*mx,-.25,.25))
        fitted=np.clip(gain*normal+offset,0,1)
        error=np.abs(fitted-patch)
        weights=context*np.minimum(1,.04/np.maximum(error,.0001))**2
    core=(slice(y-y0,y+h-y0),slice(x-x0,x+w-x0))
    difference=fitted[core]-patch[core]
    positive=np.maximum(difference,0)
    original=np.maximum(ref[y:y+h,x:x+w]-target[y:y+h,x:x+w],0)
    ratio=float(positive.sum()/max(float(original.sum()),.001))
    _,_,stats,_=cv2.connectedComponentsWithStats((difference>threshold).astype('uint8'))
    remaining=int(max(stats[1:,cv2.CC_STAT_AREA],default=0))
    # Both polarities must agree: a nearby normal screw must not explain a
    # darker edge merely because the fitted reference is darker everywhere.
    absolute_p95=float(np.percentile(np.abs(difference),95))
    if ratio>.2 or remaining>=12 or absolute_p95>.10:return None
    return dict(method='context_blur_compensation',sigma=sigma,dx=dx,dy=dy,
                context_similarity=score,context_before=before,uniqueness=uniqueness,
                gain=gain,offset=offset,ratio=ratio,remaining=remaining,absolute_p95=absolute_p95)
