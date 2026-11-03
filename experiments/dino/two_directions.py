"""Separate A reference-screen experiment from B false-negative audit; offline only."""
import sys,json,hashlib,math
from pathlib import Path
from collections import Counter
import numpy as np
import onnxruntime as ort
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.paired_review import BASE,read,digest
from dino_adapter import classify
OUT=ROOT/'workspace/dino-two-directions-20261103'
PRIOR=ROOT/'workspace/dino-paired-reference-20261103'
FONT=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',17)
def pairs(z,side=120):
    c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'));side=max(side,w+48,h+48)
    ims=[]
    for file in ['reference.png','aligned.png']:
        with Image.open(BASE/'photos'/z['sha']/file) as im:
            x0=max(0,min(im.width-side,x+w/2-side/2));y0=max(0,min(im.height-side,y+h/2-side/2))
            a=im.convert('RGB').crop((int(x0),int(y0),int(x0)+side,int(y0)+side));d=ImageDraw.Draw(a)
            d.rectangle((x-int(x0),y-int(y0),x+w-int(x0),y+h-int(y0)),outline='#e1263b',width=1);ims.append(a)
    return ims
def contacts(items,prefix):
    for start in range(0,len(items),12):
        batch=items[start:start+12];canvas=Image.new('RGB',(1000,280*math.ceil(len(batch)/2)),'white');d=ImageDraw.Draw(canvas)
        for j,z in enumerate(batch):
            col,row=j%2,j//2;xx,yy=col*500,row*280
            d.text((xx,yy),f'{start+j+1} | {Path(z["name"]).stem[-14:]} #{z["id"]}',font=FONT,fill='black')
            for k,im in enumerate(pairs(z)):canvas.paste(im.resize((245,245)),(xx+k*250,yy+30))
        canvas.save(OUT/f'{prefix}-{start//12+1}.jpg',quality=92)
def main():
    OUT.mkdir(exist_ok=True)
    rows=read(BASE/'report-rows.json');items=[]
    for row in rows:
        r=read(BASE/'photos'/row['sha256']/'result.json')
        for c in r['candidates']:
            items.append(dict(key=f'{row["sha256"]}-{c["id"]}',sha=row['sha256'],id=c['id'],name=row['relative'],machine=row['machine'],c=c))
    assert len(items)==330
    protected=[ROOT/'models/active.json',ROOT/'models/dino-examples-a3b8c97aa539/manifest.json',ROOT/'models/dino-examples-a3b8c97aa539/model.onnx',ROOT/'detector.py',ROOT/'dino_adapter.py',BASE/'results.json']
    protected += [BASE/'photos'/r['sha256']/'result.json' for r in rows]
    hashes={str(p):digest(p) for p in protected}
    plan=dict(rule='originally retained AND reference DINO screw_margin>=0 => would discard',scope='all 330 retained candidates; no difference rerun; no production changes',keys=[z['key'] for z in items],hashes=hashes)
    (OUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    m=read(ROOT/'models/dino-examples-a3b8c97aa539/manifest.json');opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1
    session=ort.InferenceSession(str(ROOT/'models/dino-examples-a3b8c97aa539/model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    cachepath=OUT/'reference-inference.json';cache=read(cachepath) if cachepath.exists() else {}
    old=read(PRIOR/'inference.json')
    for i,z in enumerate(items,1):
        key=z['key'];c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'))
        if key not in cache:
            if key in old:cache[key]=old[key]['reference']
            else:
                with Image.open(BASE/'photos'/z['sha']/'reference.png') as im:
                    crop=im.convert('L').crop((max(0,x-12),max(0,y-12),min(im.width,x+w+12),min(im.height,y+h+12)))
                    cache[key]=classify(m,session,np.asarray(crop,np.float32)/255)
            cachepath.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
        z['reference']=cache[key];z['would_discard']=cache[key]['screw_margin']>=0
        if i%30==0:print('REFERENCE',i,'/330',flush=True)
    changed=[z for z in items if z['would_discard']]
    (OUT/'a-cases.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
    contacts(changed,'a-review')
    suspects=read(PRIOR/'cases.json')['selected'];suspects=[z for z in suspects if z['label']=='NG' and z['removed']]
    contacts(suspects,'b-review')
    (OUT/'b-cases.json').write_text(json.dumps(suspects,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(digest(Path(p))==v for p,v in hashes.items())
    print('A',len(items),'would discard',len(changed),'B',len(suspects),flush=True)
if __name__=='__main__':main()
