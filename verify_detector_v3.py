"""Regression annotations are test-only and never read by the detector."""
import json
from pathlib import Path
import sys
import cv2
import numpy as np
from detector import machine_mask, proposals, prioritize


def run():
    ref=np.ones((384,384),np.float32)
    cv2.rectangle(ref,(35,35),(345,345),.3,12)
    cv2.line(ref,(170,65),(170,315),.2,4)
    mask=machine_mask(ref)
    assert mask[220,250], 'bright body cavity excluded'
    recessed=np.ones((384,384),np.float32)
    cv2.rectangle(recessed,(45,40),(340,340),.3,-1)
    cv2.rectangle(recessed,(250,130),(355,240),1.,-1)
    cv2.rectangle(recessed,(4,40),(12,340),.1,-1)  # separate fixture outside body
    envelope=machine_mask(recessed)
    assert envelope[185,300], 'open side recess excluded'
    assert not envelope[185,8], 'separate fixture included in main body envelope'
    target=ref.copy();cv2.ellipse(target,(178,200),(10,15),0,0,360,.1,-1)
    candidates,_=proposals(ref,target,mask,.13)
    assert any(c['x']<188 and c['y']<215 and c['x']+c['w']>168 and c['y']+c['h']>185 for c in candidates), 'edge-adjacent object lost'
    assert not proposals(ref,ref,mask,.1)[0]
    assert not proposals(ref,np.clip(ref*.8+.12,0,1),mask,.1)[0]
    if len(sys.argv)>1:
        case=np.load(sys.argv[1]);ref,target=case['ref'],case['target'];mask=machine_mask(ref)
        rois=[(1164,675,1203,715),(1210,669,1245,708),(1112,908,1147,945),
              (1100,1080,1145,1120),(1145,1140,1185,1180),(1210,1305,1250,1342)]
        report=[]
        for threshold in (.10,.13):
            candidates,_=proposals(ref,target,mask,threshold)
            hits=[]
            for x0,y0,x1,y1 in rois:
                matches=[c for c in candidates if c['x']<x1 and c['y']<y1 and c['x']+c['w']>x0 and c['y']+c['h']>y0]
                assert any(not prioritize(c) for c in matches), (threshold,(x0,y0,x1,y1))
                hits.append(len(matches))
            report.append(dict(threshold=threshold,total=len(candidates),high=sum(not prioritize(c) for c in candidates),marked_region_hits=hits))
        for label,control in [('exposure',np.clip(.8*ref+.12,0,1)),('translation',cv2.warpAffine(ref,np.float32([[1,0,2],[0,1,-1]]),(ref.shape[1],ref.shape[0]),borderValue=1))]:
            assert not proposals(ref,control,mask,.1)[0],label
        print(json.dumps(report))
    if len(sys.argv)>2:
        case=np.load(sys.argv[2]);ref,target=case['ref'],case['target'];mask=machine_mask(ref)
        assert mask[1180:1215,1355:1390].all()
        candidates,_=proposals(ref,target,mask,.20)
        hits=[c for c in candidates if c['x']<1390 and c['y']<1215 and c['x']+c['w']>1355 and c['y']+c['h']>1180]
        assert any(not prioritize(c) for c in hits), 'marked side screw absent at 0.20'
        print('Side screw at 0.20: total',len(candidates),'matching regions',len(hits))
    if len(sys.argv)>3:
        case=np.load(sys.argv[3]);ref,target=case['ref'],case['target'];mask=machine_mask(ref)
        candidates,_=proposals(ref,target,mask,.20)
        hits=[c for c in candidates if c['x']<1374 and c['y']<672 and c['x']+c['w']>1338 and c['y']+c['h']>633]
        assert any(c.get('recovery')=='tight_spatial_tolerance' for c in hits), 'small object beside normal structure missing'
        for label,control in [('exposure',np.clip(.8*ref+.12,0,1)),('translation',cv2.warpAffine(ref,np.float32([[1,0,2],[0,1,-1]]),(ref.shape[1],ref.shape[0]),borderValue=1))]:
            assert not proposals(ref,control,mask,.20)[0], label
        print('Upper small object at 0.20: total',len(candidates),'matching regions',len(hits))
    print('PASS: bright cavity coverage, edge-adjacent object, identical image, brightness-only control and optional six marked regions/translation control')

if __name__=='__main__':run()
