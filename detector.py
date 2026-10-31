"""Local X-ray inspection prototype. No labels or sample coordinates enter detection."""
from pathlib import Path
import cv2
import numpy as np
import json

ROOT = Path(__file__).resolve().parent


def read(path):
    a = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
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
    cv2.setRNGSeed(7)
    orb = cv2.ORB_create(nfeatures=7000)
    kr, dr = orb.detectAndCompute((ref * 255).astype('uint8'), None)
    best = None
    for rotation in range(4):
        rotated = np.rot90(raw, rotation).copy()
        s = 1536 / max(rotated.shape)
        target = cv2.resize(rotated, None, fx=s, fy=s)
        kt, dt = orb.detectAndCompute((target * 255).astype('uint8'), None)
        if dt is None or dr is None:
            continue
        pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(dt, dr, k=2)
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


def machine_mask(ref):
    mask = (ref < 0.65).astype('uint8')
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        raise ValueError('正常參考圖無法定位機體')
    mask = (labels == (1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype('uint8')
    return cv2.erode(mask, np.ones((11, 11), np.uint8)).astype(bool)


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
    for row in range(3):
        for col in range(3):
            x0, x1 = x_edges[col:col+2]
            y0, y1 = y_edges[row:row+2]
            a = ref[y0:y1, x0:x1].copy()
            b = aligned[y0:y1, x0:x1].copy()
            roi_mask = mask[y0:y1, x0:x1]
            before = correlation(a, b, roi_mask)
            mat = np.eye(2, 3, dtype=np.float32)
            accepted = False
            after = before
            dx = dy = 0.0
            try:
                cc, mat = cv2.findTransformECC(
                    a, b, mat, cv2.MOTION_TRANSLATION,
                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, .0001),
                    roi_mask.astype('uint8') * 255, 5)
                corrected = cv2.warpAffine(b, mat, (a.shape[1], a.shape[0]),
                                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                          borderMode=cv2.BORDER_REFLECT)
                inner = cv2.erode(roi_mask.astype('uint8'), np.ones((15, 15), np.uint8)) > 0
                after = correlation(a, corrected, inner)
                base_inner = correlation(a, b, inner)
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
    for region in regions:
        x0, y0, x1, y1 = region['bbox']
        inner = cv2.erode(mask[y0:y1, x0:x1].astype('uint8'), np.ones((15, 15), np.uint8)) > 0
        before = correlation(ref[y0:y1, x0:x1], aligned[y0:y1, x0:x1], inner)
        after = correlation(ref[y0:y1, x0:x1], corrected[y0:y1, x0:x1], inner)
        region['before'] = round(before, 4)
        region['after'] = round(after, 4)
        region['reliable'] = bool(after >= .82 and after >= before - .01)
    return corrected, flow, regions


def proposals(ref, target, mask, threshold):
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


def prioritize(candidate):
    """Conservative heuristic ranking, never deletes proposals; not a screw classifier."""
    c = candidate
    reasons = []
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
    result[:, 0] = np.clip(result[:, 0], 0, w-1)
    result[:, 1] = np.clip(result[:, 1], 0, h-1)
    return result


def detect(reference, target, name, threshold=.13):
    if not np.isfinite(threshold) or not .03 <= threshold <= .4:
        raise ValueError('門檻需介於 0.03 與 0.40')
    ref, raw = read(reference), read(target)
    r = cv2.resize(ref, None, fx=1536/max(ref.shape), fy=1536/max(ref.shape))
    reg = register(r, raw)
    mask = machine_mask(r) & reg['valid']
    total = max(int(machine_mask(r).sum()), 1)
    coverage = int(mask.sum()) / total
    if coverage < .95:
        raise ValueError('待測影像未完整覆蓋正常參考機體，需重新拍攝／人工確認')
    baseline, _ = proposals(r, reg['aligned'], mask, threshold)
    corrected, flow, regions = refine(r, reg['aligned'], mask)
    candidates, residual = proposals(r, corrected, mask, threshold)
    for c in candidates:
        c['reasons'] = prioritize(c)
        c['priority'] = 'review' if c['reasons'] else 'high'
    candidates.sort(key=lambda c: (c['priority'] != 'high', -c['score']))
    for i, c in enumerate(candidates, 1):
        c['id'] = i
        x, y, w, h = [c[k] for k in ('x', 'y', 'w', 'h')]
        points = source_points([[x-5, y-5], [x+w+5, y-5],
                                [x+w+5, y+h+5], [x-5, y+h+5]], reg, flow, raw.shape)
        c['source_polygon'] = np.round(points, 2).tolist()
        x0, y0 = np.floor(points.min(axis=0)).astype(int)
        x1, y1 = np.ceil(points.max(axis=0)).astype(int)
        c['source_bbox'] = [int(x0), int(y0), int(x1), int(y1)]
    out = ROOT/'outputs'/name
    out.mkdir(parents=True, exist_ok=True)
    ys, xs = np.where(mask)
    machine_points = source_points([[xs.min(), ys.min()], [xs.max(), ys.min()],
                                    [xs.max(), ys.max()], [xs.min(), ys.max()]], reg, flow, raw.shape)
    machine_box = [max(0, int(machine_points[:, 0].min())-35),
                   max(0, int(machine_points[:, 1].min())-35),
                   min(raw.shape[1], int(machine_points[:, 0].max())+35),
                   min(raw.shape[0], int(machine_points[:, 1].max())+35)]
    for i, c in enumerate(baseline, 1):
        c['id'] = i
        x, y, w, h = [c[k] for k in ('x', 'y', 'w', 'h')]
        p = source_points([[x-25, y-25], [x+w+25, y-25],
                           [x+w+25, y+h+25], [x-25, y+h+25]], reg, np.zeros_like(flow), raw.shape)
        b0 = np.floor(p.min(axis=0)).astype(int)
        b1 = np.ceil(p.max(axis=0)).astype(int)+1
        crop = raw[b0[1]:b1[1], b0[0]:b1[0]]
        cv2.imwrite(str(out/f'baseline_crop_{i}.png'), (crop*255).astype('uint8'))
        cv2.imwrite(str(out/f'baseline_ref_{i}.png'),
                    (r[max(0,y-25):y+h+25, max(0,x-25):x+w+25]*255).astype('uint8'))
        matches = [z['id'] for z in candidates if
                   min(x+w+8, z['x']+z['w']) > max(x-8, z['x']) and
                   min(y+h+8, z['y']+z['h']) > max(y-8, z['y'])]
        c['v2_nearby_ids'] = matches
        c['audit'] = '鄰近仍有第二版候選，請逐圖確認' if matches else '局部對齊後未達候選門檻；不代表正常'
    source_preview = cv2.cvtColor((raw*255).astype('uint8'), cv2.COLOR_GRAY2BGR)
    # Save natural-orientation preview at <=1536px; source coordinates remain native pixels.
    preview_scale = 1536/max(raw.shape)
    source_preview = cv2.resize(source_preview, None, fx=preview_scale, fy=preview_scale)
    high = source_preview.copy()
    all_overlay = source_preview.copy()
    for c in candidates:
        i = c['id']
        points = np.rint(np.asarray(c['source_polygon'])*preview_scale).astype('int32')
        color = (60, 65, 245) if c['priority'] == 'high' else (0, 185, 245)
        for canvas in ([high, all_overlay] if c['priority'] == 'high' else [all_overlay]):
            cv2.polylines(canvas, [points], True, color, 2)
            cv2.putText(canvas, str(i), tuple(points.min(axis=0)-[0, 6]),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
        x0, y0, x1, y1 = c['source_bbox']
        pad = max(45, (x1-x0)//2, (y1-y0)//2)
        box = [max(0, x0-pad), max(0, y0-pad), min(raw.shape[1], x1+pad), min(raw.shape[0], y1+pad)]
        c['crop_box'] = list(map(int, box))
        crop = (raw[box[1]:box[3], box[0]:box[2]]*255).astype('uint8')
        cv2.imwrite(str(out/f'crop_{i}.png'), crop)
        x, y, w, h = [c[k] for k in ('x', 'y', 'w', 'h')]
        patch = (r[max(0,y-25):y+h+25, max(0,x-25):x+w+25]*255).astype('uint8')
        cv2.imwrite(str(out/f'reference_crop_{i}.png'), patch)
    cv2.imwrite(str(out/'source.png'), source_preview)
    cv2.imwrite(str(out/'overlay.png'), high)
    cv2.imwrite(str(out/'all_overlay.png'), all_overlay)
    for key, arr in [('aligned', corrected), ('reference', r)]:
        cv2.imwrite(str(out/f'{key}.png'), (arr*255).astype('uint8'))
    heat = np.clip(residual/.3, 0, 1)
    heat[~mask] = 0
    cv2.imwrite(str(out/'difference.png'), cv2.applyColorMap((heat*255).astype('uint8'), cv2.COLORMAP_INFERNO))
    n_high = sum(c['priority'] == 'high' for c in candidates)
    result = dict(version=2, name=name, status='需人工複核',
                  rotation_ccw=reg['rotation']*90, inliers=reg['inliers'], threshold=threshold,
                  source_shape=list(raw.shape), source_machine_bbox=machine_box, preview_scale=preview_scale,
                  coordinate_frame='x/y/w/h: reference preview; source_bbox/polygon: original target pixels',
                  matrix=reg['matrix'].tolist(), local_alignment=regions,
                  alignment_warning=any(not z['reliable'] for z in regions),
                  coverage=round(coverage, 4), baseline_candidates=baseline,
                  baseline_count=len(baseline), proposal_count=len(candidates),
                  high_count=n_high, review_count=len(candidates)-n_high, candidates=candidates,
                  warning='紅框為規則優先候選，不是 AI 確認螺絲；黃色候選仍需查看。無紅框不代表正常。')
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    for name in ['ok_0', 'ng_5', 'ng_9']:
        result = detect(ROOT/'data/ok_0.png', ROOT/f'data/{name}.png', name+'_v2')
        print(name, 'baseline', result['baseline_count'], 'proposals', result['proposal_count'],
              'high', result['high_count'], 'review', result['review_count'])
