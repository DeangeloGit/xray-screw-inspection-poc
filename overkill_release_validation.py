"""Check real detector results against a private validation plan."""
import json
import sys
from pathlib import Path


def run(plan_path):
    import cv2
    from detector import detect
    from model_manager import ModelManager
    from overkill_pilot import VERSION, enabled

    cv2.setNumThreads(4)
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    snapshot = ModelManager(execution_override=plan['execution']).snapshot()
    assert enabled(snapshot) and snapshot.info()['execution'] == plan['execution'], snapshot.info()
    output = Path(plan['output'])
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for row in plan['items']:
        result = detect(row['reference'], row['path'], row['key'], .13, snapshot, output / row['key'])
        assert result['experimental_policy'] == VERSION
        kept = sorted(c['id'] for c in result['candidates'])
        discarded = sorted(c['id'] for c in result['filtered_candidates'])
        assert all(c['classification']['status'] == 'active' for c in result['candidates']+result['filtered_candidates'])
        assert kept == row['kept'], (row['key'], 'keep', sorted(set(kept)^set(row['kept'])))
        assert discarded == row['discarded'], (row['key'], 'discard', sorted(set(discarded)^set(row['discarded'])))
        by_id = {c['id']: c for c in result['candidates']+result['filtered_candidates']}
        for cid, expected in row['pilot'].items():
            assert by_id[int(cid)]['classification']['overkill_pilot'] == expected, (row['key'], cid)
        results.append(dict(key=row['key'], kept=len(kept), discarded=len(discarded), pilot_checks=len(row['pilot'])))
        print('PASS', results[-1], flush=True)
    receipt = dict(success=True, experimental_policy=VERSION, model=snapshot.info(), results=results)
    (output/'verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    run(sys.argv[1])
