"""Regression checks for object versus existing-structure evidence."""
import cv2
import numpy as np
from detector import structure_change_evidence, proposals, machine_mask


def explained(e):
    return bool(e and e['context_supported'] and e['sim'] >= .65 and e['ratio'] <= .2 and e['remaining'] < 12)


def run():
    ref = np.full((160, 160), .85, np.float32)
    cv2.rectangle(ref, (55, 50), (80, 100), .3, -1)
    cv2.circle(ref, (90, 50), 6, .45, -1)
    c = dict(x=60, y=55, w=30, h=45)
    moved = cv2.warpAffine(ref, np.float32([[1, 0, 5], [0, 1, 2]]),
                          (160, 160), borderValue=.85)*.85+.05
    evidence = structure_change_evidence(ref, moved, c, .13)
    assert explained(evidence), evidence
    assert (evidence['dx'], evidence['dy']) == (-5, -2)
    assert abs(evidence['gain']-.85) < .01
    extra = ref.copy()
    cv2.circle(extra, (92, 80), 7, .1, -1)
    c = dict(x=85, y=73, w=15, h=15)
    assert not explained(structure_change_evidence(ref, extra, c, .13))
    cv2.circle(moved, (97, 82), 7, .1, -1)
    c = dict(x=90, y=75, w=15, h=15)
    assert not explained(structure_change_evidence(ref, moved, c, .13)), 'object plus motion lost'
    assert not explained(structure_change_evidence(ref, extra, dict(x=0,y=0,w=5,h=5), .13))
    repeated = np.full((160, 160), .85, np.float32)
    cv2.circle(repeated, (70, 80), 3, .1, -1)
    extra = repeated.copy()
    cv2.circle(extra, (80, 80), 3, .1, -1)
    assert not explained(structure_change_evidence(repeated, extra,
                         dict(x=77, y=77, w=7, h=7), .13)), 'nearby similar object erased'
    import sys
    for filename in sys.argv[1:]:
        case = np.load(filename)
        ref, target = case['ref'], case['target']
        changes = []
        candidates, _ = proposals(ref, target, machine_mask(ref), .20, changes)
        assert all(c['change_type']=='unexplained_object_candidate' for c in candidates)
        assert all(c['change_type']=='existing_structure_change' and explained(c['change_evidence']) for c in changes)
        assert not {tuple(c[k] for k in ('x','y','w','h')) for c in candidates} & {tuple(c[k] for k in ('x','y','w','h')) for c in changes}
        print(filename, 'candidates', len(candidates), 'structure changes', len(changes))
    print('PASS: moved/exposure-only structure, new object, motion plus object, clipped evidence and audit partition')


if __name__ == '__main__':
    run()
