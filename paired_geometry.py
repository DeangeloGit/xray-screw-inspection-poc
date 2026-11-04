"""Restricted local recheck geometry, promoted unchanged from the validated pilot."""
import cv2
import numpy as np

RULES=dict(context_padding=52,excluded_padding=12,search_radius=12,
           minimum_context_correlation=.75,change_threshold=.10,
           minimum_component_area=12,new_dark_share=.80,
           balanced_dark_share=[.25,.75],version='exploratory-v1')

def compare(ref,target,c):
    x,y,w,h=(c[k] for k in ('x','y','w','h'));p=RULES['context_padding'];r=RULES['search_radius'];e=RULES['excluded_padding']
    x0,y0=max(r,x-p),max(r,y-p);x1,y1=min(ref.shape[1]-r,x+w+p),min(ref.shape[0]-r,y+h+p)
    patch=target[y0:y1,x0:x1].astype('float32')
    mask=np.ones(patch.shape,'uint8');mask[max(0,y-e-y0):y+h+e-y0,max(0,x-e-x0):x+w+e-x0]=0
    search=ref[y0-r:y1+r,x0-r:x1+r].astype('float32')
    corr=cv2.matchTemplate(search,patch,cv2.TM_CCOEFF_NORMED,mask=mask);corr[~np.isfinite(corr)]=-1
    _,score,_,point=cv2.minMaxLoc(corr);dx,dy=point[0]-r,point[1]-r
    # Never allow a borderline/context-poor match to justify an exclusion.
    reliable=score>=RULES['minimum_context_correlation'] and max(abs(dx),abs(dy))<r
    normal=ref[y0+dy:y1+dy,x0+dx:x1+dx].astype('float32');weights=mask.astype('float32')
    for _ in range(4):
        mass=max(float(weights.sum()),.001);mx=float((weights*normal).sum()/mass);my=float((weights*patch).sum()/mass)
        gain=float(np.clip((weights*(normal-mx)*(patch-my)).sum()/max(float((weights*(normal-mx)**2).sum()),.001),.6,1.6))
        offset=float(np.clip(my-gain*mx,-.25,.25));fitted=np.clip(gain*normal+offset,0,1)
        error=np.abs(fitted-patch);weights=mask*np.minimum(1,.04/np.maximum(error,.0001))**2
    roi=(slice(y-e-y0,y+h+e-y0),slice(x-e-x0,x+w+e-x0));delta=(fitted-patch)[roi]
    positive=np.maximum(delta-RULES['change_threshold'],0);negative=np.maximum(-delta-RULES['change_threshold'],0)
    dark=float(positive.sum());light=float(negative.sum());share=dark/max(dark+light,.00001)
    n,labels,stats,centers=cv2.connectedComponentsWithStats((delta>RULES['change_threshold']).astype('uint8'))
    overlaps=set(np.unique(labels[e:e+h,e:e+w]))-{0}
    area=max([int(stats[i,cv2.CC_STAT_AREA]) for i in overlaps],default=0)
    p95=float(np.percentile(np.abs(delta),95));outcome='uncertain'
    if reliable:
        if area<RULES['minimum_component_area'] and p95<=.10:outcome='explained'
        elif area>=RULES['minimum_component_area'] and share>=RULES['new_dark_share']:outcome='new_alert'
        elif .25<=share<=.75:outcome='movement_hint'
    metrics=dict(outcome=outcome,context_reliable=reliable,context_correlation=score,dx=dx,dy=dy,gain=gain,offset=offset,dark_mass=dark,light_mass=light,dark_share=share,component_area=area,absolute_p95=p95)
    return metrics,delta,fitted[roi],patch[roi]

def extract(ref,tar,c):
    x,y,w,h=(c[k] for k in ['x','y','w','h']);metrics,*_=compare(ref,tar,c);dx,dy=metrics['dx'],metrics['dy'];e=32
    x0,y0=max(e,x-e),max(e,y-e);x1,y1=min(ref.shape[1]-e,x+w+e),min(ref.shape[0]-e,y+h+e)
    a=tar[y0:y1,x0:x1];b=ref[y0+dy:y1+dy,x0+dx:x1+dx];fitted=np.clip(metrics['gain']*b+metrics['offset'],0,1)
    delta=cv2.GaussianBlur(fitted-a,(3,3),.6);_,labels,stats,_=cv2.connectedComponentsWithStats((delta>.08).astype('uint8'))
    ids,counts=np.unique(labels[y-y0:y+h-y0,x-x0:x+w-x0],return_counts=True);hits=[(int(count),int(i)) for i,count in zip(ids,counts) if i]
    if not hits:return dict(valid=False,reason='no_component')
    selected=max(hits)[1];xx,yy,ww,hh,area=stats[selected].tolist();bx,by=x0+xx,y0+yy;side=max(ww,hh)
    return dict(valid=True,object_box=[bx,by,ww,hh],box=[round(bx+ww/2-side/2),round(by+hh/2-side/2),side],area=area,metrics=metrics)
