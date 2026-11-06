"""Answer-aware diagnosis only; its labels/coordinates never enter a detector."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')


def aligned_points(points,result,flow):
    h,w=result['source_shape'];p=np.array(points,np.float32);x,y=p.T
    if result['mirrored_input']:x=w-1-x
    k=result['rotation_ccw']//90
    if k==1:x,y=y,w-1-x
    elif k==2:x,y=w-1-x,h-1-y
    elif k==3:x,y=h-1-y,x
    p=(np.column_stack((x,y))+.5)*result['preview_scale']-.5
    global_p=cv2.transform(p[None],np.asarray(result['matrix']))[0];p=global_p.copy()
    for _ in range(8):
        ix=np.clip(np.rint(p[:,0]).astype(int),0,flow.shape[1]-1);iy=np.clip(np.rint(p[:,1]).astype(int),0,flow.shape[0]-1)
        p=global_p-flow[iy,ix]
    return p


def components(ref,target,mask,predicted,kernel):
    import detector
    residual=cv2.erode(predicted,np.ones((kernel,kernel),np.uint8))-target
    binary=((residual>.13)&mask).astype('uint8')
    binary=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    _,labs,stats,_=cv2.connectedComponentsWithStats(binary)
    for i,(x,y,w,h,area) in enumerate(stats[1:],1):
        if area>1800 or max(w,h)>110:
            region=(labs[y:y+h,x:x+w]==i).astype('uint8')
            separated=cv2.morphologyEx(region,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
            binary[y:y+h,x:x+w][region>0]=separated[region>0]
    _,labels,stats,_=cv2.connectedComponentsWithStats(binary)
    near=cv2.erode(predicted,np.ones((15,15),np.uint8));rows=[]
    for i,(x,y,w,h,area) in enumerate(stats[1:],1):
        x,y,w,h,area=map(int,(x,y,w,h,area));c=dict(x=x,y=y,w=w,h=h,area=area)
        gate='size' if not (12<=area<=1800 and 4<=max(w,h)<=110) else ''
        if not gate:
            part=labels[y:y+h,x:x+w]==i
            sim=detector.matching_structure(ref,target,x,y,w,h)
            support=float(np.mean((near[y:y+h,x:x+w]<=target[y:y+h,x:x+w]+.06)[part]))
            c.update(shape_similarity=sim,normal_support=support,fill=area/(w*h))
            if area<40 and (sim>.55 or support>.5):gate='small_near_existing_structure'
            elif sim>=.85:
                import overkill_pilot
                ev=overkill_pilot.similarity_recovery(ref,target,c,.13,detector.structure_change_evidence) if kernel==7 else None
                gate='similarity_recovery' if ev else 'similarity_rejected'
                c['recovery_evidence']=ev
            else:gate='passed_initial_filters'
        c['gate']=gate;rows.append(c)
    return rows,residual


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    base=a.baseline.resolve();out=a.output.resolve()
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');sys.path.insert(0,str(ROOT))
    import detector
    from answered_batch_report import matches
    answers=read(base/'answer-matches.json');cases=read(base/'cases.json');misses=[]
    for m in answers:
        if m['methods']['pilot']:continue
        zs=[z for z in cases if z['photo']==m['photo'] and m['id'] in z['answers']]
        reasons=[]
        for z in zs:
            pair=z['paired_evidence'];reasons.append('structure_filter' if z['rules'] else 'target_not_screw' if pair['target']['label']!='screw' else 'reference_also_screw')
        misses.append(dict(photo=m['photo'],id=m['id'],reason='no_candidate' if not zs else '+'.join(sorted(set(reasons))),candidates=[z['key'] for z in zs],edge=[z['key'] for z in cases if z['photo']==m['photo'] and m['id'] in z['edge_answers']]))
    save(out/'diagnosis-initial.json',dict(misses=misses,added_false_alarms=[z for z in cases if z['keep']['pilot'] and not z['keep']['r3'] and not z['answers']]))
    rows=[];(out/'diagnostic-pairs').mkdir(exist_ok=True)
    for item in read(base/'plan.json')['items']:
        key=item['key'];f=out/'arrays'/f'{key}.npz'
        if not f.exists():continue
        arrays=np.load(f);ref,target,mask=[arrays[k] for k in ('ref','target','mask')]
        result=read(base/'runs'/'pilot'/key/'result.json')
        flow=np.zeros((*ref.shape,2),np.float32)
        for region in result['local_alignment']:
            x,y,X,Y=region['bbox'];flow[y:Y,x:X]=[region['dx'],region['dy']]
        flow=cv2.GaussianBlur(flow,(0,0),12)
        predicted=detector.compensate_brightness(ref,target)
        data={k:components(ref,target,mask,predicted,k) for k in (7,3)}
        for m in [m for m in answers if m['photo']==key and not m['methods']['pilot']]:
            poly=aligned_points(m['polygon'],result,flow);center=aligned_points([m['center']],result,flow)[0]
            aligned=dict(id=m['id'],polygon=poly.tolist(),center=center.tolist())
            x,y=np.floor(poly.min(axis=0)).astype(int);X,Y=np.ceil(poly.max(axis=0)).astype(int)
            x,y=max(0,x),max(0,y);X,Y=min(ref.shape[1],X),min(ref.shape[0],Y)
            rs=slice(y,Y);cs=slice(x,X);parts={}
            for kernel,(comp,residual) in data.items():
                hits=[]
                for c in comp:
                    xx,yy,w,h=[c[k] for k in ('x','y','w','h')]
                    yes,edge=matches([[xx,yy],[xx+w,yy],[xx+w,yy+h],[xx,yy+h]],[aligned])
                    if yes:hits.append(c)
                parts[str(kernel)]=dict(above_threshold_pixels=int((residual[rs,cs]>.13).sum()),maximum=float(residual[rs,cs].max()),components=hits)
            row=dict(photo=key,id=m['id'],aligned_polygon=poly.tolist(),aligned_center=center.tolist(),stages=parts,target_min=float(target[rs,cs].min()),target_max=float(target[rs,cs].max()),mask_coverage=float(mask[rs,cs].mean()),matched_candidates=[c['key'] for c in cases if c['photo']==key and m['id'] in c['answers']])
            rows.append(row)
            side=max(110,X-x+35,Y-y+35);cx,cy=center;x0=max(0,min(ref.shape[1]-side,int(cx-side/2)));y0=max(0,min(ref.shape[0]-side,int(cy-side/2)))
            canvas=Image.new('RGB',(600,300),'white')
            for j,im in enumerate((ref,target)):
                crop=Image.fromarray(np.uint8(np.clip(im[y0:y0+side,x0:x0+side],0,1)*255)).convert('RGB');d=ImageDraw.Draw(crop);p=[(float(x-x0),float(y-y0)) for x,y in poly];d.line(p+[p[0]],fill='red',width=1);canvas.paste(crop.resize((300,300)),(j*300,0))
            canvas.save(out/'diagnostic-pairs'/f'{key}-{m["id"]}.jpg')
        print('DIAGNOSE',key,flush=True)
    save(out/'diagnosis-detailed.json',rows)
    for row in rows:
        print(row['photo'],row['id'],row['matched_candidates'],[(k,v['above_threshold_pixels'],[(c['area'],c['gate'],round(c.get('shape_similarity',0),3)) for c in v['components']]) for k,v in row['stages'].items()],flush=True)


if __name__=='__main__':main()
