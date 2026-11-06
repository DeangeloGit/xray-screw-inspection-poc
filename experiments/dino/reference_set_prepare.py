"""Map existing answer regions to paired images; preserve all source labels."""
import os,sys,json,hashlib
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-4r-reference-set-20261106';PRIOR=ROOT/'workspace/dino-4r-crossbatch-20261106'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
read=lambda p:json.loads(p.read_text(encoding='utf8'))
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def flow_for(r,shape):
    flow=np.zeros((*shape,2),np.float32)
    for z in r['local_alignment']:
        x,y,X,Y=z['bbox'];flow[y:Y,x:X]=[z['dx'],z['dy']]
    return cv2.GaussianBlur(flow,(0,0),12)
def aligned(points,r,flow):
    q=np.asarray(points,np.float32).copy();h,w=r['source_shape']
    if r['mirrored_input']:q[:,0]=w-1-q[:,0]
    x,y=q[:,0].copy(),q[:,1].copy();k=r['rotation_ccw']//90
    rot=np.column_stack((x,y)) if k==0 else np.column_stack((y,w-1-x)) if k==1 else np.column_stack((w-1-x,h-1-y)) if k==2 else np.column_stack((h-1-y,x))
    g=cv2.transform(((rot+.5)*r['preview_scale']-.5)[None],np.asarray(r['matrix']))[0];q=g.copy()
    for _ in range(5):
        ix=np.clip(np.rint(q[:,0]).astype(int),0,flow.shape[1]-1);iy=np.clip(np.rint(q[:,1]).astype(int),0,flow.shape[0]-1);q=g-flow[iy,ix]
    from detector import source_points
    reg=dict(matrix=np.asarray(r['matrix']),rotation=k,mirrored=r['mirrored_input'],target_scale=r['preview_scale'])
    error=float(abs(source_points(q,reg,flow,r['source_shape'])-np.asarray(points)).max());assert error<.15,error
    return q,error
def main():
    cv2.setNumThreads(4);dest=OUT/'discovery';dest.mkdir(parents=True,exist_ok=True);answer=read(PRIOR/'answers.json');allmarks=[]
    for key in sorted(answer):
        r=read(PRIOR/'runs'/key/'result.json');ref,tar=[Image.open(PRIOR/'runs'/key/f'{n}.png').convert('RGB') for n in ('reference','aligned')];flow=flow_for(r,(ref.height,ref.width))
        for mark in answer[key]['marks']:
            p,error=aligned(mark['polygon'],r,flow);center=p.mean(axis=0);box=[int(np.floor(p[:,0].min())),int(np.floor(p[:,1].min())),int(np.ceil(p[:,0].max())-np.floor(p[:,0].min())),int(np.ceil(p[:,1].max())-np.floor(p[:,1].min()))]
            row=dict(photo=key,answer=mark['id'],polygon=p.tolist(),center=center.tolist(),answer_box=box,roundtrip_error=error,source_annotation=mark,role='construction' if key=='ng-128' else 'development_validation_not_new_batch',deferred=mark['id'] in (8,9) or (key,mark['id']) in [('ng-129',6),('ng-137',5)])
            allmarks.append(row)
            if key!='ng-128':continue
            side=80;x0=round(center[0]-side/2);y0=round(center[1]-side/2);canvas=Image.new('RGB',(640,350),'white');d=ImageDraw.Draw(canvas)
            for i,im in enumerate((ref,tar)):
                crop=im.crop((x0,y0,x0+side,y0+side));dr=ImageDraw.Draw(crop);pts=[tuple(v-[x0,y0]) for v in p];dr.line(pts+[pts[0]],fill='#00a5dd');canvas.paste(crop.resize((320,320),Image.Resampling.NEAREST),(i*320,30))
            d.text((5,5),f'128 answer {mark["id"]}  ref LEFT / target RIGHT  box={box}',fill='black');canvas.save(dest/f'answer-{mark["id"]:02}.png')
        if key=='ng-128':
            for start in (1,5,9):
                ids=[i for i in range(start,start+4) if (dest/f'answer-{i:02}.png').exists()];sheet=Image.new('RGB',(640,350*len(ids)),'white')
                for j,i in enumerate(ids):sheet.paste(Image.open(dest/f'answer-{i:02}.png'),(0,j*350))
                sheet.save(dest/f'answers-{start}.png')
    save(OUT/'aligned-answers.json',allmarks);print('MAPPED',len(allmarks),'answers; max roundtrip',max(m['roundtrip_error'] for m in allmarks))
if __name__=='__main__':main()
