"""Opt-in r3 experiment for recovering screws and filtering the added alarms."""
import hashlib
import os

import cv2
import numpy as np

from dino_adapter import input_image, paired_decision
from dino_paired_optimized import adjusted_image

VERSION = 'dino-r3-overkill-pilot-20261105'
FEATURE_SHA256 = 'de920d9986bce02b3e8447520a4a634c55a8f8f39876a12d562e04b66d5b378a'
SIDE_SCREWS = set(range(19, 33)) | set(range(35, 43)) | {45, 47}


def enabled(snapshot):
    return (os.environ.get('XRAY_OVERKILL_PILOT') == '1'
            and snapshot.manifest.get('feature_sha256') == FEATURE_SHA256
            and snapshot.session is not None and snapshot.feature_bank is not None)


def similarity_recovery(ref, target, candidate, threshold, evidence_fn):
    x, y, w, h = candidate_box(candidate)
    if min(w, h) < 5 or max(w, h) > 32 or max(w, h) > 2 * min(w, h):
        return None
    if not 25 <= candidate['area'] <= 300 or candidate['fill'] < .35:
        return None
    evidence = evidence_fn(ref, target, candidate, threshold)
    if (evidence.get('context_supported') and evidence['ratio'] >= .75
            and evidence['remaining'] >= 25):
        return evidence
    return None


def overlapping(candidate, previous):
    x, y, w, h = candidate_box(candidate)
    for item in previous:
        a, b, u, v = candidate_box(item)
        overlap = max(0, min(x+w, a+u)-max(x, a)) * max(0, min(y+h, b+v)-max(y, b))
        if overlap > .25 * min(w*h, u*v):
            return True
    return False


def structure_rules(ref, target, candidate):
    record = dict(box=candidate_box(candidate), shape=shape(target, candidate),
                  match={f'{pad}-{rad}': measure_match(ref, target, candidate, pad, rad)
                         for pad, rad in ((2, 6), (4, 10), (6, 24), (10, 38))})
    record['plug'] = [v for level in (.08, .14, .20) for v in signatures(record, (ref, target), level)]
    rules = []
    if same_hole(record):
        rules.append('hole')
    if same_connector(record):
        rules.append('wire')
    board = same_board(record)
    if board:
        rules.append(board)
    return rules


def apply(snapshot, ref, target, candidate, prediction):
    if prediction.get('status') != 'active':
        return prediction
    recovered = candidate.get('recovery') == 'overkill_pilot_similarity'
    initial_keep = prediction['filter_recommendation'] == 'keep'
    if initial_keep and not recovered:
        return prediction
    pair = prediction['paired_evidence']
    route = 'A' if recovered else ''
    if pair['target']['label'] != 'screw' and max(candidate['w'], candidate['h']) <= 45:
        left, right = (a[select(candidate, 4)] for a in (ref, target))
        if min(left.shape) >= 4:
            manifest = snapshot.manifest
            weights = core_mask(manifest, left, right)
            if weights is not None:
                images = [adjusted_image(manifest, im) for im in (left, right)]
                margins = combined(compare_scores(snapshot, images, weights))
                if margins and margins[0] < 0 <= margins[1]:
                    sides = [dict(label='screw' if score >= 0 else 'non_screw', screw_margin=score,
                                  input_sha256=hashlib.sha256(im.tobytes()).hexdigest())
                             for im, score in zip(images, margins)]
                    prediction = dict(prediction, **paired_decision(sides[1], sides[0]), action='manual_review',
                                      paired_recheck={'performed': False})
                    route = 'A+B' if recovered else 'B'
    if not route:
        return prediction
    rules = structure_rules(ref, target, candidate) if prediction['filter_recommendation'] == 'keep' else []
    if rules:
        prediction = dict(prediction, action='discard', label='non_screw', filter_recommendation='exclude',
                          decision_reason='雙圖重看後，附近的正常結構可解釋候選，排除')
    return dict(prediction, overkill_pilot=dict(route=route, rules=rules))


def crop(im,x,y,w,h):
    return im[y:y+h,x:x+w]


def candidate_box(c):
    return tuple(c[k] for k in ('x','y','w','h'))


def masked_fit(a,b,where):
    sel=(where>0)&np.isfinite(a)&np.isfinite(b)
    ra,rb=a[sel],b[sel]
    if len(ra)<15 or min(ra.std(),rb.std())<.02:
        return 0.,9.,0.,0.
    gain,off=np.linalg.lstsq(np.c_[ra,np.ones_like(ra)],rb,rcond=None)[0]
    err=np.abs(gain*ra+off-rb)
    return float(np.corrcoef(ra,rb)[0,1]),float(np.quantile(err,.85)),float(gain),float(off)


def measure_match(ref,test,c,pad,radius):
    x,y,w,h=candidate_box(c)
    x0,y0=x-pad,y-pad
    cw,ch=w+2*pad,h+2*pad
    patch=crop(test,x0,y0,cw,ch)
    max_h,max_w=test.shape
    sx0,sy0=max(0,x0-radius),max(0,y0-radius)
    sx1,sy1=min(max_w,x0+cw+radius),min(max_h,y0+ch+radius)
    search=ref[sy0:sy1,sx0:sx1]
    if min(x0,y0)<0 or x0+cw>max_w or y0+ch>max_h or patch.std()<.025:
        return {}
    scores=cv2.matchTemplate(search,patch,cv2.TM_CCOEFF_NORMED)
    _,score,_,(ix,iy)=cv2.minMaxLoc(scores)
    lx,ly=sx0+ix,sy0+iy
    other=crop(ref,lx,ly,cw,ch)
    dx,dy=lx-x0,ly-y0
    ring=np.ones_like(patch)
    ring[max(0,pad-1):pad+h+1,max(0,pad-1):pad+w+1]=0
    corr,err,gain,off=masked_fit(other,patch,np.ones_like(ring))
    rc,re,_,_=masked_fit(other,patch,ring)
    cc,ce,_,_=masked_fit(other,patch,1-ring)
    return dict(score=float(score),dx=dx,dy=dy,err=err,rc=rc,re=re,cc=cc,ce=ce,gain=gain,off=off,
                match_dark=float(np.quantile(other[1-ring>0],.25)),test_dark=float(np.quantile(patch[1-ring>0],.25)))


def shape(test,c):
    x,y,w,h=candidate_box(c)
    p=28
    x0,y0=max(0,x-p),max(0,y-p)
    patch=test[y0:y+h+p,x0:x+w+p]
    bx,by=x-x0,y-y0
    inside=np.zeros(patch.shape,bool)
    inside[by:by+h,bx:bx+w]=True
    pixels=patch[inside]
    results=[]
    for cutoff in [float(np.median(pixels))+.025,float(np.quantile(pixels,.7))+.08]:
        dark=(patch<min(.9,cutoff)).astype('uint8')
        count,labels,stats,_=cv2.connectedComponentsWithStats(dark)
        weights=np.bincount(labels[inside],minlength=count)
        weights[0]=0
        if weights.max()<4:
            results.append({})
            continue
        i=int(weights.argmax())
        component=labels==i
        a,b,u,v,area=(int(j) for j in stats[i])
        contours,_=cv2.findContours(component.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cnt=max(contours,key=cv2.contourArea)
        contour_area=float(cv2.contourArea(cnt)); arc=float(cv2.arcLength(cnt,True))
        mx=int(max(bx-a,a+u-bx-w)); my=int(max(by-b,b+v-by-h))
        m=np.zeros(patch.shape,bool)
        m[max(0,by-4):by+h+4,max(0,bx-4):bx+w+4]=True
        results.append(dict(box=[a+x0,b+y0,u,v],area=area,overlap=int(weights[i]),inner_ratio=float((component&m).sum()/area),
                            density=area/(u*v),mx=mx,my=my,circularity=4*np.pi*contour_area/max(arc**2,1),
                            dark_cutoff=cutoff))
    return results


def components(image,level):
    dark=(image<level).astype('uint8')
    if level!=.14:
        dark=cv2.morphologyEx(dark,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    cnt,labels,stats,centers=cv2.connectedComponentsWithStats(dark)
    h,w=image.shape
    for i in range(1,cnt):
        x,y,bw,bh,area=map(int,stats[i])
        if 4<=bw<=16 and 4<=bh<=16 and 22<=area<=170 and x>2 and y>2 and x+bw<w-2 and y+bh<h-2:
            yield (x,y,bw,bh,area,labels==i,centers[i])


def wire_tail(img,blob):
    x,y,w,h,area,mask,center=blob
    # Detect a faint dark ridge extending away from the opaque plug.
    close=cv2.morphologyEx(img,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    ridge=close-img
    outside=cv2.dilate(mask.astype('uint8'),np.ones((5,5),np.uint8))==0
    grid=np.indices(img.shape)
    dist=np.hypot(grid[1]-center[0],grid[0]-center[1])
    near=dist<9
    out=[]
    for cutoff in (.035,.05,.075):
        lines=((ridge>cutoff)&outside).astype('uint8')
        n,labels,stats,_=cv2.connectedComponentsWithStats(lines)
        good=[]
        for i in np.unique(labels[near]):
            if not i:continue
            xx,yy,ww,hh,a=stats[i]
            if a<8:continue
            rr=dist[labels==i]
            good.append((float(rr.max()-rr.min()),int(a)))
        out.append(max(good,default=(0.,0))[0])
    return out


def signatures(z,ims,level):
    x,y,w,h=z['box'];cx,cy=x+w/2,y+h/2
    x0,y0=max(0,int(cx)-35),max(0,int(cy)-35)
    a,b=[a[y0:int(cy)+36,x0:int(cx)+36] for a in ims]
    cand=np.zeros(a.shape,bool)
    cand[y-y0:y-y0+h,x-x0:x-x0+w]=True
    result=[]
    for tar in components(b,level):
        overlap=int((tar[5]&cand).sum())
        if overlap<max(6,tar[4]*.25):
            continue
        for ref in components(a,level):
            delta=ref[-1]-tar[-1]
            distance=float(np.linalg.norm(delta))
            if distance>16:continue
            dims=min(min(tar[i],ref[i])/max(tar[i],ref[i]) for i in (2,3,4))
            if dims<.52:continue
            def symbol(blob):
                x,y,w,h=blob[:4]
                return cv2.resize(blob[5][y:y+h,x:x+w].astype('uint8'),(32,32),interpolation=cv2.INTER_NEAREST)>0
            l,r=map(symbol,(ref,tar))
            overlap2=float(np.logical_and(l,r).sum()/np.logical_or(l,r).sum())
            result.append(dict(level=level,dx=float(delta[0]),dy=float(delta[1]),distance=distance,dims=dims,iou=overlap2,
                               tails=[wire_tail(a,ref),wire_tail(b,tar)],targets=[list(tar[:5]),list(ref[:5])]))
    return result


def drift(a,b=None):
    if b is None:
        b={'dx':0,'dy':0}
    return max(abs(a[k]-b[k]) for k in ('dx','dy'))


def same_hole(z):
    small,mid,near=z['match']['2-6'],z['match']['4-10'],z['match']['6-24']
    core=z['shape'][0]
    if not all((small,mid,near,core)):
        return False
    return (core['circularity']>=.82 and core['inner_ratio']>=.8
            and mid['score']>=.87 and near['score']>=.87 and mid['match_dark']<.60
            and drift(mid)<=2 and drift(mid,near)<=1)


def same_connector(z):
    # Require a matching dark plug in both images, plus a thin dark ridge
    # running from its neighborhood in both images.
    return any(p['distance']<=12 and p['iou']>=.72 and min(max(t) for t in p['tails'])>=22
               for p in z['plug'])


def same_board(z):
    x,y,w,h=z['box']
    core,outer=z['shape']
    near,wide=z['match']['6-24'],z['match']['10-38']
    corner=bool(max(w,h)<=9 and outer and outer['inner_ratio']<=.2
                and min(outer['box'][2:])>=2*max(w,h))
    border=bool(core and core['inner_ratio']<=.2 and near and near['score']>=.65
                and near['err']<=.10 and near['rc']>=.65)
    component=bool(near and wide and near['score']>=.86 and wide['score']>=.82
                   and wide['rc']>=.70 and drift(wide)<=5 and drift(near,wide)<=2)
    return next((name for name,yes in [('corner',corner),('border',border),('component',component)] if yes),'')


def select(c,pad):
    x,y,w,h=[c[k] for k in ('x','y','w','h')]
    return np.s_[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad]


def compare_scores(snap,views,mask=None):
    m=snap.manifest
    pos=len(m['example_bank']['screw']['ids'])
    bank=snap.feature_bank
    local,focused,side=[],[],[]
    for im in views:
        a=np.asarray(im,np.float32)/255
        a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
        raw=snap.session.run(None,{snap.session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0]
        vectors=[raw[1:].mean(axis=0)]
        vectors.append((raw[1:]*mask[:,None]).sum(axis=0))
        vectors=[v/np.linalg.norm(v) for v in vectors]
        margins=[]
        for i,v in enumerate(vectors):
            similarities=bank[:,0,1]@v
            margins.append(float(np.sort(similarities[:pos])[-3:].mean()-np.sort(similarities[pos:])[-3:].mean()))
            if i==0:
                side_scores=similarities[[j-1 for j in sorted(SIDE_SCREWS)]]
                head_scores=similarities[[j-1 for j in range(1,pos+1) if j not in SIDE_SCREWS]]
                side.append(float(np.sort(side_scores)[-3:].mean()-np.sort(head_scores)[-3:].mean()))
        local.append(margins[0])
        focused.append(margins[1])
    return dict(local=local,focused=focused,side_margin=side)


def core_mask(m,left,right):
    # The same location map is used for both images, derived from new darkness.
    delta=np.maximum(left-right-.13,0)
    dm=np.asarray(input_image(m,np.clip(delta,0,1)).convert('L'),np.float32)/255
    weights=cv2.resize(dm,(16,16),interpolation=cv2.INTER_AREA).reshape(-1)
    return weights if weights.max()>.03 else None


def combined(scores):
    if not scores.get('focused') or scores['side_margin'][1]<=0:
        return []
    return [(a+b)/2 for a,b in zip(scores['local'],scores['focused'])]
