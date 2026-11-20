"""Offline contour sensitivity audit. No classification or production writes.

Fixed intensity sweep is a diagnostic, not a learned segmentation threshold.
Closed components may still be normal board structures: never call them objects.
"""
import hashlib
import cv2
import numpy as np

LEVELS = (32, 64, 96, 128, 160, 192, 224)
PADS = (12, 20, 32)


def iou(a, b):
    x, y, w, h = a
    X, Y, W, H = b
    area = max(0, min(x+w, X+W)-max(x, X))*max(0, min(y+h, Y+H)-max(y, Y))
    return area / max(1, w*h+W*H-area)


def analyze(target, seeds):
    """Full-image components avoid inventing boundaries at crop edges.

    A component is supported only when >=half the seed rectangle is inside,
    and its whole boundary lies strictly inside every diagnostic window.
    Adjacent-level support is recorded, not interpreted as semantic completeness.
    Merge suggestions require the exact same component at BOTH levels; there
    is no proximity merge or transitive union of partially overlapping groups.
    """
    target = np.asarray(target, dtype=np.uint8)
    height, width = target.shape
    rows = [dict(id=s['id'], seed=s['seed'], levels=[], boundary_status='unknown',
                 object_box=None, dino_evaluated=False) for s in seeds]
    for level in LEVELS:
        _, labels, stats, _ = cv2.connectedComponentsWithStats((target < level).astype('uint8'))
        for row in rows:
            x,y,w,h = [int(row['seed'][k]) for k in ('x','y','w','h')]
            assert 0 <= x < x+w <= width and 0 <= y < y+h <= height
            ids, counts = np.unique(labels[y:y+h,x:x+w], return_counts=True)
            foreground = ids != 0
            if not foreground.any():
                row['levels'].append(dict(level=level, supported=False, reason='no_foreground'))
                continue
            ids, counts = ids[foreground], counts[foreground]
            k = int(np.argmax(counts)); ident = int(ids[k]); coverage = float(counts[k]/(w*h))
            a,b,u,v,area = map(int, stats[ident])
            closed = [a > max(0,x-pad) and b > max(0,y-pad) and
                      a+u < min(width,x+w+pad) and b+v < min(height,y+h+pad) for pad in PADS]
            row['levels'].append(dict(level=level, component=ident, box=[a,b,u,v],
                area=area, seed_coverage=coverage, closed_windows=closed,
                supported=coverage >= .5 and all(closed)))
    groups = {}
    for row in rows:
        row['stable_pairs'] = []
        for a,b in zip(row['levels'],row['levels'][1:]):
            if a['supported'] and b['supported'] and iou(a['box'],b['box']) >= .8:
                key = (a['level'], a['component'], b['component'])
                groups.setdefault(key, []).append(row['id'])
                row['stable_pairs'].append(dict(levels=[a['level'],b['level']], boxes=[a['box'],b['box']]))
        if row['stable_pairs']:
            row['boundary_status'] = 'closed_contour_hypothesis_not_verified_object'
    merges = [dict(level_pair=[key[0], key[0]+32], components=list(key[1:]), seed_ids=members,
                   action='observe_only', semantic_identity='unknown')
              for key,members in groups.items() if len(members)>1]
    return dict(rows=rows, merge_hypotheses=merges, intensity_levels=list(LEVELS),
                window_pads=list(PADS), official_decisions_changed=False,
                image_sha256=hashlib.sha256(target.tobytes()).hexdigest())
