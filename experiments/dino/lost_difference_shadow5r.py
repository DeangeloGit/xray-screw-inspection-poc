"""Offline audit of differences suppressed by spatial tolerance; no alarm writes.

All pixel gates reuse existing detector/structure checks. No answer coordinates,
filenames or DINO scores select seeds. Uncertain context remains visible.
"""
import cv2
import numpy as np
from structure_shadow5r import RULES
from ok_reference_shadow5r import context_match
from enclosure_rescue5r import geometry
VERSION='5r-lost-difference-offline-20261120'

def analyze(reference,target,mask,threshold=.13):
    import detector
    predicted=detector.compensate_brightness(reference,target)
    delta=predicted-target
    main=cv2.erode(predicted,np.ones((7,7),np.uint8))-target
    opened=cv2.morphologyEx(((delta>threshold)&mask).astype('uint8'),cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    n,labels,stats,_=cv2.connectedComponentsWithStats(opened)
    rows=[]
    for ident,(x,y,w,h,area) in enumerate(stats[1:],1):
        x,y,w,h,area=map(int,(x,y,w,h,area))
        if not (12<=area<=1800 and 4<=max(w,h)<=110):continue
        component=labels[y:y+h,x:x+w]==ident
        surviving=int(((main[y:y+h,x:x+w]>threshold)&component).sum())
        if surviving>=12:continue
        seed=dict(x=x,y=y,w=w,h=h)
        obj=geometry(target,seed)
        box=obj['extent'] if obj else [x,y,w,h]
        c=dict(zip(('x','y','w','h'),box));views=[]
        for pad in RULES['pads']:
            v=context_match(reference,target,c,pad)
            if v['valid']:
                a,b,u,z=box;dx,dy=v['dx'],v['dy']
                res=reference[b+dy:b+z+dy,a+dx:a+u+dx]*v['gain']+v['offset']-target[b:b+z,a:a+u]
                _,_,ss,_=cv2.connectedComponentsWithStats((res>threshold).astype('uint8'))
                v['remaining_pixels']=int((res>threshold).sum());v['largest_component']=int(ss[1:,4].max()) if len(ss)>1 else 0
            views.append(v)
        valid=all(v['valid'] and v['score']>=RULES['minimum_correlation'] and max(abs(v['dx']),abs(v['dy']))<RULES['search'] and RULES['gain_bounds'][0]<=v['gain']<=RULES['gain_bounds'][1] for v in views)
        consistent=valid and all(abs(views[0][k]-views[1][k])<=RULES['maximum_offset_disagreement'] for k in ('dx','dy'))
        if not consistent:state='uncertain_correspondence'
        elif all(v['largest_component']>=RULES['minimum_component_area'] for v in views):state='unexplained_difference'
        elif all(v['remaining_pixels']==0 for v in views):state='explained_by_context_motion'
        else:state='uncertain_residual'
        rows.append(dict(id=len(rows)+1,seed=seed,area=area,main_surviving_pixels=surviving,box=box,stable_object=obj,views=views,state=state,dino_evaluated=False,official_alarm=False))
    return dict(version=VERSION,mode='offline_observation_only',threshold=threshold,rows=rows,official_decisions_changed=False)
