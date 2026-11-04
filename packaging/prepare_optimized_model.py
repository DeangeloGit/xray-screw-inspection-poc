"""Publish an immutable r3 model from the previously verified full example bank."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
NAME='dino-paired-optimized-47-20261104-r3'


def main():
    source=ROOT/'models/dino-paired-47-20261103'
    target=ROOT/'models'/NAME
    if target.exists():raise FileExistsError(target)
    shutil.copytree(source,target)
    bank=ROOT/'workspace/dino-contrast-pair-20261103/bank-features.npz'
    m=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    assert len(m['example_bank']['screw']['ids'])==47 and len(m['example_bank']['normal']['ids'])==65
    m.update(model_id='DINO 合併優化雙圖 r3：47 張螺絲＋65 張正常',
             feature_strategy='contrast-global-local-half-v1',feature_file='paired-features.npz',
             feature_sha256=hashlib.sha256(bank.read_bytes()).hexdigest(),
             paired_recheck='single-reliable-contained-component-plus2-v1',
             provenance=dict(parent=source.name,method='Promoted validated full-bank contrast/global-local/restricted-pair method',
                             timing_report='dino-gpu-paired-retry-20261104-120844',independent_accuracy_validation=False))
    shutil.copyfile(bank,target/m['feature_file'])
    (target/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    print(target)


if __name__=='__main__':main()
