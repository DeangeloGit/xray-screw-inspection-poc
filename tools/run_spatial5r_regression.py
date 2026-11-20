"""Reproduce full detection or additive-only 5r regression in a new directory.

Private JSON manifest: {"items": [{"key", "path", "sha256", "reference",
"reference_sha256", "baseline_result", "baseline_result_sha256",
"baseline_images", "label", "machine"}]}. Baselines are optional for full
detection and mandatory for additive replay. No filename affects inference.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'experiments/dino'),str(ROOT)]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--home',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--probe',type=Path,required=True)
    ap.add_argument('--mode',choices=['full','additive'],default='full')
    args=ap.parse_args()
    if read(args.probe)['status']!='passed':raise ValueError('Required DINO probe has not passed')
    items=read(args.manifest)['items']
    if len({x['key'] for x in items})!=len(items):raise ValueError('Duplicate image keys')
    for item in items:
        if Path(item['key']).name!=item['key'] or item['key'] in ('.','..'):
            raise ValueError('Invalid image key')
        for path_key,sha_key in [('path','sha256'),('reference','reference_sha256')]:
            if sha(item[path_key])!=item[sha_key]:raise ValueError('Source verification failed: '+item['key'])
        if args.mode=='additive' or item.get('baseline_result'):
            if sha(item['baseline_result'])!=item['baseline_result_sha256']:
                raise ValueError('Baseline verification failed: '+item['key'])
    args.output.mkdir(parents=True,exist_ok=False)
    from spatial5r_runtime import Engine
    import spatial5r
    import enclosure_guard5r
    import fragment_core_guard5r
    import enclosure_rescue5r
    import structure_shadow5r
    engine=Engine(args.home)
    selected=engine.snapshot()
    policy_sha=sha(spatial5r.__file__)
    guard_sha=sha(enclosure_guard5r.__file__)
    core_sha=sha(fragment_core_guard5r.__file__)
    rescue_sha=sha(enclosure_rescue5r.__file__)
    shadow_sha=sha(structure_shadow5r.__file__)
    save(args.output/'plan.json',dict(items=items,mode=args.mode,manifest_sha256=sha(args.manifest),
         probe_sha256=sha(args.probe),policy_sha256=policy_sha,enclosure_guard_sha256=guard_sha,fragment_core_sha256=core_sha,enclosure_rescue_sha256=rescue_sha,structure_shadow_sha256=shadow_sha,runtime_identity=engine.policy_hash,
         model=selected.info(),banks=engine.bundle.details(engine.banks.current)))
    rows=[]
    for item in items:
        directory=args.output/'runs'/item['key']
        directory.mkdir(parents=True)
        started=time.monotonic()
        baseline=read(item['baseline_result']) if item.get('baseline_result') else None
        if args.mode=='full':
            shutil.copyfile(item['path'],directory/('input'+Path(item['path']).suffix.lower()))
            result=engine.detect(item['reference'],item['path'],item['key'],
                                 item.get('threshold',.13),selected,directory)
        else:
            source=Path(item['baseline_images'])
            for name in ['reference.png','aligned.png','source.png','overlay.png','all_overlay.png']:
                shutil.copyfile(source/name,directory/name)
            engine.cache.clear()
            result=spatial5r.apply(selected,engine.bundle,baseline,directory,
                                  item['reference'],item['path'],engine.review,engine.normal)
            result=fragment_core_guard5r.apply(selected,result,directory)
            result=enclosure_guard5r.apply(selected,result,directory)
            result=enclosure_rescue5r.apply(selected,result,directory)
            result=structure_shadow5r.apply(result,directory)
            save(directory/'result.json',result)
        old={c['id'] for c in baseline['candidates']} if baseline else set()
        kept={c['id'] for c in result['candidates']}
        # Frame IDs only compare unchanged base geometry. Positional human
        # answer matching is a separate gate, never inferred from NG labels.
        lost=sorted(old-kept) if args.mode=='additive' else []
        unchanged=all(c in result['filtered_candidates'] for c in baseline['filtered_candidates']) if args.mode=='additive' else None
        assert len(kept)+len(result['filtered_candidates'])==result['pre_ai_count']
        assert sha(spatial5r.__file__)==policy_sha,'Policy changed during run'
        assert sha(enclosure_guard5r.__file__)==guard_sha,'Enclosure guard changed during run'
        assert sha(fragment_core_guard5r.__file__)==core_sha,'Fragment core guard changed during run'
        assert sha(enclosure_rescue5r.__file__)==rescue_sha,'Rescue policy changed during run'
        assert sha(structure_shadow5r.__file__)==shadow_sha,'Shadow policy changed during run'
        assert sha(item['path'])==item['sha256'] and sha(item['reference'])==item['reference_sha256']
        row=dict(key=item['key'],label=item['label'],machine=item['machine'],kept=len(kept),
                 removed=len(result['filtered_candidates']),baseline_kept=len(old) if baseline else None,
                 lost_original_ids=lost,prior_exclusions_identical=unchanged,
                 added=result['spatial5r']['added'],seconds=round(time.monotonic()-started,2),
                 result_sha256=sha(directory/'result.json'))
        rows.append(row)
        save(args.output/'rows.json',rows)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    save(args.output/'summary.json',dict(status='completed',mode=args.mode,photos=len(rows),
         lost_original_frames=sum(len(r['lost_original_ids']) for r in rows),
         scope='Full detector rerun' if args.mode=='full' else 'Fresh additive stages on frozen original detections; not full detector rerun',
         accuracy_accepted=False,remaining='Review all new alarms, actual object locations and complete report before acceptance'))


if __name__=='__main__':main()
