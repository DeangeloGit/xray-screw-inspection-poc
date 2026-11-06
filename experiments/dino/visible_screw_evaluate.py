"""Frozen exposed-part model evaluated across every image and all new proposals."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np,cv2
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-visible-screw-20261106'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from visible_screw_geometry import proposals,part_image
from model_manager import ModelManager
from dino_paired_optimized import adjusted_image,features
from blackblock_ablation import score
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def main():
    cv2.setNumThreads(4);plan=read(OUT/'experiment-plan.json');snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');bank=np.load(OUT/'visible-part-bank.npz')['bank'];rows=[];montage=Image.new('RGB',(1200,480),'white');d=ImageDraw.Draw(montage)
    for photo in [str(i) for i in range(128,138)]+['golden']:
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{photo}.npz');ref,tar=[(np.clip(a[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')];parts=proposals(ref,tar)
        for i,p in enumerate(parts):
            z={k:v for k,v in p.items() if k!='mask'};z.update(photo=photo,id=i,pair={})
            for side,a0 in [('reference',ref),('target',tar)]:
                view=adjusted_image(snap.manifest,part_image(a0,z['box']));v=features(snap.manifest,snap.session,view);z['pair'][side]=dict(score(v,bank,50),input_sha256=hashlib.sha256(view.tobytes()).hexdigest())
            z['keep']=z['pair']['target']['margin']>=plan['target_min'] and z['pair']['reference']['margin']<0;rows.append(z)
        kept=[z for z in rows if z['photo']==photo and z['keep']];print('PHOTO',photo,'parts',len(parts),'KEEP',[(z['box'],round(z['pair']['target']['margin'],3),round(z['pair']['reference']['margin'],3)) for z in kept],flush=True)
        if photo!='golden':
            j=int(photo)-128;crop=Image.fromarray(np.uint8(tar[435:466,720:744]*255)).convert('RGB').resize((180,190),Image.Resampling.NEAREST);montage.paste(crop,((j%5)*240,(j//5)*240+30));d.text(((j%5)*240+4,(j//5)*240+4),photo+' B region (review)',fill='black')
    montage.save(OUT/'all-B-regions.jpg');(OUT/'all-part-scores.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in read(OUT/'frozen-before-heldout.json').items())
    print('TOTAL PARTS',len(rows),'KEPT',sum(z['keep'] for z in rows),flush=True)
if __name__=='__main__':main()
