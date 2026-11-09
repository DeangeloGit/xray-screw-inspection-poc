"""Read-only CPU candidate-stage diagnosis; saved PNG geometry is counterfactual.

No model session, classification, registration search, settings changes, or run
output writes. Output is a separate audit JSON/PNG, never a detection result.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    destination = out / 'audit/candidate-diagnostics.json'
    preview_path = out / 'audit/candidate-diagnostics-D-all-photos.png'
    if destination.exists() or preview_path.exists():
        raise ValueError('Diagnostic outputs already exist')
    os.environ['XRAY_WORKSPACE'] = str(out / 'audit/candidate-diagnostics-runtime')
    os.environ['XRAY_CONFIG'] = str(out / 'audit/candidate-diagnostics-runtime/absent-config.json')
    os.environ['XRAY_OVERKILL_PILOT'] = '0'
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'experiments/dino'))
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw
    import detector
    import overkill_pilot
    import improvement_policy
    import visible_screw_geometry_v2 as visible
    cv2.setNumThreads(1)
    cv2.setRNGSeed(7)
    plan = read(out / 'plan.json')
    answers = read(out / 'answers.json')
    threshold = plan['threshold']
    source_hashes = {str(out / name): sha(out / name) for name in ('plan.json', 'answers.json')}
    golden_path = Path(plan['reference'])
    source_hashes[str(golden_path)] = sha(golden_path)
    full_ref = detector.read(golden_path)
    exact_ref = cv2.resize(full_ref, None, fx=1536 / max(full_ref.shape), fy=1536 / max(full_ref.shape))
    machine = detector.machine_mask(exact_ref)
    structure = detector.structure_mask(exact_ref)

    def transform(points, result, flow):
        p = np.asarray(points, np.float32).copy()
        hh, ww = result['source_shape']
        if result['mirrored_input']:
            p[:, 0] = ww - 1 - p[:, 0]
        x, y = p[:, 0].copy(), p[:, 1].copy()
        turn = result['rotation_ccw'] // 90
        p = (p if turn == 0 else np.column_stack((y, ww - 1 - x)) if turn == 1
             else np.column_stack((ww - 1 - x, hh - 1 - y)) if turn == 2
             else np.column_stack((hh - 1 - y, x)))
        p = (p + .5) * result['preview_scale'] - .5
        global_points = cv2.transform(p[None], np.asarray(result['matrix']))[0]
        p = global_points.copy()
        for _ in range(12):
            xx = np.clip(np.rint(p[:, 0]).astype(int), 0, flow.shape[1] - 1)
            yy = np.clip(np.rint(p[:, 1]).astype(int), 0, flow.shape[0] - 1)
            p = global_points - flow[yy, xx]
        return p

    def polygon_mask(points):
        mask = np.zeros(machine.shape, np.uint8)
        cv2.fillPoly(mask, [np.rint(points).astype('int32')], 1)
        return mask.astype(bool)

    def nearby(c, region):
        x, y, w, h = (int(c[k]) for k in ('x', 'y', 'w', 'h'))
        return bool(region[max(0, y):y+h, max(0, x):x+w].any())

    def candidate_trace(component, ref, target, predicted, residual, normal_nearby):
        x, y, w, h, area, pixels = component
        info = dict(box=[x, y, w, h], area=area)
        if not (12 <= area <= 1800 and 4 <= max(w, h) <= 110):
            info['first_rejection'] = 'area_or_size: require 12<=area<=1800 and 4<=max_side<=110'
            return info
        py, px = np.where(pixels)
        _, (a, b), _ = cv2.minAreaRect(np.column_stack([px, py]).astype('float32'))
        aspect = (max(a, b) + 1) / (min(a, b) + 1)
        score = float(np.percentile(residual[y:y+h, x:x+w][pixels], 90))
        diff = (predicted - target)[max(0, y-5):min(ref.shape[0], y+h+5),
                                    max(0, x-5):min(ref.shape[1], x+w+5)]
        bipolar = float(np.maximum(-diff, 0).sum()) / max(float(np.maximum(diff, 0).sum()), 1e-6)
        support = float(np.mean((normal_nearby[y:y+h, x:x+w] <= target[y:y+h, x:x+w] + .06)[pixels]))
        similarity = detector.matching_structure(ref, target, x, y, w, h)
        contrast = float(np.median((predicted - target)[y:y+h, x:x+w][pixels]))
        candidate = dict(x=x, y=y, w=w, h=h, area=area, shape_similarity=round(similarity, 3),
                         score=round(score, 4), normal_support=round(support, 3),
                         aspect=round(float(aspect), 2), fill=round(area / (w*h), 3),
                         bipolar=round(bipolar, 3), contrast=round(contrast, 4))
        info.update(score_p90=score, shape_similarity=similarity, normal_support=support,
                    bipolar=bipolar, aspect=float(aspect), fill=area/(w*h), candidate=candidate)
        info['tight_recovery_gates'] = dict(area_25_to_600=25 <= area <= 600,
            max_side_at_most_50=max(w, h) <= 50, aspect_at_most_4=candidate['aspect'] <= 4,
            fill_at_least_point25=candidate['fill'] >= .25,
            score_at_least_threshold_plus_point05=candidate['score'] >= threshold + .05,
            bipolar_at_most_point5=candidate['bipolar'] <= .5,
            similarity_at_most_point55=candidate['shape_similarity'] <= .55)
        if area < 40 and (similarity > .55 or support > .5):
            info['first_rejection'] = 'small_near_normal: area<40 and (shape_similarity>.55 or normal_support>.5)'
            return info
        if similarity >= .85:
            recovery = overkill_pilot.similarity_recovery(ref, target, candidate, threshold,
                                                        detector.structure_change_evidence)
            info.update(r3_first_rejection='shape_similarity>=.85', pilot_similarity_recovery=recovery)
            if not recovery:
                info['first_rejection'] = 'shape_similarity>=.85; pilot recovery unsupported'
                return info
        checked, explained = detector.check_candidate(ref, target, copy.deepcopy(candidate), threshold)
        info.update(check_candidate_explained=explained,
                    structure_change_evidence=checked.get('change_evidence'),
                    single_reference_evidence=checked.get('single_reference_evidence'),
                    first_rejection='check_candidate_explained' if explained else None,
                    passes_candidate_core_and_structure_check=not explained)
        return info

    def stages(ref, target, predicted, residual, allowed, region_masks):
        raw = (residual > threshold) & allowed
        opened = cv2.morphologyEx(raw.astype('uint8'), cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        before_split = opened.copy()
        _, labels, stats, _ = cv2.connectedComponentsWithStats(opened)
        for ident, (x, y, w, h, area) in enumerate(stats[1:], 1):
            if area > 1800 or max(w, h) > 110:
                local = (labels[y:y+h, x:x+w] == ident).astype('uint8')
                separated = cv2.morphologyEx(local, cv2.MORPH_OPEN,
                                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
                opened[y:y+h, x:x+w][local > 0] = separated[local > 0]
        _, labels, stats, _ = cv2.connectedComponentsWithStats(opened)
        normal_nearby = cv2.erode(predicted, np.ones((15, 15), np.uint8))
        output = {}
        for key, region in region_masks.items():
            relevant = set(map(int, np.unique(labels[region]))) - {0}
            traces = []
            for ident in relevant:
                x, y, w, h, area = map(int, stats[ident])
                pixels = labels[y:y+h, x:x+w] == ident
                trace = candidate_trace((x, y, w, h, area, pixels), ref, target, predicted,
                                        residual, normal_nearby)
                trace['pixels_inside_answer_region'] = int((pixels & region[y:y+h, x:x+w]).sum())
                traces.append(trace)
            output[key] = dict(raw_above_threshold_pixels=int(raw[region].sum()),
                after_open_pixels=int(before_split[region].sum()), after_large_component_split_pixels=int(opened[region].sum()),
                components=sorted(traces, key=lambda z: -z['pixels_inside_answer_region']))
        return output

    rows = []
    gallery = []
    for row in plan['items']:
        if row['is_reference']:
            continue
        key = row['key']
        folder = out / 'runs/r3' / key
        for name in ('result.json', 'reference.png', 'aligned.png'):
            source_hashes[str(folder/name)] = sha(folder/name)
        result = read(folder / 'result.json')
        ref, target = [np.asarray(Image.open(folder/(n+'.png')).convert('L'), np.float32)/255
                       for n in ('reference', 'aligned')]
        assert np.array_equal((exact_ref*255).astype('uint8'), (ref*255).round().astype('uint8'))
        flow = np.zeros((*ref.shape, 2), np.float32)
        for z in result['local_alignment']:
            x, y, X, Y = z['bbox']
            flow[y:Y, x:X] = [z['dx'], z['dy']]
        flow = cv2.GaussianBlur(flow, (0, 0), 12)
        mapped = []
        for mark in answers[key]['marks']:
            polygon = transform(mark['polygon'], result, flow)
            center = transform([mark['center']], result, flow)[0]
            mapped.append(dict(mark=mark, polygon=polygon, center=center))
        d = min(mapped, key=lambda z: np.linalg.norm(z['center'] - np.array([587.7089, 608.5934])))
        distance = float(np.linalg.norm(d['center'] - np.array([587.7089, 608.5934])))
        assert distance < 60, (key, distance)
        selected = mapped if key == 'ng-2271' else [d]
        regions = {str(z['mark']['id']): polygon_mask(z['polygon']) for z in selected}
        hh, ww = result['source_shape']
        resized_shape = (round(ww*result['preview_scale']), round(hh*result['preview_scale']))
        if (result['rotation_ccw']//90) % 2:
            resized_shape = resized_shape[::-1]
        valid = cv2.warpAffine(np.ones((resized_shape[1], resized_shape[0]), np.uint8),
                               np.asarray(result['matrix']), (ref.shape[1], ref.shape[0])) > 0
        mask = machine & valid
        predicted = detector.compensate_brightness(ref, target)
        channels = {}
        for kernel in (7, 3):
            residual = cv2.erode(predicted, np.ones((kernel, kernel), np.uint8)) - target
            channels[str(kernel)] = dict(
                actual_mask=stages(ref, target, predicted, residual, mask, regions),
                counterfactual_valid_only=stages(ref, target, predicted, residual, valid, regions),
                extrema={m: dict(peak=float(residual[r].max()), p95=float(np.percentile(residual[r], 95)))
                         for m, r in regions.items()})
        region_records = []
        for z in selected:
            ident = str(z['mark']['id'])
            region = regions[ident]
            center = z['center']
            cx, cy = np.rint(center).astype(int)
            positive = ((ref - target) > threshold) & region
            cands = result['candidates'] + result['filtered_candidates']
            record = dict(answer_id=z['mark']['id'], is_D=z is d,
                aligned_center=center.tolist(), aligned_polygon=z['polygon'].tolist(),
                region_pixels=int(region.sum()), machine_mask_pixels=int((region & machine).sum()),
                machine_mask_share=float(machine[region].mean()), valid_share=float(valid[region].mean()),
                center_in_machine=bool(machine[cy, cx]), center_in_structure=bool(structure[cy, cx]),
                raw_reference_minus_target_peak=float((ref-target)[region].max()),
                raw_added_pixels=int(positive.sum()), raw_added_pixels_inside_mask=int((positive & mask).sum()),
                actual_r3_candidates=[dict(id=c['id'], box=[c[k] for k in ('x','y','w','h')]) for c in cands if nearby(c, region)],
                actual_r3_structure_changes=[c for c in result['structure_changes'] if nearby(c, region)])
            if key == 'ng-2271':
                supplement = improvement_policy.supplemental(ref, target, mask, predicted, cands)
                parts = visible.proposals(ref, target)
                record['diagnostic_joined_fragment_candidates'] = [c for c in supplement if nearby(c, region)]
                record['diagnostic_visible_part_candidates'] = [{k:v for k,v in c.items() if k!='mask'} for c in parts
                    if nearby(dict(zip(('x','y','w','h'), c['box'])), region)]
            complete = out / 'runs/4r' / key / 'complete.json'
            if complete.is_file():
                current_path = complete.parent / 'result.json'
                current = read(current_path)
                source_hashes[str(current_path)] = sha(current_path)
                assert current['matrix'] == result['matrix'] and current['local_alignment'] == result['local_alignment']
                assert sha(complete.parent/'aligned.png') == sha(folder/'aligned.png')
                record['actual_4r_candidates'] = [dict(id=c['id'], box=[c[k] for k in ('x','y','w','h')])
                    for c in current['candidates']+current['filtered_candidates'] if nearby(c, region)]
                record['actual_4r_structure_changes'] = [c for c in current['structure_changes'] if nearby(c, region)]
            region_records.append(record)
        rows.append(dict(photo=key, D_answer_id=d['mark']['id'], D_center_distance=distance,
                         regions=region_records, stages=channels))
        cx, cy = np.rint(d['center']).astype(int)
        sl = (slice(cy-40, cy+41), slice(cx-40, cx+41))
        rgb = np.repeat((target[sl]*255).astype('uint8')[:,:,None], 3, axis=2)
        rgb[~mask[sl]] = (rgb[~mask[sl]]*.55 + np.array([110, 0, 0])).clip(0,255)
        img = Image.fromarray(rgb).resize((243, 243))
        draw = ImageDraw.Draw(img)
        poly = [(float((x-cx+40)*3), float((y-cy+40)*3)) for x,y in d['polygon']]
        draw.line(poly+[poly[0]], fill='#00baff', width=2)
        gallery.append((key, img))
        print(key, 'D answer', d['mark']['id'], 'mask', round(float(machine[regions[str(d['mark']['id'])]].mean()), 4), flush=True)
    # The answer file may be corrected independently while diagnostics run.
    # Its starting hash identifies the exact annotation snapshot used here.
    immutable = {p:h for p,h in source_hashes.items() if p != str(out/'answers.json')}
    assert all(sha(p) == h for p,h in immutable.items())
    result = dict(status='diagnostic_only', method='CPU geometry; cv2 threads=1; no DINO/ONNX/GPU',
        limitation='Candidate traces use saved uint8 reference/aligned PNG arrays, quantized from original float detection. Exact Golden normalization/resize reconstructs machine mask; saved matrix reconstructs global valid mask. Threshold-border component counts may differ from original float run. valid-only traces are counterfactual diagnostics, NOT official detections or accepted alerts.',
        threshold=threshold, source_hashes=source_hashes, protected_run_inputs_unchanged=True,
        answers_snapshot_unchanged_at_finish=sha(out/'answers.json')==source_hashes[str(out/'answers.json')],
        source_or_model_modified=False, photos=rows)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    sheet = Image.new('RGB', (5*253, 2*279), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, (key, img) in enumerate(gallery):
        x,y = (i%5)*253,(i//5)*279
        draw.text((x+4,y+3), key+' D | red=outside mask', fill='black')
        sheet.paste(img, (x+4,y+24))
    sheet.save(preview_path)
    print('SAVED', destination, flush=True)


if __name__ == '__main__':
    main()
