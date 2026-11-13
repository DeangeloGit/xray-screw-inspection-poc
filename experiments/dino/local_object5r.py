"""Experimental image-derived compact-object review. Not enabled in 5r service.

A long proposal may contain a screw attached to a thin wire. Opening at two
scales removes thin connections; only compact components present at both
scales are reviewed. No photo IDs, answer boxes or old predictions locate cores.
"""
import copy

import cv2
import numpy as np

VERSION = '5r-core-object-bank-multiscale-trial-20261113'


def compact_cores(target, box):
    x, y, w, h = map(int, box)
    if min(w, h) <= 0 or max(w, h) <= 3 * min(w, h):
        return []
    image = np.rint(np.clip(target, 0, 1) * 255).astype('uint8')
    x0, y0 = max(0, x - 4), max(0, y - 4)
    roi = image[y0:min(image.shape[0], y + h + 4),
                x0:min(image.shape[1], x + w + 4)]
    if not roi.size or int(roi.max()) == int(roi.min()):
        return []
    threshold, mask = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    by_scale = {}
    # A fixed pair of opening sizes failed when a thicker, resampled wire
    # stayed connected to the screw. Search all fitting odd sizes instead;
    # persistence across adjacent scales identifies the compact component.
    scales = list(range(3, min(w, h) + 1, 2))
    for size in scales:
        opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
        _, _, stats, centers = cv2.connectedComponentsWithStats(opened)
        components = []
        for (xx, yy, ww, hh, area), (cx, cy) in zip(stats[1:], centers[1:]):
            if (min(ww, hh) < 3 or max(ww, hh) > 3 * min(ww, hh) or area < 9
                    or not (x <= x0 + cx < x + w and y <= y0 + cy < y + h)):
                continue
            components.append([int(x0 + xx), int(y0 + yy), int(ww), int(hh)])
        by_scale[size] = components
    result = []
    def overlap(a, b):
            inter = max(0, min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0])) * max(
                0, min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))
            return inter / max(1, a[2]*a[3] + b[2]*b[3] - inter)
    for small, large in zip(scales, scales[1:]):
        for a in by_scale[large]:
            for b in by_scale[small]:
                iou = overlap(a, b)
                if iou >= .8:
                    if not any(overlap(a, r['box']) >= .8 for r in result):
                        result.append(dict(box=a, threshold=float(threshold), scale_iou=float(iou),
                                           opening_sizes=[small, large]))
                    break
    return result


def review_lost_keep(core_snapshot, reference, target, baseline, trial):
    """Review losses only; cannot independently introduce a new baseline alarm.

    This protection is experimental, not proof of regression acceptance. The
    unchanged paired classifier and existing object bank make the decision on
    each image-derived core. Fragment additions do not re-label the reference
    of this complete-object check.
    """
    if baseline.get('filter_recommendation') != 'keep' or trial.get('filter_recommendation') != 'exclude':
        return trial
    from dino_paired_optimized import classify_candidate
    extent = trial['canonical_object']['box']
    checks = []
    for core in compact_cores(target, extent):
        candidate = dict(zip(('x', 'y', 'w', 'h'), core['box']))
        pred = classify_candidate(core_snapshot, target, reference, candidate)
        checks.append(dict(core=core, prediction=pred))
    accepted = next((r for r in checks if r['prediction']['filter_recommendation'] == 'keep'), None)
    result = copy.deepcopy(accepted['prediction'] if accepted else trial)
    result['local_object5r'] = dict(version=VERSION, checks=checks, accepted=bool(accepted),
                                   previous=trial, baseline_was_keep=True)
    if accepted:
        result['canonical_object'] = dict(trial['canonical_object'], previous_box=extent,
                                           box=accepted['core']['box'], version=VERSION)
        result['decision_reason'] = '5r 實驗：長條候選內有跨尺寸穩定的局部物件；雙圖判斷支持待測螺絲，保留。'
    return result
