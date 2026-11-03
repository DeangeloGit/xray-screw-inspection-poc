"""Attach original audited pictures to the existing immutable bank, without changing it."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=ROOT/'models/dino-examples-a3b8c97aa539';src=ROOT/'workspace/windows-check/diagnostics/clip-screw-examples'
    manifest=(p/'manifest.json').read_bytes();active=(ROOT/'models/active.json').read_bytes();m=json.loads(manifest);meta={}
    (p/'examples').mkdir(exist_ok=True)
    for label in ('screw','normal'):
        for n in m['example_bank'][label]['ids']:
            f=src/(n if n.endswith('.png') else n+'.png');data=f.read_bytes();name=hashlib.sha256(n.encode()).hexdigest()+'.png';dest=p/'examples'/name
            if dest.exists():assert dest.read_bytes()==data
            else:dest.write_bytes(data)
            meta[n]=dict(file=name,sha256=hashlib.sha256(data).hexdigest(),name=n)
    payload=json.dumps(meta,ensure_ascii=False,indent=2)
    if (p/'examples.json').exists():assert json.loads((p/'examples.json').read_text(encoding='utf-8'))==meta
    else:(p/'examples.json').write_text(payload,encoding='utf-8')
    assert (p/'manifest.json').read_bytes()==manifest and (ROOT/'models/active.json').read_bytes()==active
    print('Attached',len(meta),'original pictures. Model and active pointer unchanged.')
if __name__=='__main__':main()
