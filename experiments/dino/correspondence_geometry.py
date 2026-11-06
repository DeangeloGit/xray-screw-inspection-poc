"""Image-only reference correspondence and complete local contour candidates."""
import cv2
import numpy as np

def template_matches(ref,target,c,search=40):
    x,y,w,h=(int(c[k]) for k in ('x','y','w','h'));rows=[]
    if max(w,h)>80 or min(w,h)<5:return rows
    for pad in (4,8,16):
        x0,y0=max(0,x-pad),max(0,y-pad);X,Y=min(target.shape[1],x+w+pad),min(target.shape[0],y+h+pad)
        sx,sy=max(0,x0-search),max(0,y0-search);sX,sY=min(ref.shape[1],X+search),min(ref.shape[0],Y+search)
        tpl=target[y0:Y,x0:X].astype('float32');area=ref[sy:sY,sx:sX].astype('float32')
        if tpl.std()<.025:return []
        _,score,_,loc=cv2.minMaxLoc(cv2.matchTemplate(area,tpl,cv2.TM_CCOEFF_NORMED))
        dx,dy=loc[0]+sx-x0,loc[1]+sy-y0
        rows.append(dict(pad=pad,score=score,dx=dx,dy=dy))
    return rows

def strong_match(rows):
    return bool(len(rows)==3 and min(r['score'] for r in rows[:2])>=.94 and rows[2]['score']>=.86
                and 4<=max(abs(rows[0]['dx']),abs(rows[0]['dy']))<=36
                and all(max(abs(r[k]-rows[0][k]) for k in ('dx','dy'))<=2 for r in rows))

def contours(target,c):
    x,y,w,h=(int(c[k]) for k in ('x','y','w','h'));pad=20;x0,y0=max(0,x-pad),max(0,y-pad)
    roi=target[y0:y+h+pad,x0:x+w+pad];rows=[]
    for cutoff in (.2,.3,.4,.5):
        binary=cv2.morphologyEx((roi<cutoff).astype('uint8'),cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
        n,labels,stats,centers=cv2.connectedComponentsWithStats(binary)
        for i in range(1,n):
            xx,yy,ww,hh,area=map(int,stats[i]);xx+=x0;yy+=y0
            inter=max(0,min(x+w,xx+ww)-max(x,xx))*max(0,min(y+h,yy+hh)-max(y,yy))
            if inter<.25*w*h or area<20 or max(ww,hh)>45 or max(ww,hh)>2.5*min(ww,hh):continue
            rows.append(dict(box=[xx,yy,ww,hh],cutoff=cutoff,area=area,fill=area/(ww*hh),coverage=inter/(w*h)))
    return rows
