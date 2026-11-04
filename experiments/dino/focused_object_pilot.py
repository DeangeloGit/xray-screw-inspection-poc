"""Second isolated pilot, on exactly the prior 17 cases; never changes production."""
import sys,json
from pathlib import Path
import numpy as np,cv2
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.local_added_object_pilot import OUT as PRIOR,read,save,digest,compare,font
from dino_adapter import embedding,input_image,classify_vector,paired_decision
OUT=ROOT/'workspace/focused-object-pilot-20261103'
RULES=dict(delta_threshold=.08,context_padding=32,object_padding=8,dilate=2,background_original_weight=.25,uncertainty_margin=.02,
          note='Exploratory rules selected with knowledge of the two failures; same fixed 17 cases, not independent accuracy validation. No examples added.')
def guarded(t,r):
    band=RULES['uncertainty_margin']
    if t < -band:return 'exclude'
    if abs(t)<=band:return 'review'
    if r>=band:return 'exclude'
    if abs(r)<band:return 'review'
    return 'keep'

def main():
    import onnxruntime as ort
    OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
    plan=read(PRIOR/'plan.json');old=read(PRIOR/'results-v3.json');rulefile=OUT/'rules.json'
    if rulefile.exists():assert read(rulefile)==RULES
    else:save(rulefile,RULES)
    save(OUT/'plan.json',dict(previous_plan=str(PRIOR/'plan.json'),previous_plan_sha256=digest(PRIOR/'plan.json'),keys=[z['key'] for z in plan['cases']],rules=RULES))
    m=read(ROOT/'models/dino-paired-47-20261103/manifest.json');o=ort.SessionOptions();o.intra_op_num_threads=4
    session=ort.InferenceSession(str(ROOT/'models/dino-paired-47-20261103/model.onnx'),sess_options=o,providers=['CPUExecutionProvider'])
    results=[]
    for n,(z,baseline) in enumerate(zip(plan['cases'],old),1):
        ref,tar=[np.asarray(Image.open(Path(z['source'])/f).convert('L'),dtype='float32')/255 for f in ['reference.png','aligned.png']]
        c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'));e=RULES['context_padding']
        metrics,*_=compare(ref,tar,c);dx,dy=metrics['dx'],metrics['dy']
        x0,y0=max(e,x-e),max(e,y-e);x1,y1=min(ref.shape[1]-e,x+w+e),min(ref.shape[0]-e,y+h+e)
        a=tar[y0:y1,x0:x1];b=ref[y0+dy:y1+dy,x0+dx:x1+dx];fitted=np.clip(metrics['gain']*b+metrics['offset'],0,1)
        delta=cv2.GaussianBlur(fitted-a,(3,3),.6)
        _,labels,stats,_=cv2.connectedComponentsWithStats((delta>RULES['delta_threshold']).astype('uint8'))
        ids,counts=np.unique(labels[y-y0:y+h-y0,x-x0:x+w-x0],return_counts=True)
        ids_counts=[(int(count),int(i)) for i,count in zip(ids,counts) if i]
        record=dict(number=n,key=z['key'],baseline_target=baseline['target']['screw_margin'],baseline_reference=baseline['reference']['screw_margin'],
            baseline_guard=guarded(baseline['target']['screw_margin'],baseline['reference']['screw_margin']),variants={})
        if not ids_counts:
            record['extraction']='no_component';results.append(record);continue
        selected=max(ids_counts)[1];mask=(labels==selected).astype('uint8');d=RULES['dilate'];mask=cv2.dilate(mask,np.ones((2*d+1,2*d+1),'uint8'))
        xx,yy,ww,hh,area=stats[selected].tolist();pad=RULES['object_padding'];side=max(ww,hh)+2*pad;cx,cy=xx+ww/2,yy+hh/2
        box=(int(cx-side/2),int(cy-side/2),int(cx-side/2)+side,int(cy-side/2)+side)
        record.update(extraction='ok',object_box=[x0+xx,y0+yy,ww,hh],crop_box=[x0+box[0],y0+box[1],side,side],mask_area=int(area),context_metrics=metrics)
        # Identical rectangle for both sides; no model or example bank updates.
        for kind in ['focused','soft_background']:
            outputs={}
            for label,array in [('target',a),('reference',b)]:
                gray=float(np.median(array[mask==0])) if (mask==0).any() else .5
                view=array if kind=='focused' else array*mask+(RULES['background_original_weight']*array+(1-RULES['background_original_weight'])*gray)*(1-mask)
                im=Image.fromarray(np.uint8(np.clip(view,0,1)*255))
                # Pad outside the local patch with its median rather than black.
                canvas=Image.new('L',(side,side),round(gray*255));left,top=max(0,box[0]),max(0,box[1]);right,bottom=min(im.width,box[2]),min(im.height,box[3])
                canvas.paste(im.crop((left,top,right,bottom)),(left-box[0],top-box[1]));crop=np.asarray(canvas,dtype='float32')/255
                input_image(m,crop).save(OUT/'images'/f'{n}-{kind}-{label}.png')
                outputs[label]=classify_vector(m,embedding(m,session,crop))
            pair=paired_decision(outputs['target'],outputs['reference'])
            record['variants'][kind]=dict(**outputs,paired_keep=pair['filter_recommendation']=='keep',guard=guarded(outputs['target']['screw_margin'],outputs['reference']['screw_margin']))
        overlay=np.stack([a,a,a],axis=-1);overlay[mask>0]=.6*overlay[mask>0]+.4*np.array([0,1,0]);Image.fromarray(np.uint8(np.clip(overlay,0,1)*255)).save(OUT/'images'/f'{n}-mask.png')
        results.append(record)
        print(n,z['category'],'guard',record['baseline_guard'],[(k,round(v['target']['screw_margin'],4),round(v['reference']['screw_margin'],4),v['paired_keep'],v['guard']) for k,v in record['variants'].items()],flush=True)
    save(OUT/'results.json',results)
    assert all(digest(Path(p))==v for p,v in plan['hashes'].items())
    save(OUT/'preservation.json',dict(unchanged_files=len(plan['hashes']),unchanged=True,formal_model_changed=False))
if __name__=='__main__':main()
