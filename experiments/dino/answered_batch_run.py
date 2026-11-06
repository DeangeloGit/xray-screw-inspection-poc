"""Frozen answered-batch evaluation; writes only to an isolated experiment folder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
MODEL = 'dino-paired-optimized-47-20261104-r3'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execution', default='gpu', choices=['cpu', 'gpu'])
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['XRAY_WORKSPACE'] = str(out/'runtime')
    os.environ['XRAY_CONFIG'] = str(out/'isolated-settings.json')
    sys.path.insert(0, str(ROOT))
    import cv2
    import overkill_pilot
    from detector import detect
    from model_manager import ModelManager
    cv2.setNumThreads(4)
    model = ModelManager(ROOT/'models', allow_cpu=True, execution_override=args.execution).snapshot(MODEL)
    assert not model.error and model.info()['execution'] == args.execution, model.info()
    assert [len(model.manifest['example_bank'][k]['ids']) for k in ('screw', 'normal')] == [47, 65]
    golden = source/'Golden.tiff'
    photos = sorted((source/'NG').glob('*.tiff'))
    assert photos and golden.exists()
    answers = {p.stem: p for p in (source/'ANSWER_PNG').rglob('*.png')}
    assert {p.stem for p in photos} == set(answers)
    protected = list(source.rglob('*')) + list((ROOT/'models'/MODEL).glob('*'))
    protected += list(ROOT.glob('*.py')) + [ROOT/'models/active.json', ROOT/'config/station.json']
    hashes = {str(p): sha(p) for p in protected if p.is_file()}
    plan = dict(source=str(source), hashes=hashes, model=model.info(), threshold=.13,
                commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
                policy=overkill_pilot.VERSION,
                items=[dict(key=p.stem.rsplit('_',1)[-1],path=str(p),answer=str(answers[p.stem]),sha256=sha(p)) for p in photos]
                + [dict(key='golden',path=str(golden),answer=None,sha256=sha(golden))],
                methods=['r3','recovery','pilot'],
                recovery_description='Same fixed pilot, with structure_rules returning [] in this process only; isolates the overkill filter effect.')
    if (out/'plan.json').exists():
        assert json.loads((out/'plan.json').read_text(encoding='utf-8')) == plan, 'Frozen inputs changed'
    else:
        save(out/'plan.json', plan)
    original_rules = overkill_pilot.structure_rules
    for row in plan['items']:
        for method in plan['methods']:
            folder = out/'runs'/method/row['key']
            if (folder/'complete.json').exists():
                print('RESUME', method, row['key'], flush=True)
                continue
            os.environ['XRAY_OVERKILL_PILOT'] = '0' if method == 'r3' else '1'
            overkill_pilot.structure_rules = (lambda *a: []) if method == 'recovery' else original_rules
            started = time.perf_counter()
            r = detect(golden, row['path'], row['key'], .13, model_snapshot=model, output_directory=folder)
            assert all(c['classification']['status']=='active' for c in r['candidates']+r['filtered_candidates'])
            assert (r.get('experimental_policy') == overkill_pilot.VERSION) == (method != 'r3')
            receipt = dict(key=row['key'],method=method,kept=r['proposal_count'],excluded=r['filtered_count'],seconds=round(time.perf_counter()-started,2),result_sha256=sha(folder/'result.json'))
            save(folder/'complete.json',receipt)
            print(json.dumps(receipt),flush=True)
    assert all(sha(p)==h for p,h in hashes.items()), 'Protected files changed'
    save(out/'run-complete.json',dict(complete=True,protected_files_unchanged=True,photos=len(plan['items']),methods=plan['methods']))


if __name__ == '__main__':
    main()
