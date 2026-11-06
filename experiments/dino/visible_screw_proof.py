"""Fresh B-part jitter and controlled image tests; synthetic controls are diagnostic."""
import os,sys,json,copy,hashlib
from pathlib import Path
import numpy as np,cv2
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));EXP=ROOT/'workspace/dino-4r-visible-screw-20261106/v3'
os.environ['XRAY_WORKSPACE']=str(EXP/'proof-runtime');os.environ['XRAY_CONFIG']=str(EXP/'isolated-settings.json')
import visible_screw_policy_v3 as policy
from model_manager import ModelManager
from correspondence_stability_probe import variations,fingerprint
from dino_paired_optimized import adjusted_image
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def proposal(z):return dict(zip(('x','y','w','h'),z['box']),recovery='r4_visible_part',visible_part=z)
def overlap(a,b):
    x,y,w,h=a;X,Y,W,H=b;return max(0,min(x+w,X+W)-max(x,X))*max(0,min(y+h,Y+H)-max(y,Y))
def main():
    cv2.setNumThreads(4);snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');policy.configure(np.load(EXP.parent/'visible-part-bank.npz')['bank'],read(EXP/'experiment-plan.json'));rows=read(EXP/'all-part-scores.json');tests=[];controls=[];proof=[]
    dest=EXP/'final/report/images';dest.mkdir(parents=True,exist_ok=True)
    for photo in map(str,range(128,138)):
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{photo}.npz');ref,tar=[(np.clip(a[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')];parts=[proposal(z) for z in rows if z['photo']==photo];objects=policy.Objects(ref,tar,parts);z=next(z for z in rows if z['photo']==photo and z['keep']);seed=proposal(z);expected=policy.classify(snap,ref,tar,seed,objects);fp=fingerprint(expected);assert fp['verdict']=='keep';out=[]
        assert overlap(z['box'],z['occluder_box'])==0
        for q,settings in variations(seed):
            q.update(recovery='r4_visible_part',visible_part=z);pred=policy.classify(snap,ref,tar,q,objects);same=fingerprint(pred)==fp;assert same,(photo,settings);out.append(dict(**settings,query={k:q[k] for k in ('x','y','w','h')},same_final_prediction=True,object_id=pred['canonical_object']['object_id']))
        tests.append(dict(photo=photo,box=z['box'],tests=out,expected=fp,total_tests=len(out),stable_tests=sum(t['same_final_prediction'] for t in out)))
        for side,array in [('reference',ref),('target',tar)]:
            im=adjusted_image(snap.manifest,policy.geometry.part_image(array,z['box']));digest=hashlib.sha256(im.tobytes()).hexdigest();assert digest==expected['paired_evidence'][side]['input_sha256'];file=f'B-input-{photo}-{side}.png';im.save(dest/file);proof.append(dict(photo=photo,side=side,file=file,input_sha256=digest,occluder_overlap_pixels=0))
        x,y,w,h=z['occluder_box']
        for level in (0.,.08,.14):
            changed=tar.copy();changed[y+3:y+h-3,x+3:x+w-3]=level;changed=(changed*255).astype('uint8').astype('float32')/255
            regenerated=[{k:v for k,v in p.items() if k!='mask'} for p in policy.geometry.proposals(ref,changed)];samepart=next((p for p in regenerated if p['box']==z['box']),None);assert samepart is not None
            pair=policy.classify_part(snap,ref,changed,z['box']);assert all(pair[s]['input_sha256']==expected['paired_evidence'][s]['input_sha256'] for s in ('reference','target'))
            controls.append(dict(photo=photo,kind='opaque_interior_only_changed',level=level,part_rediscovered=True,model_inputs_identical=True,keep=True,synthetic=True))
        # Remove only the assistant-reviewed visible B region, retaining the opaque
        # block and the separate D screw. This is a controlled synthetic diagnostic.
        B=[727,440,10,21];changed=tar.copy();bx,by,bw,bh=B;changed[by:by+bh,bx:bx+bw]=ref[by:by+bh,bx:bx+bw];assert overlap(B,z['occluder_box'])==0
        nearby=[]
        for p in policy.geometry.proposals(ref,changed):
            if not overlap(p['box'],B):continue
            pair=policy.classify_part(snap,ref,changed,p['box']);keep=pair['target']['screw_margin']>=.05 and pair['reference']['screw_margin']<0;nearby.append(dict(box=p['box'],pair=pair,keep=keep))
        assert not any(p['keep'] for p in nearby),photo
        controls.append(dict(photo=photo,kind='B_removed_occluder_retained',review_box=B,nearby_proposals=nearby,keep=False,synthetic=True))
        # Evidence pair: unmodified then B removed, with the opaque block retained.
        crop=(695,430,752,477);im=Image.new('RGB',(570,235),'white')
        for i,array in enumerate((tar,changed)):
            view=Image.fromarray(np.uint8(array[crop[1]:crop[3],crop[0]:crop[2]]*255)).convert('RGB').resize((285,235),Image.Resampling.NEAREST);im.paste(view,(i*285,0))
        im.save(dest/f'B-removal-{photo}.png');print('PROOF',photo,'45 fresh shifts/scales; 3 black-only edits unchanged; B removed -> no B alarm',flush=True)
    save(EXP/'B-perturbation-results.json',dict(total_tests=450,stable_tests=sum(z['stable_tests'] for z in tests),fresh_inference=True,pairs=tests,scope='Candidate-window perturbations with image-derived occluder-side association; not image rotation/noise/new scans'))
    save(EXP/'B-counterfactual-results.json',dict(tests=controls,synthetic_tests=40,scope='Diagnostic controlled edits only, not real-image acceptance'))
    save(EXP/'actual-B-input-proof.json',dict(rows=proof,all_input_hashes_match=True,occluder_pixels_in_inputs=0))
if __name__=='__main__':main()
