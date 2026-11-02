"""Require a vacated source as well as an appearance match for object motion."""
import cv2
import numpy as np


def explain(ref,target,candidate,threshold):
    x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
    padding,radius=5,32
    x0,y0=x-padding,y-padding;x1,y1=x+w+padding,y+h+padding
    if x0<radius or y0<radius or x1+radius>=ref.shape[1] or y1+radius>=ref.shape[0]:return None
    patch=target[y0:y1,x0:x1].astype('float32')
    if patch.std()<.03:return None
    search=ref[y0-radius:y1+radius,x0-radius:x1+radius].astype('float32')
    scores=cv2.matchTemplate(search,patch,cv2.TM_CCOEFF_NORMED)
    _,score,_,point=cv2.minMaxLoc(scores)
    dx,dy=point[0]-radius,point[1]-radius
    if score<.92 or max(abs(dx),abs(dy))<4 or max(abs(dx),abs(dy))>=radius:return None
    second=scores.copy();second[max(0,point[1]-3):point[1]+4,max(0,point[0]-3):point[0]+4]=-1
    if score-float(second.max())<.04:return None
    normal=ref[y0+dy:y1+dy,x0+dx:x1+dx].astype('float32')
    context=np.ones(normal.shape,bool)
    context[padding:padding+h,padding:padding+w]=False
    a,b=normal[context],patch[context]
    # Fitting the moved object's own pixels can hide additional attenuation.
    gain=float(np.clip(np.cov(a,b)[0,1]/max(float(a.var()),.001),.7,1.4)) if a.std()>.03 else 1.
    offset=float(np.clip(np.median(b-gain*a),-.15,.15))
    fitted=np.clip(gain*normal+offset,0,1)
    if np.percentile(np.abs(fitted-patch),95)>.10:return None
    if np.percentile(np.abs(fitted[padding:padding+h,padding:padding+w]-patch[padding:padding+h,padding:padding+w]),95)>.08:return None
    old=ref[y+dy:y+h+dy,x+dx:x+w+dx]
    source_now=target[y+dy:y+h+dy,x+dx:x+w+dx]
    destination=target[y:y+h,x:x+w]
    appearance=ref[y:y+h,x:x+w]-destination
    disappearance=source_now-old
    # Source and destination must be disjoint, and comparable signed mass must
    # disappear from the old site. Merely finding another screw is insufficient.
    overlap=max(0,w-abs(dx))*max(0,h-abs(dy))
    if overlap:return None
    strong=appearance>threshold
    if strong.sum()<12:return None
    cleared=disappearance>threshold
    if cleared.sum()<.8*strong.sum():return None
    mass=float(np.maximum(disappearance,0).sum()/max(float(np.maximum(appearance,0).sum()),.001))
    if not .7<=mass<=1.4:return None
    if np.mean(disappearance[strong]>threshold)<.8:return None
    # A target patch must uniquely point back to its old reference location.
    backsearch=target[y0+dy-radius:y1+dy+radius,x0+dx-radius:x1+dx+radius]
    if backsearch.shape!=(patch.shape[0]+2*radius,patch.shape[1]+2*radius):return None
    back=cv2.matchTemplate(backsearch.astype('float32'),normal,cv2.TM_CCOEFF_NORMED)
    _,backscore,_,backpoint=cv2.minMaxLoc(back)
    if backscore<.92 or max(abs(backpoint[0]-radius+dx),abs(backpoint[1]-radius+dy))>1:return None
    return dict(method='reciprocal_object_transport',dx=dx,dy=dy,sim=score,
                cleared_fraction=float(cleared.sum()/strong.sum()),mass_ratio=mass,ratio=0.)
