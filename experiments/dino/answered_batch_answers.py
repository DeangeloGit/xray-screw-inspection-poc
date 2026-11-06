"""Extract supplied red rectangles; register answers without consulting detections."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def extract(path, original):
    rgb = np.asarray(Image.open(path).convert('RGB'))
    r,g,b = rgb.astype(np.int16).transpose(2,0,1)
    red = ((r-g>65)&(r-b>65)&(r>140)).astype('uint8')
    # Rectangle interiors stay separate even where two answer outlines touch.
    closed = cv2.morphologyEx(red,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,hierarchy = cv2.findContours(closed,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for i,c in enumerate(contours):
        x,y,w,h=cv2.boundingRect(c)
        if hierarchy[0,i,3]>=0 and w>=7 and h>=7 and cv2.contourArea(c)>25:
            boxes.append([x,y,x+w-1,y+h-1])
    boxes.sort(key=lambda z:(z[1],z[0]))
    assert boxes, path
    a=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    scale=min(1.,1500/max(original.shape))
    target=cv2.resize(original,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    sift=cv2.SIFT_create(nfeatures=10000,contrastThreshold=.015)
    kb,db=sift.detectAndCompute(target,None)
    wins=[]
    for flip in (False,True):
        v=np.fliplr(a).copy() if flip else a
        mask=np.fliplr(red).copy() if flip else red
        allowed=(1-cv2.dilate(mask,np.ones((7,7),np.uint8)))*255
        ka,da=sift.detectAndCompute(v,allowed)
        matches=cv2.BFMatcher().knnMatch(da,db,k=2)
        good=[m for m,n in matches if m.distance<.7*n.distance]
        if len(good)<10:continue
        sa=np.float32([ka[m.queryIdx].pt for m in good])
        sb=np.float32([kb[m.trainIdx].pt for m in good])
        mat,valid=cv2.estimateAffine2D(sa,sb,method=cv2.RANSAC,ransacReprojThreshold=2,maxIters=5000)
        if valid is None:continue
        chosen=valid[:,0].astype(bool)
        err=np.linalg.norm(cv2.transform(sa[None],mat)[0]-sb,axis=1)
        wins.append((int(chosen.sum()),flip,mat,float(np.median(err[chosen])),float(np.percentile(err[chosen],95))))
    count,flip,mat,median,p95=max(wins,key=lambda z:z[0])
    v=np.fliplr(a).copy() if flip else a
    mask=np.fliplr(red).copy() if flip else red
    # Compare in answer coordinates to avoid inventing detail by enlarging screenshots.
    warped=cv2.warpAffine(target,cv2.invertAffineTransform(mat),(a.shape[1],a.shape[0]),borderValue=255)
    valid=(v<230)&(warped<230)&(cv2.dilate(mask,np.ones((7,7),np.uint8))==0)
    corr=float(np.corrcoef(v[valid],warped[valid])[0,1])
    assert count>=25 and p95<3 and corr>.85,(path,count,p95,corr)
    marks=[]
    for box in boxes:
        x,y,X,Y=box
        poly=np.float32([[x,y],[X,y],[X,Y],[x,Y]])
        if flip:poly[:,0]=a.shape[1]-1-poly[:,0]
        mapped=cv2.transform(poly[None],mat)[0]/scale
        marks.append(dict(id=len(marks)+1,answer_bbox=box,polygon=mapped.tolist(),center=mapped.mean(axis=0).tolist()))
    return dict(marks=marks,registration=dict(inliers=count,mirrored=flip,affine_to_resized_source=mat.tolist(),source_resize=scale,median_error=median,p95_error=p95,correlation=corr))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    out=args.output;plan=read(out/'plan.json');result={}
    (out/'answer-audit').mkdir(exist_ok=True)
    for row in plan['items']:
        if not row['answer']:continue
        original=np.asarray(Image.open(row['path']).convert('L'))
        answer=extract(row['answer'],original)
        im=Image.fromarray(original).convert('RGB');draw=ImageDraw.Draw(im)
        for m in answer['marks']:
            p=[tuple(z) for z in m['polygon']];draw.line(p+[p[0]],fill='red',width=5)
            draw.text(tuple(m['center']),str(m['id']),fill='red',stroke_width=2)
        im.thumbnail((1000,1000));im.save(out/'answer-audit'/f'{row["key"]}.jpg',quality=95)
        result[row['key']]=answer
        print(row['key'],len(answer['marks']),answer['registration'],flush=True)
    (out/'answers.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
