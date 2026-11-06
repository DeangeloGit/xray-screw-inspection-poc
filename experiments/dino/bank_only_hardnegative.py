"""Add one authentic normal reference crop; no synthetic pixels or query rules."""
from bank_only_probe import ROOT,OUT,PRIOR,AUDIT,read,save,score
import numpy as np,hashlib
from PIL import Image
from model_manager import ModelManager
from dino_paired_optimized import example_features,adjusted_image
def main():
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    # This source is the supplied known-good Golden reference, never the
    # unannotated NG candidate. Its matched structure exposes a coverage gap.
    source=PRIOR/'runs/ng-132/reference.png';a=np.asarray(Image.open(source).convert('L'),np.float32)/255;x,y,w,h=[1351,484,6,26];crop=a[y-12:y+h+12,x-12:x+w+12]
    feature=example_features(snap.manifest,snap.session,crop)[None];bank=np.concatenate([np.load(OUT/'clean3_normal_add1-bank.npz')['bank'],feature]);np.savez_compressed(OUT/'clean3_normal_add2-bank.npz',bank=bank,n=47);adjusted_image(snap.manifest,crop).save(OUT/'examples/N67-good-reference.png')
    save(OUT/'normal67-provenance.json',dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_label='supplied known-good Golden reference, source inventory hash verified',box=[x,y,w,h],padding=12,matched_failure='ng-132 #137',training_pixels='reference only, not NG target',counted_examples=1,augmentations=8,query_or_score_rule_changed=False))
    rows=read(OUT/'fixed-query-scores.json');result=[]
    for photo in map(str,range(128,138)):
        cache=np.load(AUDIT/'all-features'/f'{photo}.npz')
        for r in rows:
            if r['photo']!=photo:continue
            pair={s:score(cache[h],bank) for s,h in r['input_sha256'].items()};keep=pair['target']['margin']>=0 and pair['reference']['margin']<0;result.append(dict(key=r['key'],photo=photo,answers=r['answers'],keep=keep,pair=pair,original=r['arms']['original']['keep']))
            if r['key'] in ('ng-128-40','ng-132-137','ng-135-88','ng-128-10'):print('NEW NORMAL',r['key'],keep,'target',pair['target']['margin'],'reference',pair['reference']['margin'],flush=True)
    expected={(r['photo'],a) for r in result if r['original'] for a in r['answers']};hits={(r['photo'],a) for r in result if r['keep'] for a in r['answers']};save(OUT/'normal67-fixed-query.json',dict(rows=result,raw_hits=len(hits),lost_raw_hits=sorted(expected-hits),raw_unmatched=sum(r['keep'] and not r['answers'] for r in result)));print('RAW lost',sorted(expected-hits),flush=True)
if __name__=='__main__':main()
