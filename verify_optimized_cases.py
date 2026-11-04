"""Revalidate the fixed 59 cropped pairs, with actual CPU or GPU inference."""
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from model_manager import ModelManager
from dino_paired_optimized import classify_candidate

ROOT=Path(__file__).resolve().parent


def main(execution, output):
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    plan=read(ROOT/'workspace/dino-learn-joint-20261103/results.json')
    expected=read(ROOT/'workspace/dino-four-remaining-20261103/restricted-results.json')
    s=ModelManager(allow_cpu=True,execution_override=execution).snapshot('dino-paired-optimized-47-20261104-r3')
    assert not s.error,s.info()
    rows=[]
    for z,want in zip(plan,expected):
        assert z['key']==want['key']
        arrays=[np.asarray(Image.open(Path(z['source'])/f).convert('L'),np.float32)/255 for f in ('reference.png','aligned.png')]
        # These are already PNG-quantized report frames. Pass the exact same values
        # through the production classifier, including its one-frame quantization.
        p=classify_candidate(s,arrays[1],arrays[0],z['c']);pair=p.get('paired_evidence',{})
        assert p['status']=='active',p
        sides={side:pair[side]['label']=='screw' for side in ('reference','target')}
        changes=[side for side in sides if sides[side]!=want['new'][side]['screw']]
        hashes={side:pair[side]['input_sha256'] for side in sides}
        assert hashes==want['input_hashes'],(z['number'],'input mismatch')
        assert not changes and (p['action']!='discard')==want['new']['keep'],(z['number'],changes)
        rows.append(dict(number=z['number'],group=z['group'],**sides,keep=p['action']!='discard',decision_changes=changes))
        if len(rows)%10==0:print(execution,len(rows),'/59 unchanged',flush=True)
    summary=dict(success=True,execution=execution,model=s.info(),cases=len(rows),decision_changes=0,
                 original_screws_correct=sum(r['keep'] for r in rows if r['group']=='original_screw'),
                 normal_false_alarms=sum(r['keep'] for r in rows if r['group']=='normal'),rows=rows)
    Path(output).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False),flush=True)


if __name__=='__main__':main(*sys.argv[1:])
