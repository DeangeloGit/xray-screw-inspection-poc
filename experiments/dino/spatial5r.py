"""Additive enclosure inspection and evidence-backed fragment review for 5r.

No filename, label, answer coordinate or newly trained feature enters decisions.
The completed original pipeline is the immutable starting point.
"""
import copy
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

VERSION = '5r-enclosure-parent-review-20261120'


def enclosure_mask(reference, original):
    """Find the faint enclosure connected to the main body, within a bounded band.

    A dilated mask only limits the search; it is not the inspection envelope.
    The envelope itself must have image support in the normal reference.
    """
    ys, xs = np.where(original)
    if not len(xs):
        raise ValueError('Cannot extend an empty machine mask')
    radius = max(8, int(round(max(np.ptp(xs), np.ptp(ys)) * .032)))
    limit = cv2.dilate(original.astype('uint8'), np.ones((radius*2+1, radius*2+1), np.uint8))
    binary = ((reference < .94) & (limit > 0)).astype('uint8')
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    _, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    if len(stats) < 2:
        return original.copy()
    # Select by overlap with the original body, not by an external cable's size.
    support = np.bincount(labels[original], minlength=len(stats))
    support[0] = 0
    component = (labels == int(np.argmax(support))).astype('uint8')
    contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    envelope = np.zeros_like(component)
    cv2.fillConvexPoly(envelope, cv2.convexHull(max(contours, key=cv2.contourArea)), 1)
    return original | ((envelope > 0) & (limit > 0))


def overlap(a, b):
    x, y, w, h = a
    X, Y, W, H = b
    intersection = max(0, min(x+w, X+W)-max(x, X))*max(0, min(y+h, Y+H)-max(y, Y))
    return intersection / max(1, min(w*h, W*H)), intersection / max(1, w*h+W*H-intersection)


def stable_core(shapes):
    """A compact component covering the query at two intensity levels protects it."""
    supported = [g for g in shapes if g.get('coverage', 0) >= .5]
    for i, a in enumerate(supported):
        for b in supported[i+1:]:
            if a['cutoff'] != b['cutoff'] and overlap(a['box'], b['box'])[1] >= .6:
                return [a, b]
    return []


def review_fragment(snapshot, reference, target, candidate):
    from correspondence_geometry import contours, template_matches
    from dino_paired_optimized import classify_candidate
    old = candidate['classification']
    if old.get('filter_recommendation') != 'keep':
        return old
    x, y, w, h = (int(candidate[k]) for k in ('x', 'y', 'w', 'h'))
    if max(w, h) > 16 or candidate.get('recovery') == '5r_enclosure':
        return old
    shapes = contours(target, candidate)
    protected = stable_core(shapes)
    evidence = dict(version=VERSION, query=[x, y, w, h], stable_core=protected, accepted=False)
    if protected:
        return dict(old, spatial_review5r=evidence)
    parents = shapes + old.get('r4_experiment', {}).get('geometry', [])
    eligible = []
    for parent in parents:
        a, b, c, d = parent['box']
        if overlap([x, y, w, h], parent['box'])[0] < .25:
            continue
        X, Y = max(x+w, a+c), max(y+h, b+d)
        a, b = min(x, a), min(y, b)
        extent = [a, b, X-a, Y-b]
        if extent[2]*extent[3] >= 3*w*h and max(extent[2:]) <= 96:
            eligible.append(extent)
    if not eligible:
        return dict(old, spatial_review5r=evidence)
    extent = max(eligible, key=lambda b: b[2]*b[3])
    query = dict(zip(('x', 'y', 'w', 'h'), extent))
    matches = template_matches(reference, target, query)
    evidence.update(parent_box=extent, matches=matches)
    # Wider context must support the same nearby existing structure. Small-view
    # matching alone can lock onto a screw-shaped fragment or a repeated wire.
    consistent = (len(matches) == 3 and matches[1]['score'] >= .65
                  and matches[2]['score'] >= .75
                  and abs(matches[1]['dx']-matches[2]['dx']) <= 8
                  and abs(matches[1]['dy']-matches[2]['dy']) <= 2
                  and max(abs(matches[2][k]) for k in ('dx', 'dy')) <= 12)
    if not consistent:
        return dict(old, spatial_review5r=evidence)
    checked = classify_candidate(snapshot, target, reference, query)
    evidence['parent_prediction'] = checked
    # Both complete-object views must say non-screw. Ambiguity keeps the alarm;
    # no global score threshold or original paired decision is relaxed.
    if not all(checked['paired_evidence'][side]['label'] == 'non_screw'
               for side in ('reference', 'target')):
        return dict(old, spatial_review5r=evidence)
    evidence.update(accepted=True, previous=copy.deepcopy(old))
    return dict(checked, status='active', model_id=snapshot.manifest['model_id'],
                action='discard', spatial_review5r=evidence,
                canonical_object=dict(old.get('canonical_object', {}), box=extent,
                                      previous_box=[x, y, w, h], version=VERSION),
                decision_reason='5r 完整物件複核：小片段沒有跨明暗層穩定的獨立核心；周圍結構與參照相符，完整物件雙圖皆不像螺絲，排除。')


def apply(snapshot, bundle, result, directory, reference_path, target_path,
          review_bank, normal_bank, *, fragments=True):
    import detector
    import example_audit_policy as policy
    import integrated_bank_policy as integrated
    import connector_policy as terminal
    import visible_screw_policy_v3 as visible
    from alarm_review5r import review_alarm

    directory = Path(directory)
    original = copy.deepcopy(result)
    updated = copy.deepcopy(result)
    reference_full = detector.read(reference_path)
    reference = cv2.resize(reference_full, None, fx=1536/max(reference_full.shape), fy=1536/max(reference_full.shape))
    target = np.asarray(Image.open(directory/'aligned.png').convert('L'), np.float32)/255
    qr = np.asarray(Image.open(directory/'reference.png').convert('L'), np.float32)/255
    raw = detector.read(target_path)
    scale = 1536/max(raw.shape)
    rotated = np.rot90(raw, result['rotation_ccw']//90)
    if result.get('mirrored_input'):
        rotated = np.rot90(np.fliplr(raw), result['rotation_ccw']//90)
    small = cv2.resize(rotated, None, fx=scale, fy=scale)
    matrix = np.asarray(result['matrix'], np.float64)
    valid = cv2.warpAffine(np.ones(small.shape, np.uint8), matrix, (reference.shape[1], reference.shape[0])) > 0
    machine = detector.machine_mask(reference)
    envelope = enclosure_mask(reference, machine) & valid
    machine &= valid
    # Save both scopes: coverage of the old deep-structure hull is not coverage
    # of the bright enclosure. These files are diagnostic, never new inputs.
    detector.write_image(str(directory/'inspection_original.png'), machine.astype('uint8')*255)
    detector.write_image(str(directory/'inspection_enclosure.png'), envelope.astype('uint8')*255)
    proposed, _ = detector.proposals(reference, target, envelope, result['threshold'])
    all_old = sorted(original['candidates']+original['filtered_candidates'], key=lambda c: c['id'])
    extras = []
    for c in proposed:
        x, y, w, h = (c[k] for k in ('x', 'y', 'w', 'h'))
        outside = float(np.mean(~machine[y:y+h, x:x+w]))
        if outside < .5 or any(overlap([x,y,w,h], [z[k] for k in ('x','y','w','h')])[0] > .25 for z in all_old):
            continue
        extras.append(dict(c, recovery='5r_enclosure', original_mask_outside_fraction=outside))
    flow = np.zeros((*reference.shape, 2), np.float32)
    for region in result['local_alignment']:
        x,y,X,Y = region['bbox']
        flow[y:Y,x:X] = [region['dx'], region['dy']]
    flow = cv2.GaussianBlur(flow, (0,0), 12)
    reg = dict(matrix=matrix, rotation=result['rotation_ccw']//90, target_scale=scale,
               mirrored=result.get('mirrored_input', False))
    max_id = max((c['id'] for c in all_old), default=0)
    trial = bundle.trial_snapshot(snapshot)
    for i, c in enumerate(extras, max_id+1):
        c['id'] = i
        c['reasons'] = detector.prioritize(c)
        c['priority'] = 'review' if c['reasons'] else 'high'
        x,y,w,h = (c[k] for k in ('x','y','w','h'))
        points = detector.source_points([[x-5,y-5],[x+w+5,y-5],[x+w+5,y+h+5],[x-5,y+h+5]],reg,flow,raw.shape)
        c['source_polygon'] = np.round(points,2).tolist()
        a,b = np.floor(points.min(axis=0)).astype(int)
        X,Y = np.ceil(points.max(axis=0)).astype(int)
        c['source_bbox'] = list(map(int,[a,b,X,Y]))
        pad = max(45, (X-a)//2, (Y-b)//2)
        box = [max(0,a-pad),max(0,b-pad),min(raw.shape[1],X+pad),min(raw.shape[0],Y+pad)]
        c['crop_box'] = list(map(int,box))
        detector.write_image(str(directory/f'crop_{i}.png'), (raw[box[1]:box[3],box[0]:box[2]]*255).astype('uint8'))
        detector.write_image(str(directory/f'reference_crop_{i}.png'), (qr[max(0,y-25):y+h+25,max(0,x-25):x+w+25]*255).astype('uint8'))
        objects = policy.Objects(qr,target,all_old+extras)
        pred = integrated.classify(snapshot,qr,target,c,objects)
        pred,_ = terminal.apply(snapshot,qr,target,pred,review_bank,normal_bank)
        prior = visible.BANK, visible.CONFIG, policy.BANK
        try:
            policy.configure(bundle.parts,prior[1],review_bank)
            pred = review_alarm(trial,qr,target,pred,c,all_old+extras,review_bank,normal_bank,core_snapshot=snapshot)
        finally:
            policy.configure(*prior)
        pred = dict(pred, action='manual_review' if pred['filter_recommendation']=='keep' else 'discard')
        c['classification'] = pred
    updated['candidates'], updated['filtered_candidates'] = [], []
    changes = []
    for c in all_old+extras:
        pred = review_fragment(snapshot,qr,target,c) if fragments else c['classification']
        if pred['filter_recommendation'] != c['classification']['filter_recommendation']:
            changes.append(c['id'])
        updated['candidates' if pred['filter_recommendation']=='keep' else 'filtered_candidates'].append(dict(c,classification=pred))
    updated['pre_ai_count'] = len(all_old)+len(extras)
    updated['proposal_count'] = len(updated['candidates'])
    updated['filtered_count'] = len(updated['filtered_candidates'])
    updated['high_count'] = sum(c['priority']=='high' for c in updated['candidates'])
    updated['review_count'] = updated['proposal_count']-updated['high_count']
    updated['wire_review_count'] = sum(bool(c.get('wire_review')) for c in updated['candidates'])
    encoded = json.dumps(original,ensure_ascii=False,sort_keys=True).encode('utf8')
    baseline = 'baseline-5r-'+hashlib.sha256(encoded).hexdigest()[:16]+'.json'
    (directory/baseline).write_bytes(encoded)
    updated['spatial5r'] = dict(version=VERSION, baseline_file=baseline, added=len(extras),
                               fragment_removed=changes, fragments_enabled=fragments,
                               original_pixels=int(machine.sum()),enclosure_pixels=int(envelope.sum()),
                               policy_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    source = cv2.imdecode(np.fromfile(directory/'source.png',np.uint8),cv2.IMREAD_COLOR)
    high, all_overlay = source.copy(), source.copy()
    for c in updated['candidates']:
        points = np.rint(np.asarray(c['source_polygon'])*result['preview_scale']).astype('int32')
        color = (60,65,245) if c['priority']=='high' else (0,185,245)
        for canvas in ([high,all_overlay] if c['priority']=='high' else [all_overlay]):
            cv2.polylines(canvas,[points],True,color,2)
            cv2.putText(canvas,str(c['id']),tuple(points.min(axis=0)-[0,6]),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
    detector.write_image(str(directory/'overlay.png'),high)
    detector.write_image(str(directory/'all_overlay.png'),all_overlay)
    return updated
