"""Context-only monotonic exposure calibration with spatial holdout checks."""
import cv2
import numpy as np


def curve(a,b):
    order=np.argsort(a);a=a[order];b=b[order]
    groups=np.array_split(np.arange(len(a)),16)
    points=[]
    for group in groups:
        if len(group)<8:continue
        x=float(np.median(a[group]));y=float(np.median(b[group]))
        if points and abs(x-points[-1][0])<.005:
            points[-1][1].extend(b[group].tolist())
        else:points.append([x,b[group].tolist()])
    if len(points)<5:return None
    xs=np.array([p[0] for p in points]);ys=np.array([np.median(p[1]) for p in points])
    blocks=[]
    for i,y in enumerate(ys):
        blocks.append([i,i,float(y),len(points[i][1])])
        while len(blocks)>1 and blocks[-2][2]>blocks[-1][2]:
            q=blocks.pop();p=blocks.pop();mass=p[3]+q[3]
            blocks.append([p[0],q[1],(p[2]*p[3]+q[2]*q[3])/mass,mass])
    for lo,hi,y,_ in blocks:ys[lo:hi+1]=y
    return xs,ys


def explain(ref,target,candidate,threshold):
    x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
    pad=24
    if min(x,y)<pad or x+w+pad>=ref.shape[1] or y+h+pad>=ref.shape[0]:return None
    a=ref[y-pad:y+h+pad,x-pad:x+w+pad]
    b=target[y-pad:y+h+pad,x-pad:x+w+pad]
    context=np.ones(a.shape,bool);context[pad-3:pad+h+3,pad-3:pad+w+3]=False
    if a[context].std()<.025 or b[context].std()<.025:return None
    corr=float(np.corrcoef(a[context],b[context])[0,1])
    if corr<.85:return None
    yy,xx=np.indices(a.shape);partition=(yy//6+xx//6)%2==0
    errors=[]
    for side in (partition,~partition):
        result=curve(a[context&side],b[context&side])
        if result is None:return None
        xs,ys=result
        hold=context&~side
        if np.percentile(np.abs(np.interp(a[hold],xs,ys)-b[hold]),90)>.07:return None
        core=a[pad:pad+h,pad:pad+w];test=b[pad:pad+h,pad:pad+w]
        if core.min()<xs[0]-.01 or core.max()>xs[-1]+.01:return None
        delta=np.interp(core,xs,ys)-test
        if np.percentile(np.abs(delta),95)>.08:return None
        ratio=float(np.maximum(delta,0).sum()/max(float(np.maximum(core-test,0).sum()),.001))
        if ratio>.2:return None
        _,_,stats,_=cv2.connectedComponentsWithStats((delta>threshold).astype('uint8'))
        if max(stats[1:,cv2.CC_STAT_AREA],default=0)>=12:return None
        errors.append(float(np.percentile(np.abs(delta),95)))
    return dict(method='context_monotonic_tone_curve',dx=0,dy=0,context_similarity=corr,
                absolute_p95=max(errors),ratio=ratio)
