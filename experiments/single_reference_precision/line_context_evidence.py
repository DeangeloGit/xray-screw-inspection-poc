"""Test existing narrow line contrast using independent context on both ends.

No candidate pixels are used to fit either exposure model. Both end models
must predict the candidate, so an extra object cannot calibrate itself away.
"""
import numpy as np


def fit(normal, target, xpos):
    a=normal.ravel().astype('float64');b=target.ravel().astype('float64')
    x=xpos.ravel().astype('float64')
    design=np.column_stack([a,x,np.ones(len(a))])
    if np.std(a)<.02 or np.std(b)<.02:return None
    weights=np.ones(len(a))
    for _ in range(4):
        coef=np.linalg.lstsq(design*weights[:,None],b*weights,rcond=None)[0]
        error=design@coef-b
        weights=np.minimum(1,.025/np.maximum(np.abs(error),.0001))
    if not .5<=coef[0]<=6 or abs(coef[1])>.06:return None
    rmse=float(np.sqrt(np.mean(error**2)))
    if rmse>.035:return None
    # A flat gradient alone is insufficient evidence of an existing line.
    plane=np.column_stack([x,np.ones(len(a))])
    plane_error=plane@np.linalg.lstsq(plane,b,rcond=None)[0]-b
    if rmse>float(np.sqrt(np.mean(plane_error**2)))*.65:return None
    return coef,rmse


def explain(ref,target,candidate,threshold):
    x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
    if min(w,h)>5 or max(w,h)<12 or max(w,h)>80:return None
    if w>h:
        ref,target=ref.T,target.T
        x,y,w,h=y,x,h,w
    padding,band,gap=4,12,3
    if x<padding+3 or y<band+gap+3 or x+w+padding+3>=ref.shape[1] or y+h+band+gap+3>=ref.shape[0]:return None
    x0,x1=x-padding,x+w+padding
    bands=[(y-gap-band,y-gap),(y+h+gap,y+h+gap+band)]
    models=[]
    for dx in range(-2,3):
        fits=[]
        for ya,yb in bands:
            normal=ref[ya:yb,x0+dx:x1+dx];test=target[ya:yb,x0:x1]
            xx=np.broadcast_to(np.arange(x0,x1)-x,normal.shape)
            result=fit(normal,test,xx)
            if result is None:break
            fits.append(result)
        if len(fits)==2:models.append((sum(f[1] for f in fits),dx,fits))
    if not models:return None
    loss,dx,fits=min(models,key=lambda r:r[0])
    core=ref[y:y+h,x+dx:x+w+dx];test=target[y:y+h,x:x+w]
    xx=np.broadcast_to(np.arange(w),core.shape)
    errors=[]
    for coef,_ in fits:
        prediction=np.clip(coef[0]*core+coef[1]*xx+coef[2],0,1)
        delta=prediction-test
        p95=float(np.percentile(np.abs(delta),95))
        if p95>.08 or float(np.max(delta))>threshold:return None
        errors.append(p95)
    return dict(method='two_ended_line_context',dx=dx,dy=0,
                context_rmse=loss/2,absolute_p95=max(errors),
                gains=[float(f[0][0]) for f in fits],ratio=0.)
