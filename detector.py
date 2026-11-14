"""Local X-ray inspection prototype. No labels or sample coordinates enter detection."""
from pathlib import Path
import cv2
import numpy as np
import json

from runtime_paths import WORK_ROOT as ROOT
from model_manager import manager
from detection_runtime import CURRENT, detection, directions, parallel_map, PIPELINE
from brightness_fit import brightness

DETECTOR_VERSION = 13


def write_image(path, image):
    ok, encoded = cv2.imencode(Path(path).suffix, image)
    if not ok: raise ValueError('無法儲存影像')
    Path(path).write_bytes(encoded.tobytes())


def read(path):
    a = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    if a is None:
        raise ValueError('無法讀取影像，請使用 PNG、JPEG 或 TIFF')
    if a.ndim == 3:
        a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    if min(a.shape) < 128 or max(a.shape) > 16000:
        raise ValueError('影像尺寸需介於 128 與 16000 像素')
    lo, hi = np.percentile(a, [1, 99])
    if hi <= lo:
        raise ValueError('影像缺乏灰階變化，需重新拍攝／人工確認')
    return np.clip((a.astype(np.float32) - lo) / float(hi - lo), 0, 1)


def register(ref, raw):
    from registration_candidate import choose_registration
    return choose_registration(ref, raw, _register_orientation, machine_mask, correlation)


def _register_orientation(ref, raw):
    cv2.setRNGSeed(7)
    orb = cv2.ORB_create(nfeatures=7000)
    context = CURRENT.get()
    kr, dr = context.reference.features if context and ref is context.reference.small else orb.detectAndCompute((ref * 255).astype('uint8'), None)
    prepared_directions = directions(raw, dr)
    best = None
    for rotation in range(4):
        target, s, kt, dt, pairs = prepared_directions[rotation]
        if pairs is None:
            continue
        good = [m for pair in pairs if len(pair) == 2
                for m, n in [pair] if m.distance < 0.72 * n.distance]
        if len(good) < 10:
            continue
        src = np.float32([kt[m.queryIdx].pt for m in good])
        dst = np.float32([kr[m.trainIdx].pt for m in good])
        matrix, inside = cv2.estimateAffinePartial2D(
            src, dst, method=cv2.RANSAC, ransacReprojThreshold=2)
        if matrix is None:
            continue
        count = int(inside.sum())
        if best is None or count > best['inliers']:
            best = dict(inliers=count, rotation=rotation, matrix=matrix,
                        target=target, target_scale=s)
    if best is None or best['inliers'] < 25:
        raise ValueError('找不到足夠的共同結構，對齊失敗；需人工確認或重拍')
    matrix = best['matrix']
    scale = float(np.hypot(matrix[0, 0], matrix[0, 1]))
    if not 0.5 < scale < 2:
        raise ValueError('拍攝尺度差異過大，需人工確認')
    h, w = ref.shape
    best['aligned'] = cv2.warpAffine(best['target'], matrix, (w, h), borderValue=1)
    best['valid'] = cv2.warpAffine(np.ones(best['target'].shape, np.uint8), matrix, (w, h)) > 0
    return best


def structure_mask(ref):
    context = CURRENT.get()
    if context and ref is context.reference.small:
        return context.reference.structure
    mask = (ref < 0.65).astype('uint8')
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        raise ValueError('正常參考圖無法定位機體')
    mask = (labels == (1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype('uint8')
    return cv2.erode(mask, np.ones((11, 11), np.uint8)).astype(bool)


def machine_mask(ref):
    """Inspect the main body envelope, including bright cavities and side recesses."""
    context = CURRENT.get()
    if context and ref is context.reference.small:
        return context.reference.machine
    structure = structure_mask(ref).astype('uint8')
    contours, _ = cv2.findContours(structure, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError('正常參考圖無法定位機體')
    filled = np.zeros_like(structure)
    # Closing holes alone leaves open side recesses outside the contour. Use the
    # convex envelope of the main body, not a hull of all objects in the image.
    hull = cv2.convexHull(max(contours, key=cv2.contourArea))
    cv2.fillConvexPoly(filled, hull, 1)
    return filled.astype(bool)


def compensate_brightness(ref, target):
    """Robust local affine exposure fit; strong residuals cannot train away objects."""
    return brightness(ref, target)


def correlation(a, b, mask):
    if int(mask.sum()) < 100:
        return 0.0
    x, y = a[mask], b[mask]
    if x.std() < .01 or y.std() < .01:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def refine(ref, aligned, mask):
    """Bounded translations on 3x3 regions; smooth remap, no unconstrained warp."""
    ys, xs = np.where(mask)
    x_edges = np.linspace(xs.min(), xs.max() + 1, 4).astype(int)
    y_edges = np.linspace(ys.min(), ys.max() + 1, 4).astype(int)
    shifts = np.zeros((3, 3, 2), np.float32)
    regions = []
    inner_masks = []
    for row in range(3):
        for col in range(3):
            x0, x1 = x_edges[col:col+2]
            y0, y1 = y_edges[row:row+2]
            a = ref[y0:y1, x0:x1].copy()
            b = aligned[y0:y1, x0:x1].copy()
            roi_mask = mask[y0:y1, x0:x1]
            roi_u8 = roi_mask.astype('uint8')
            inner = cv2.erode(roi_u8, np.ones((15, 15), np.uint8)) > 0
            base_inner = correlation(a, b, inner)
            inner_masks.append((inner, base_inner))
            before = correlation(a, b, roi_mask)
            mat = np.eye(2, 3, dtype=np.float32)
            accepted = False
            after = before
            dx = dy = 0.0
            try:
                cc, mat = cv2.findTransformECC(
                    a, b, mat, cv2.MOTION_TRANSLATION,
                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, .0001),
                    roi_u8 * 255, 5)
                corrected = cv2.warpAffine(b, mat, (a.shape[1], a.shape[0]),
                                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                          borderMode=cv2.BORDER_REFLECT)
                after = correlation(a, corrected, inner)
                before = base_inner
                accepted = bool(cc > .82 and np.max(np.abs(mat[:, 2])) <= 6
                                and after >= base_inner + .0001)
                if accepted:
                    dx, dy = map(float, mat[:, 2])
                    shifts[row, col] = [dx, dy]
            except cv2.error:
                pass
            reliable = max(before, after if accepted else before) >= .82
            regions.append(dict(region=f'{row+1}-{col+1}', bbox=[int(x0), int(y0), int(x1), int(y1)],
                                before=round(before, 4), after=round(after if accepted else before, 4),
                                dx=round(dx, 3), dy=round(dy, 3), refined=accepted,
                                reliable=bool(reliable)))
    # Keep each region's measured translation in its interior; feather only seams.
    flow = np.zeros((*ref.shape, 2), np.float32)
    for row in range(3):
        for col in range(3):
            x0, x1 = x_edges[col:col+2]
            y0, y1 = y_edges[row:row+2]
            flow[y0:y1, x0:x1] = shifts[row, col]
    flow = cv2.GaussianBlur(flow, (0, 0), 12)
    base_x, base_y = np.meshgrid(np.arange(ref.shape[1], dtype='float32'),
                                np.arange(ref.shape[0], dtype='float32'))
    mapx, mapy = base_x + flow[..., 0], base_y + flow[..., 1]
    corrected = cv2.remap(aligned, mapx, mapy, cv2.INTER_LINEAR, borderValue=1)
    for region, (inner, before) in zip(regions, inner_masks):
        x0, y0, x1, y1 = region['bbox']
        after = correlation(ref[y0:y1, x0:x1], corrected[y0:y1, x0:x1], inner)
        region['before'] = round(before, 4)
        region['after'] = round(after, 4)
        region['reliable'] = bool(after >= .82 and after >= before - .01)
    return corrected, flow, regions


def legacy_proposals(ref, target, mask, threshold):
    residual = ((ref - cv2.GaussianBlur(ref, (0, 0), 15)) -
                (target - cv2.GaussianBlur(target, (0, 0), 15)))
    edges = cv2.Canny((ref * 255).astype('uint8'), 40, 100)
    band = cv2.dilate(edges, np.ones((9, 9), np.uint8)) > 0
    binary = ((residual > threshold) & mask & ~band).astype('uint8')
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    candidates = []
    normal_nearby = cv2.erode(ref, np.ones((15, 15), np.uint8))
    for i in range(1, n):
        x, y, w, h, area = map(int, stats[i])
        if not (12 <= area <= 1800 and 4 <= max(w, h) <= 110):
            continue
        component = (labels[y:y+h, x:x+w] == i)
        py, px = np.where(component)
        points = np.column_stack([px, py]).astype('float32')
        _, (a, b), _ = cv2.minAreaRect(points)
        aspect = (max(a, b) + 1) / (min(a, b) + 1)
        score = float(np.percentile(residual[y:y+h, x:x+w][component], 90))
        # Normal-metal proximity and bipolar residual distinguish edge motion from extra objects.
        nearby = (slice(max(0, y-5), min(ref.shape[0], y+h+5)),
                  slice(max(0, x-5), min(ref.shape[1], x+w+5)))
        diff = residual[nearby]
        negative = float(np.maximum(-diff, 0).sum())
        positive = float(np.maximum(diff, 0).sum())
        bipolar = negative / max(positive, 1e-6)
        contrast = float(np.median(ref[y:y+h, x:x+w][component] -
                                   target[y:y+h, x:x+w][component]))
        normal_support = float(np.mean((normal_nearby[y:y+h, x:x+w] <=
                                        target[y:y+h, x:x+w] + .06)[component]))
        candidates.append(dict(x=x, y=y, w=w, h=h, area=area, score=round(score, 4),
                               normal_support=round(normal_support, 3),
                               aspect=round(float(aspect), 2), fill=round(area/(w*h), 3),
                               bipolar=round(bipolar, 3), contrast=round(contrast, 4)))
    candidates.sort(key=lambda c: c['score'], reverse=True)
    return candidates, residual


def matching_structure(ref, target, x, y, w, h):
    padding, radius = 6, 12
    x0, y0 = max(radius, x-padding), max(radius, y-padding)
    x1, y1 = min(ref.shape[1]-radius, x+w+padding), min(ref.shape[0]-radius, y+h+padding)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    patch = target[y0:y1, x0:x1].astype('float32')
    if patch.std() < .015:
        return 0.0
    search = ref[y0-radius:y1+radius, x0-radius:x1+radius].astype('float32')
    return float(cv2.matchTemplate(search, patch, cv2.TM_CCOEFF_NORMED).max())


def structure_change_evidence(ref, target, candidate, threshold):
    """Explain a candidate with bounded translation and context-only exposure fit.

    Similarity alone cannot reject an object: most positive residual must also
    disappear, with no object-sized component left. This does not certify normality.
    """
    x, y, w, h = (candidate[k] for k in ('x', 'y', 'w', 'h'))
    padding, radius = 12, 12
    x0, y0 = max(radius, x-padding), max(radius, y-padding)
    x1 = min(ref.shape[1]-radius, x+w+padding)
    y1 = min(ref.shape[0]-radius, y+h+padding)
    # A clipped candidate cannot support a complete explanation.
    if x0 > x or y0 > y or x1 < x+w or y1 < y+h:
        return {}
    patch = target[y0:y1, x0:x1].astype('float32')
    if patch.size == 0 or patch.std() < .015:
        return {}
    search = ref[y0-radius:y1+radius, x0-radius:x1+radius].astype('float32')
    scores = cv2.matchTemplate(search, patch, cv2.TM_CCOEFF_NORMED)
    _, similarity, _, point = cv2.minMaxLoc(scores)
    dx, dy = point[0]-radius, point[1]-radius
    normal = ref[y0+dy:y1+dy, x0+dx:x1+dx].astype('float32')
    core = (slice(y-y0, y+h-y0), slice(x-x0, x+w-x0))
    context = np.ones_like(patch)
    context[core] = 0  # An extra object must not train its own brightness correction.
    outside = context > 0
    def context_similarity(image):
        a, b = image[outside], patch[outside]
        if a.std() < .015 or b.std() < .015:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])
    context_match = context_similarity(normal)
    context_before = context_similarity(ref[y0:y1, x0:x1])
    # A nearby similar screw is not evidence that the surrounding structure moved.
    supported = context_match >= .6 and (max(abs(dx), abs(dy)) <= 2
                                         or context_match >= context_before + .03)
    weights = context.copy()
    for _ in range(4):
        mass = max(float(weights.sum()), .001)
        mx = (weights*normal).sum()/mass
        my = (weights*patch).sum()/mass
        covariance = (weights*(normal-mx)*(patch-my)).sum()
        variance = (weights*(normal-mx)**2).sum()
        gain = np.clip(covariance/max(float(variance), .001), .6, 1.6)
        offset = np.clip(my-gain*mx, -.25, .25)
        fitted = np.clip(gain*normal+offset, 0, 1)
        error = np.abs(fitted-patch)
        weights = context*np.minimum(1, .04/np.maximum(error, .0001))**2
    difference = fitted[core]-patch[core]
    original = ref[y:y+h, x:x+w]-target[y:y+h, x:x+w]
    ratio = float(np.maximum(difference, 0).sum()) / max(float(np.maximum(original, 0).sum()), .001)
    _, _, stats, _ = cv2.connectedComponentsWithStats((difference > threshold).astype('uint8'))
    remaining = max(stats[1:, cv2.CC_STAT_AREA], default=0)
    return dict(sim=float(similarity), context_similarity=context_match,
                context_before=context_before, context_supported=bool(supported),
                dx=dx, dy=dy, gain=float(gain),
                offset=float(offset), ratio=ratio, remaining=int(remaining))


def proposals(ref, target, mask, threshold, structure_changes=None, similarity_recoveries=None, *, predicted=None):
    if predicted is None:
        predicted = compensate_brightness(ref, target)
    residual = cv2.erode(predicted, np.ones((7, 7), np.uint8)) - target
    shared_arrays = (cv2.erode(predicted, np.ones((15, 15), np.uint8)), predicted-target)
    candidates, _ = candidates_from_residual(ref, target, mask, threshold, predicted, residual, shared_arrays,
                                             similarity_recoveries=similarity_recoveries)
    # Tight-tolerance recovery: small objects beside existing dark structures can
    # be erased by the main 3px tolerance. Require compact, novel, predominantly
    # one-sided evidence before retaining a 1px-tolerance candidate.
    tight_residual = cv2.erode(predicted, np.ones((3, 3), np.uint8)) - target
    recovered, _ = candidates_from_residual(ref, target, mask, threshold, predicted, tight_residual, shared_arrays)
    for candidate in recovered:
        c = candidate
        if not (25 <= c['area'] <= 600 and max(c['w'], c['h']) <= 50
                and c['aspect'] <= 4 and c['fill'] >= .25
                and c['score'] >= threshold + .05 and c['bipolar'] <= .5
                and c['shape_similarity'] <= .55):
            continue
        duplicate = False
        for existing in candidates:
            overlap = max(0, min(c['x']+c['w'], existing['x']+existing['w'])-max(c['x'],existing['x'])) * max(0,min(c['y']+c['h'],existing['y']+existing['h'])-max(c['y'],existing['y']))
            if overlap / max(1, min(c['w']*c['h'], existing['w']*existing['h'])) > .25:
                duplicate = True
                break
        if not duplicate:
            c['recovery'] = 'tight_spatial_tolerance'
            candidates.append(c)
            x, y, w, h = (c[k] for k in ('x','y','w','h'))
            residual[y:y+h,x:x+w] = np.maximum(residual[y:y+h,x:x+w], tight_residual[y:y+h,x:x+w])
    retained = []
    for c, explained in parallel_map(lambda c: check_candidate(ref, target, c, threshold), candidates, 1):
        if explained:
            if structure_changes is not None:
                structure_changes.append(c)
        else:
            retained.append(c)
    retained.sort(key=lambda c:c['score'], reverse=True)
    return retained, residual


def check_candidate(ref, target, c, threshold):
    evidence = structure_change_evidence(ref, target, c, threshold)
    explained = bool(evidence and evidence['context_supported'] and evidence['sim'] >= .65
                     and evidence['ratio'] <= .2 and evidence['remaining'] < 12)
    if not explained:
        from single_reference_evidence import explain
        context_evidence = explain(ref, target, c, threshold)
        if context_evidence:
            c['single_reference_evidence'] = context_evidence
            explained = True
    c['change_evidence'] = evidence
    c['change_type'] = 'existing_structure_change' if explained else 'unexplained_object_candidate'
    if not explained:
        from wire_review import review_evidence
        wire = review_evidence(ref, target, c, threshold)
        if wire:
            c['wire_review'] = wire
    return c, explained


def candidates_from_residual(ref, target, mask, threshold, predicted, residual, shared_arrays=None,
                             similarity_recoveries=None):
    binary = ((residual > threshold) & mask).astype('uint8')
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    # Separate a compact object from long connected residuals instead of dropping
    # the entire oversized component. Keep ordinary small components intact.
    n, component_labels, component_stats, _ = cv2.connectedComponentsWithStats(binary)
    changed = False
    for index, (x, y, w, h, area) in enumerate(component_stats[1:], 1):
        if area > 1800 or max(w, h) > 110:
            region = (component_labels[y:y+h, x:x+w] == index).astype('uint8')
            separated = cv2.morphologyEx(region, cv2.MORPH_OPEN,
                                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
            inside = region > 0
            if not np.array_equal(region[inside], separated[inside]):
                changed = True
                binary[y:y+h, x:x+w][inside] = separated[inside]

    if changed:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    else:
        labels, stats = component_labels, component_stats
    candidates = []
    normal_nearby, signed_difference = shared_arrays if shared_arrays is not None else (cv2.erode(predicted, np.ones((15, 15), np.uint8)), predicted-target)
    for i in range(1, n):
        x, y, w, h, area = map(int, stats[i])
        if not (12 <= area <= 1800 and 4 <= max(w, h) <= 110):
            continue
        component = (labels[y:y+h, x:x+w] == i)
        py, px = np.where(component)
        points = np.column_stack([px, py]).astype('float32')
        _, (a, b), _ = cv2.minAreaRect(points)
        aspect = (max(a, b) + 1) / (min(a, b) + 1)
        score = float(np.percentile(residual[y:y+h, x:x+w][component], 90))
        # Normal-metal proximity and bipolar residual distinguish edge motion from extra objects.
        nearby = (slice(max(0, y-5), min(ref.shape[0], y+h+5)),
                  slice(max(0, x-5), min(ref.shape[1], x+w+5)))
        diff = signed_difference[nearby]
        negative = float(np.maximum(-diff, 0).sum())
        positive = float(np.maximum(diff, 0).sum())
        bipolar = negative / max(positive, 1e-6)
        contrast = float(np.median(predicted[y:y+h, x:x+w][component] -
                                   target[y:y+h, x:x+w][component]))
        normal_support = float(np.mean((normal_nearby[y:y+h, x:x+w] <=
                                        target[y:y+h, x:x+w] + .06)[component]))
        shape_similarity = matching_structure(ref, target, x, y, w, h)
        # Correlation ignores brightness offsets/gain; suppress a close existing
        # shape only when the local template has a strong match.
        if area < 40 and (shape_similarity > .55 or normal_support > .5):
            continue
        if shape_similarity >= .85 and similarity_recoveries is None:
            continue
        candidate = dict(shape_similarity=round(shape_similarity, 3), x=x, y=y, w=w, h=h, area=area, score=round(score, 4),
                         normal_support=round(normal_support, 3),
                         aspect=round(float(aspect), 2), fill=round(area/(w*h), 3),
                         bipolar=round(bipolar, 3), contrast=round(contrast, 4))
        if shape_similarity >= .85:
            from overkill_pilot import similarity_recovery
            evidence = similarity_recovery(ref, target, candidate, threshold, structure_change_evidence)
            if evidence:
                candidate.update(shape_similarity=shape_similarity, recovery='overkill_pilot_similarity', pilot_context=evidence)
                similarity_recoveries.append(candidate)
        else:
            candidates.append(candidate)
    candidates.sort(key=lambda c: c['score'], reverse=True)
    return candidates, residual


def prioritize(candidate):
    """Conservative heuristic ranking, never deletes proposals; not a screw classifier."""
    c = candidate
    reasons = []
    if c.get('wire_review'):
        reasons.append('疑似線材位移：兩側線條連續且原位置有變化；候選仍保留，小螺絲可能混在線材中，需複核')
    if c.get('shape_similarity', 0) > .65:
        reasons.append('附近有相似輪廓，可能為既有結構的對齊或外觀差異')
    if c['normal_support'] > .5:
        reasons.append('正常圖鄰近有相似深色結構，可能為固定零件或線材偏移')
    if c['aspect'] > 8:
        reasons.append('輪廓過於細長，疑似線材或邊界殘差')
    if c['contrast'] < .12:
        reasons.append('相對正常圖的額外衰減較弱')
    if c['bipolar'] > .7:
        reasons.append('鄰近同時出現明暗差分，疑似結構偏移')
    if c['area'] < 35:
        reasons.append('差分面積較小，保留供複核')
    if c['fill'] < .18:
        reasons.append('輪廓稀疏或破碎')
    return reasons


def source_points(points, reg, flow, raw_shape):
    points = np.asarray(points, np.float32).reshape(-1, 2)
    ix = np.clip(np.rint(points[:, 0]).astype(int), 0, flow.shape[1]-1)
    iy = np.clip(np.rint(points[:, 1]).astype(int), 0, flow.shape[0]-1)
    global_points = points + flow[iy, ix]
    inv = cv2.invertAffineTransform(reg['matrix'])
    rotated = cv2.transform(global_points[None], inv)[0]
    # cv2.resize maps pixel centres with this half-pixel convention.
    rotated = (rotated + .5) / reg['target_scale'] - .5
    x, y = rotated[:, 0], rotated[:, 1]
    h, w = raw_shape
    k = reg['rotation']
    if k == 0: result = np.column_stack([x, y])
    elif k == 1: result = np.column_stack([w-1-y, x])
    elif k == 2: result = np.column_stack([w-1-x, h-1-y])
    else: result = np.column_stack([y, h-1-x])
    if reg.get('mirrored', False):
        result[:, 0] = w-1-result[:, 0]
    result[:, 0] = np.clip(result[:, 0], 0, w-1)
    result[:, 1] = np.clip(result[:, 1], 0, h-1)
    return result


def detect(reference, target, name, threshold=.13, model_snapshot=None, output_directory=None):
    with detection(reference, read, structure_mask, machine_mask):
        return _detect(reference, target, name, threshold, model_snapshot, output_directory)


def _detect(reference, target, name, threshold=.13, model_snapshot=None, output_directory=None):
    model_snapshot = model_snapshot or manager.snapshot()
    import overkill_pilot
    pilot_enabled = overkill_pilot.enabled(model_snapshot)
    if not np.isfinite(threshold) or not .03 <= threshold <= .4:
        raise ValueError('門檻需介於 0.03 與 0.40')
    context = CURRENT.get()
    ref, raw = context.reference.full, read(target)
    r = context.reference.small
    reg = register(r, raw)
    mask = machine_mask(r) & reg['valid']
    total = max(int(context.reference.machine.sum()), 1)
    coverage = int(mask.sum()) / total
    if coverage < .95:
        raise ValueError('待測影像未完整覆蓋正常參考機體，需重新拍攝／人工確認')
    baseline, _ = legacy_proposals(r, reg['aligned'], structure_mask(r) & reg['valid'], threshold)
    corrected, flow, regions = refine(r, reg['aligned'], structure_mask(r) & reg['valid'])
    structure_changes = []
    recovered = [] if pilot_enabled else None
    candidates, residual = proposals(r, corrected, mask, threshold, structure_changes, recovered)
    if recovered:
        additions = []
        for candidate in sorted(recovered, key=lambda c: -c['score']):
            if not overkill_pilot.overlapping(candidate, candidates):
                candidate, explained = check_candidate(r, corrected, candidate, threshold)
                if not explained:
                    additions.append(candidate)
    else:
        additions = []
    for c in candidates + additions:
        c['reasons'] = prioritize(c)
        c['priority'] = 'review' if c['reasons'] else 'high'
    candidates.sort(key=lambda c: (c['priority'] != 'high', -c['score']))
    candidates.extend(additions)
    for i, c in enumerate(candidates, 1):
        c['id'] = i
        x, y, w, h = [c[k] for k in ('x', 'y', 'w', 'h')]
        points = source_points([[x-5, y-5], [x+w+5, y-5],
                                [x+w+5, y+h+5], [x-5, y+h+5]], reg, flow, raw.shape)
        c['source_polygon'] = np.round(points, 2).tolist()
        x0, y0 = np.floor(points.min(axis=0)).astype(int)
        x1, y1 = np.ceil(points.max(axis=0)).astype(int)
        c['source_bbox'] = [int(x0), int(y0), int(x1), int(y1)]
    out = Path(output_directory) if output_directory is not None else ROOT/'outputs'/name
    out.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(structure_changes, 1):
        c['id'] = i
        x, y, w, h = (c[k] for k in ('x', 'y', 'w', 'h'))
        region = (slice(max(0, y-12), y+h+12), slice(max(0, x-12), x+w+12))
        for prefix, image in [('structure_ref', r), ('structure_target', corrected)]:
            write_image(str(out/f'{prefix}_{i}.png'), (image[region]*255).astype('uint8'))
    ys, xs = np.where(mask)
    machine_points = source_points([[xs.min(), ys.min()], [xs.max(), ys.min()],
                                    [xs.max(), ys.max()], [xs.min(), ys.max()]], reg, flow, raw.shape)
    machine_box = [max(0, int(machine_points[:, 0].min())-35),
                   max(0, int(machine_points[:, 1].min())-35),
                   min(raw.shape[1], int(machine_points[:, 0].max())+35),
                   min(raw.shape[0], int(machine_points[:, 1].max())+35)]
    zero_flow = np.zeros_like(flow)
    for i, c in enumerate(baseline, 1):
        c['id'] = i
        x, y, w, h = [c[k] for k in ('x', 'y', 'w', 'h')]
        p = source_points([[x-25, y-25], [x+w+25, y-25],
                           [x+w+25, y+h+25], [x-25, y+h+25]], reg, zero_flow, raw.shape)
        b0 = np.floor(p.min(axis=0)).astype(int)
        b1 = np.ceil(p.max(axis=0)).astype(int)+1
        crop = raw[b0[1]:b1[1], b0[0]:b1[0]]
        write_image(str(out/f'baseline_crop_{i}.png'), (crop*255).astype('uint8'))
        write_image(str(out/f'baseline_ref_{i}.png'),
                    (r[max(0,y-25):y+h+25, max(0,x-25):x+w+25]*255).astype('uint8'))
        matches = [z['id'] for z in candidates if
                   min(x+w+8, z['x']+z['w']) > max(x-8, z['x']) and
                   min(y+h+8, z['y']+z['h']) > max(y-8, z['y'])]
        c['v2_nearby_ids'] = matches
        c['audit'] = '鄰近仍有目前版本候選，請逐圖確認' if matches else '局部對齊後未達候選門檻；不代表正常'
    source_preview = cv2.cvtColor((raw*255).astype('uint8'), cv2.COLOR_GRAY2BGR)
    # Save natural-orientation preview at <=1536px; source coordinates remain native pixels.
    preview_scale = 1536/max(raw.shape)
    source_preview = cv2.resize(source_preview, None, fx=preview_scale, fy=preview_scale)
    for c in candidates:
        i = c['id']
        x0, y0, x1, y1 = c['source_bbox']
        pad = max(45, (x1-x0)//2, (y1-y0)//2)
        box = [max(0, x0-pad), max(0, y0-pad), min(raw.shape[1], x1+pad), min(raw.shape[0], y1+pad)]
        c['crop_box'] = list(map(int, box))
        crop = (raw[box[1]:box[3], box[0]:box[2]]*255).astype('uint8')
        write_image(str(out/f'crop_{i}.png'), crop)
        if model_snapshot.manifest.get('backend') == 'dino_onnx':
            c['classification'] = classify_dino_candidate(model_snapshot, corrected, r, c)
            if pilot_enabled:
                ref_u8, target_u8 = context.arrays(r, corrected)
                c['classification'] = overkill_pilot.apply(model_snapshot, ref_u8, target_u8, c, c['classification'])
        elif model_snapshot.manifest.get('preprocessing') == 'aligned-gray-tight12-v1':
            cx, cy, cw, ch = (c[k] for k in ('x','y','w','h'))
            ai_crop = corrected[max(0,cy-12):cy+ch+12, max(0,cx-12):cx+cw+12]
            # Match the previously evaluated PNG crop quantization exactly.
            ai_crop = (np.clip(ai_crop,0,1)*255).astype('uint8').astype('float32')/255
        else:
            ai_crop = raw[box[1]:box[3], box[0]:box[2]]
        if model_snapshot.manifest.get('backend') == 'dino_onnx':
            pass
        elif model_snapshot.manifest.get('backend')=='yolo_onnx':
            x0,y0=max(0,cx-12),max(0,cy-12)
            c['classification'] = model_snapshot.classify(ai_crop, candidate_box=[cx-x0,cy-y0,cx-x0+cw,cy-y0+ch])
        else:
            c['classification'] = model_snapshot.classify(ai_crop)
        x, y, w, h = [c[k] for k in ('x', 'y', 'w', 'h')]
        patch = (r[max(0,y-25):y+h+25, max(0,x-25):x+w+25]*255).astype('uint8')
        write_image(str(out/f'reference_crop_{i}.png'), patch)
    pre_ai_count = len(candidates)
    filtered_candidates = [c for c in candidates if c['classification'].get('action') == 'discard']
    candidates = [c for c in candidates if c['classification'].get('action') != 'discard']
    # Render only retained candidates. Preserve original IDs and crops for the audit.
    high, all_overlay = source_preview.copy(), source_preview.copy()
    for c in candidates:
        points = np.rint(np.asarray(c['source_polygon'])*preview_scale).astype('int32')
        color = (60, 65, 245) if c['priority'] == 'high' else (0, 185, 245)
        for canvas in ([high, all_overlay] if c['priority'] == 'high' else [all_overlay]):
            cv2.polylines(canvas, [points], True, color, 2)
            cv2.putText(canvas, str(c['id']), tuple(points.min(axis=0)-[0, 6]), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
    write_image(str(out/'source.png'), source_preview)
    write_image(str(out/'overlay.png'), high)
    write_image(str(out/'all_overlay.png'), all_overlay)
    for key, arr in [('aligned', corrected), ('reference', r)]:
        write_image(str(out/f'{key}.png'), (arr*255).astype('uint8'))
    heat = np.clip(residual/.3, 0, 1)
    heat[~mask] = 0
    write_image(str(out/'difference.png'), cv2.applyColorMap((heat*255).astype('uint8'), cv2.COLORMAP_INFERNO))
    n_high = sum(c['priority'] == 'high' for c in candidates)
    result = dict(model=model_snapshot.info(), version=DETECTOR_VERSION, pipeline=PIPELINE, name=name, status='需人工複核',
                  rotation_ccw=reg['rotation']*90, mirrored_input=reg.get('mirrored',False),
                  orientation_evidence=reg.get('orientation_evidence'), inliers=reg['inliers'], threshold=threshold,
                  source_shape=list(raw.shape), source_machine_bbox=machine_box, preview_scale=preview_scale,
                  coordinate_frame='x/y/w/h: reference preview; source_bbox/polygon: original target pixels',
                  matrix=reg['matrix'].tolist(), local_alignment=regions,
                  alignment_warning=any(not z['reliable'] for z in regions),
                  coverage=round(coverage, 4), baseline_candidates=baseline,
                  baseline_count=len(baseline), proposal_count=len(candidates),
                  pre_ai_count=pre_ai_count, filtered_count=len(filtered_candidates), filtered_candidates=filtered_candidates,
                  structure_change_count=len(structure_changes), structure_changes=structure_changes,
                  high_count=n_high, review_count=len(candidates)-n_high, candidates=candidates,
                  wire_review_count=sum(bool(c.get('wire_review')) for c in candidates),
                  warning='紅框為規則優先候選，不是 AI 確認螺絲；黃色候選仍需查看。無紅框不代表正常。')
    if pilot_enabled:
        result['experimental_policy'] = overkill_pilot.VERSION
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def classify_dino_candidate(snapshot, target, reference, candidate):
    """Same coordinates, padding and PNG quantization as the frozen report."""
    if snapshot.manifest.get('feature_strategy') == 'contrast-global-local-half-v1':
        from dino_paired_optimized import classify_candidate
        return classify_candidate(snapshot, target, reference, candidate)
    x, y, w, h = (candidate[k] for k in ('x', 'y', 'w', 'h'))
    region = (slice(max(0, y-12), y+h+12), slice(max(0, x-12), x+w+12))
    crops = [(np.clip(im[region], 0, 1)*255).astype('uint8').astype('float32')/255
             for im in (target, reference)]
    return snapshot.classify(crops[0], reference_crop=crops[1])


if __name__ == '__main__':
    for name in ['ok_0', 'ng_5', 'ng_9']:
        result = detect(ROOT/'data/ok_0.png', ROOT/f'data/{name}.png', name+'_v2')
        print(name, 'baseline', result['baseline_count'], 'proposals', result['proposal_count'],
              'high', result['high_count'], 'review', result['review_count'])
