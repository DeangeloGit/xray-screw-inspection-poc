"""Compare new batch bytes and oriented pixels against a prior source inventory."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('prior_inventory',type=Path);args=p.parse_args()
    read=lambda f:json.loads(f.read_text(encoding='utf-8'))
    plan=read(args.output/'plan.json');prior=read(args.prior_inventory)['files'];rows=[]
    for item in plan['items']:
        if not item['answer']:continue
        source=Path(item['path']);matches=[r for r in prior if r['sha256']==item['sha256']]
        evidence=None
        if matches:
            evidence=dict(kind='same_file_sha256',prior_path=matches[0]['path'],prior_sha256=matches[0]['sha256'])
        else:
            new=np.asarray(Image.open(source))
            for old in prior:
                f=Path(old['path'])
                if f.name!=source.name or f.parent.name not in ('NG','NG1'):continue
                assert hashlib.sha256(f.read_bytes()).hexdigest()==old['sha256']
                a=np.asarray(Image.open(f))
                for flip in (False,True):
                    for turn in range(4):
                        b=np.rot90(np.fliplr(a) if flip else a,turn)
                        if np.array_equal(new,b):
                            evidence=dict(kind='exact_oriented_pixels',prior_path=str(f),prior_sha256=old['sha256'],mirrored=flip,quarter_turns_ccw=turn,pixel_sha256=hashlib.sha256(new.tobytes()).hexdigest())
                if evidence:break
        rows.append(dict(name=source.name,sha256=item['sha256'],previously_used=evidence is not None,evidence=evidence))
    (args.output/'provenance.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(scans=len(rows),previously_used=sum(r['previously_used'] for r in rows),unmatched=sum(not r['previously_used'] for r in rows)),indent=2))


if __name__=='__main__':main()
