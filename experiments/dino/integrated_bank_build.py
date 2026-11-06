"""Reconstruct the experimental bank from its recipe; verify exact feature equality."""
from integrated_bank_probe import OUT,OLD,NEW,read,save
import argparse,hashlib
import numpy as np

def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',default='curated_v5_review');a=p.parse_args()
    recipe=read(OUT/f'{a.arm}-recipe.json')
    files=[OLD/'original-bank.npz',OLD/'positive_clean3-bank.npz',NEW/'collection/context-bank.npz',NEW/'collection/core-bank.npz']
    original,clean,context,core=[np.load(f) for f in files]
    b=original['bank'].copy()
    for ident in recipe['original_positive_crop_ids']:
        i=int(ident[1:])-1;b[i]=clean['bank'][i]
    ids=context['ids'].tolist();n=int(context['n'])
    positives=[i for i in ids[:n] if i not in recipe['inactive_new_positive_ids']]
    normals=[i for i in ids[n:] if i not in recipe['inactive_new_normal_ids']]
    def vector(ident):
        source=core if recipe['view_overrides'].get(ident)=='core' else context
        return source['bank'][source['ids'].tolist().index(ident)]
    bank=np.concatenate((b[:47],np.stack([vector(i) for i in positives]),b[47:],np.stack([vector(i) for i in normals])))
    names=[f'S{i:02}' for i in range(1,48)]+positives+[f'O-N{i:02}' for i in range(1,66)]+normals
    actual=np.load(OUT/f'{a.arm}-bank.npz')
    assert names==actual['ids'].tolist() and np.array_equal(bank,actual['bank'])
    assert 47+len(positives)==int(actual['n'])==recipe['positive']
    assert 65+len(normals)==recipe['normal']
    save(OUT/'bank-build-verification.json',dict(status='passed',arm=a.arm,exact_feature_equality=True,positive=recipe['positive'],normal=recipe['normal'],source_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},feature_sha256=hashlib.sha256(bank.tobytes()).hexdigest()))
    print('EXACT BANK RECONSTRUCTION',recipe['positive'],recipe['normal'],flush=True)

if __name__=='__main__':main()
