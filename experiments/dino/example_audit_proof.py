"""Fresh candidate-window perturbations and synthetic shape controls."""
from example_audit_probe import ROOT,OUT,BASE,read,save
import example_audit_policy as policy
import numpy as np,cv2,hashlib
from PIL import Image
from model_manager import ModelManager
from correspondence_stability_probe import variations,fingerprint
from dino_paired_optimized import adjusted_image
def main():
    cv2.setNumThreads(4);snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    policy.configure(np.load(BASE.parent.parent/'visible-part-bank.npz')['bank'],read(BASE.parent/'experiment-plan.json'),np.load(OUT/'letterbox-112-bank.npz')['bank'])
    tests=[];controls=[];inputs=[];imagepath=OUT/'proof-images';imagepath.mkdir(exist_ok=True)
    trial=next(z for z in read(OUT/'gated-ablation-summary.json') if z['bank']=='allbank' and z['consensus']=='mean_four');keys=trial['added'];assert len(keys)==10
    for photo in map(str,range(128,138)):
        dest=OUT/'proof'/f'{photo}.json'
        if dest.exists():
            previous=read(dest);tests+=previous['tests'];controls+=previous['controls'];inputs+=previous['inputs'];continue
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{photo}.npz');ref,tar=[(np.clip(a[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')]
        r=read(BASE/'runs/pilot'/photo/'result.json');cs=r['candidates']+r['filtered_candidates'];seed=next(c for c in cs if f'{photo}-{c["id"]}' in keys);objects=policy.Objects(ref,tar,cs)
        original=policy.classify(snap,ref,tar,seed,objects);assert original['filter_recommendation']=='keep';expected=fingerprint(original);extent=original['canonical_object']['box'];rr=[];cc=[];ii=[]
        for query,settings in variations(seed):
            pred=policy.classify(snap,ref,tar,query,objects);same=fingerprint(pred)==expected
            rr.append(dict(photo=photo,seed_id=seed['id'],query=query,**settings,same_prediction=same,fresh_inference=True,box=pred['canonical_object']['box'],verdict=pred['filter_recommendation']));assert same,(photo,query)
        for v in original['example_crop_review']['views']:
            for side,ar in [('reference',ref),('target',tar)]:
                im=adjusted_image(snap.manifest,policy.square_crop(ar,extent,v['pad']));digest=hashlib.sha256(im.tobytes()).hexdigest();assert digest==v[side]['input_sha256'];name=f'board-{photo}-pad{v["pad"]}-{side}.png';im.save(imagepath/name);ii.append(dict(photo=photo,pad=v['pad'],side=side,file=name,input_sha256=digest))
        x,y,w,h=extent
        for kind,level in [('restore_reference',None),('solid_dark_rectangle',0.),('solid_dark_rectangle',.08),('solid_dark_rectangle',.14)]:
            altered=tar.copy();altered[y:y+h,x:x+w]=ref[y:y+h,x:x+w] if level is None else level
            result=policy.review(snap,ref,altered,extent);cc.append(dict(photo=photo,kind=kind,level=level,box=extent,keep=result['keep'],pair=result['pair'],views=result['views'],synthetic=True))
            # Record failures honestly; final acceptance explicitly checks these.
            if level in (None,0.):
                im=Image.new('RGB',(600,300),'white')
                for i,ar in enumerate((tar,altered)):
                    c=Image.fromarray(np.uint8(ar[y-20:y+h+20,x-20:x+w+20]*255)).convert('RGB');c=c.resize((300,300),Image.Resampling.NEAREST);im.paste(c,(300*i,0))
                im.save(imagepath/f'board-{photo}-{kind}.png')
        save(dest,dict(tests=rr,controls=cc,inputs=ii));tests+=rr;controls+=cc;inputs+=ii
        print('PROOF',photo,'stable',sum(t['same_prediction'] for t in rr),'/',len(rr),'synthetic keeps',[(c['kind'],c['level']) for c in cc if c['keep']],flush=True)
    save(OUT/'board-proof.json',dict(total_tests=len(tests),stable_tests=sum(t['same_prediction'] for t in tests),tests=tests,controls=controls,synthetic_control_failures=sum(c['keep'] for c in controls),actual_inputs=inputs,scope='450 fresh query-window tests, not image resampling or new scans. Forty controls re-run new four-view review on fixed image-derived boxes; synthetic, not physical validation.'))
if __name__=='__main__':main()
