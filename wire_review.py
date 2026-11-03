"""Advisory wire evidence using one reference. Never use it to delete candidates."""
import cv2
import numpy as np


def review_evidence(ref,target,candidate,threshold):
    x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
    padding=45
    if x<padding or y<padding or x+w+padding>=ref.shape[1] or y+h+padding>=ref.shape[0]:return None
    a=ref[y-padding:y+h+padding,x-padding:x+w+padding].astype('float32')
    b=target[y-padding:y+h+padding,x-padding:x+w+padding].astype('float32')
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(11,11))
    ar=cv2.morphologyEx(a,cv2.MORPH_CLOSE,kernel)-a
    br=cv2.morphologyEx(b,cv2.MORPH_CLOSE,kernel)-b
    core=np.zeros(a.shape,bool);core[padding:padding+h,padding:padding+w]=True
    # A dark extra object raises the ridge threshold; surrounding faint wire
    # then cannot supply a continuous explanation for it.
    cutoff=max(.08,float(np.percentile(br[core],90))*.35)
    bm=(br>cutoff).astype('uint8');am=(ar>cutoff).astype('uint8')
    n,labels,stats,_=cv2.connectedComponentsWithStats(bm)
    overlaps=[int(((labels==i)&core).sum()) for i in range(1,n)]
    if not overlaps or max(overlaps)<max(10,.5*candidate['area']):return None
    label=int(np.argmax(overlaps))+1;component=labels==label
    cy,cx=np.where(component)
    length=float(np.hypot(np.ptp(cx),np.ptp(cy)))
    if length<max(45,2*max(w,h)):return None
    outside=cv2.dilate(core.astype('uint8'),np.ones((17,17),np.uint8))==0
    distance=cv2.distanceTransform(bm,cv2.DIST_L2,5)
    core_width=float(np.max(distance[core&component]))
    if core_width>2.8:return None
    # Require two distant reference-supported anchors outside the candidate.
    nearby=cv2.dilate(am,np.ones((7,7),np.uint8))>0
    anchors=component&outside&nearby
    ay,ax=np.where(anchors)
    if len(ax)<25 or np.hypot(np.ptp(ax),np.ptp(ay))<35:return None
    # A line ending near the candidate is not a two-sided explanation. In
    # particular, do not treat a screw attached to a wire as a wire extension.
    along=ax if w>=h else ay
    end=padding+(w if w>=h else h)
    if (along<padding-8).sum()<8 or (along>end+8).sum()<8:return None
    # The reference support must itself be a long, thin component, not a nearby screw.
    nr,rl,rs,_=cv2.connectedComponentsWithStats(am)
    supports=[]
    for i in range(1,nr):
        region=rl==i;yy,xx=np.where(region)
        if len(xx)<35 or np.hypot(np.ptp(xx),np.ptp(yy))<40:continue
        matched=(cv2.dilate(region.astype('uint8'),np.ones((7,7),np.uint8))>0)&anchors
        my,mx=np.where(matched);ma=mx if w>=h else my
        if len(ma)<20 or (ma<padding-8).sum()<8 or (ma>end+8).sum()<8:continue
        supports.append(region)
    if not supports:return None
    support=np.logical_or.reduce(supports)
    lost=float(np.maximum(ar-br,0)[support].sum())
    appeared=float(np.maximum(br-ar,0)[core&component].sum())
    if lost<max(1.,appeared*.7):return None
    ref_width=cv2.distanceTransform(am,cv2.DIST_L2,5)
    if core_width>float(np.percentile(ref_width[support],95))+.6:return None
    strength=float(np.percentile(br[core&component],95))
    normal_strength=float(np.percentile(ar[support],95))
    # High-attenuation edges and opaque small objects are deliberately outside
    # this wire-only rule; matching their thin silhouette is not sufficient.
    if strength>.45 or float(np.percentile(b[core&component],5))<.25:return None
    if strength>normal_strength*1.25+.025:return None
    # All strong candidate pixels must belong to this continuous line.
    strong=core&(br>max(.10,threshold))
    if strong.sum() and np.mean(component[strong])<.95:return None
    return dict(method='wire_continuity_review_only',length=length,
                core_radius=core_width,normal_strength=normal_strength,
                target_strength=strength,anchor_pixels=int(len(ax)),
                vacated_ridge_mass=lost,appeared_ridge_mass=appeared)
