"""Image-only exposed-part proposals beside opaque components; no truth or IDs."""
import cv2,numpy as np

def proposals(ref,target):
    n,labels,stats,_=cv2.connectedComponentsWithStats((target<.15).astype('uint8'));out=[]
    for ident in range(1,n):
        x,y,w,h,area=map(int,stats[ident])
        if not (150<=area<=2500 and 15<=max(w,h)<=100 and min(w,h)>=8):continue
        inset=max(2,round(min(w,h)*.1));bands=[('left',x-15,y+inset,x-1,y+h-inset),('right',x+w+1,y+inset,x+w+15,y+h-inset),('top',x+inset,y-15,x+w-inset,y-1),('bottom',x+inset,y+h+1,x+w-inset,y+h+15)]
        for side,x0,y0,X,Y in bands:
            x0=max(0,x0);y0=max(0,y0);X=min(target.shape[1],X);Y=min(target.shape[0],Y)
            t=target[y0:Y,x0:X];r=ref[y0:Y,x0:X]
            if min(t.shape)<3:continue
            binary=((t>.18)&(t<.8)).astype('uint8');binary=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
            count,ll,ss,_=cv2.connectedComponentsWithStats(binary)
            for j in range(1,count):
                a,b,u,v,mass=map(int,ss[j])
                if not (10<=mass<=450 and 3<=min(u,v) and max(u,v)<=35 and max(u,v)<=4*min(u,v)):continue
                mask=ll[b:b+v,a:a+u]==j;delta=(r-t)[b:b+v,a:a+u];changed=(delta>.10)&mask
                if changed.sum()<8:continue
                extent=[a+x0,b+y0,u,v]
                if any(z['box']==extent for z in out):continue
                out.append(dict(box=extent,occluder_box=[x,y,w,h],area=mass,mask=mask,side=side,changed_pixels=int(changed.sum()),mean_difference=float(delta[mask].mean())))
    return out

def part_image(array,extent):
    # A square white canvas preserves the part aspect ratio. No occluder or
    # contextual padding pixels are sampled; only the exposed-part rectangle.
    x,y,w,h=extent;s=max(w,h)+4;out=np.ones((s,s),np.float32);xx=(s-w)//2;yy=(s-h)//2
    out[yy:yy+h,xx:xx+w]=array[y:y+h,x:x+w]
    return out
