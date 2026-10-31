from pathlib import Path
import cv2, numpy as np, json
ROOT=Path(__file__).resolve().parent

def read(path):
    a=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
    if a is None: raise ValueError('無法讀取影像')
    if a.ndim==3: a=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY)
    lo,hi=np.percentile(a,[1,99])
    return np.clip((a.astype(np.float32)-lo)/max(float(hi-lo),1),0,1)

def detect(reference,target,name,threshold=0.13):
    ref=read(reference); raw=read(target)
    scale=0.5
    r=cv2.resize(ref,None,fx=scale,fy=scale)
    orb=cv2.ORB_create(nfeatures=7000)
    kr,dr=orb.detectAndCompute((r*255).astype('uint8'),None)
    best=None
    for rotation in range(4):
        t=cv2.resize(np.rot90(raw,rotation).copy(),(r.shape[1],r.shape[0]))
        kt,dt=orb.detectAndCompute((t*255).astype('uint8'),None)
        if dt is None or dr is None: continue
        pairs=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(dt,dr,k=2)
        good=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<0.72*n.distance]
        if len(good)<10: continue
        src=np.float32([kt[m.queryIdx].pt for m in good]); dst=np.float32([kr[m.trainIdx].pt for m in good])
        M,inside=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=2)
        if M is None: continue
        count=int(inside.sum())
        if best is None or count>best[0]: best=(count,rotation,M,t)
    if best is None or best[0]<25: raise ValueError('對齊失敗，需人工複核')
    count,rotation,M,t=best
    aligned=cv2.warpAffine(t,M,(r.shape[1],r.shape[0]),borderValue=1)
    valid=cv2.warpAffine(np.ones(t.shape,np.uint8),M,(r.shape[1],r.shape[0]))>0
    # Machine mask: exclude blank field and isolated external fixtures using normal reference.
    mask=(r<0.65).astype('uint8')
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((31,31),np.uint8))
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask)
    if n>1: mask=(labels==(1+np.argmax(stats[1:,cv2.CC_STAT_AREA]))).astype('uint8')
    mask=cv2.erode(mask,np.ones((11,11),np.uint8)).astype(bool)&valid
    # Local high-pass removes gradual exposure drift; signed residual retains extra attenuation.
    rh=r-cv2.GaussianBlur(r,(0,0),15); th=aligned-cv2.GaussianBlur(aligned,(0,0),15)
    residual=rh-th
    # Suppress residual bands around existing normal metal edges (registration tolerance).
    edges=cv2.Canny((r*255).astype('uint8'),40,100)
    edge_band=cv2.dilate(edges,np.ones((9,9),np.uint8))>0
    binary=((residual>threshold)&mask&~edge_band).astype('uint8')
    binary=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((2,2),np.uint8))
    n,lab,stats,_=cv2.connectedComponentsWithStats(binary)
    candidates=[]
    for i in range(1,n):
        x,y,w,h,area=map(int,stats[i])
        if 12<=area<=1800 and 4<=max(w,h)<=110:
            score=float(np.percentile(residual[lab==i],90))
            candidates.append(dict(x=x,y=y,w=w,h=h,area=area,score=round(score,4)))
    candidates.sort(key=lambda c:c['score'],reverse=True)
    out=ROOT/'outputs'/name; out.mkdir(parents=True,exist_ok=True)
    canvas=cv2.cvtColor((aligned*255).astype('uint8'),cv2.COLOR_GRAY2BGR)
    for i,c in enumerate(candidates):
        x,y,w,h=[c[k] for k in ('x','y','w','h')]
        cv2.rectangle(canvas,(x-5,y-5),(x+w+5,y+h+5),(0,165,255),2)
        cv2.putText(canvas,str(i+1),(x,y-8),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,165,255),1)
        pad=30; crop=aligned[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad]
        cv2.imwrite(str(out/f'crop_{i+1}.png'),(crop*255).astype('uint8'))
    cv2.imwrite(str(out/'overlay.png'),canvas)
    cv2.imwrite(str(out/'reference.png'),(r*255).astype('uint8'))
    cv2.imwrite(str(out/'aligned.png'),(aligned*255).astype('uint8'))
    heat=np.clip(residual/0.3,0,1)
    heat[~mask]=0
    cv2.imwrite(str(out/'difference.png'),cv2.applyColorMap((heat*255).astype('uint8'),cv2.COLORMAP_INFERNO))
    # Coordinates are in the normal reference frame, not the unrotated input.
    result=dict(name=name,status='需人工複核',rotation_ccw=rotation*90,inliers=count,threshold=threshold,coordinate_frame='reference preview, 1536 × 1536',matrix=M.tolist(),candidates=candidates,warning='候選分數是差分強度，不是螺絲機率；未檢出不代表 OK。')
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    for name in ['ok_0','ng_5','ng_9']:
        result=detect(ROOT/'data/ok_0.png',ROOT/f'data/{name}.png',name)
        print(name,'rotation',result['rotation_ccw'],'inliers',result['inliers'],'candidates',len(result['candidates']))
