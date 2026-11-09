"""Complete report for a new machine evaluated by two independently run pipelines.

This module only reads detections and annotations. It does not infer, tune a
model, manufacture normal labels, or require a favourable comparison to pass
the report integrity checks.
"""
import argparse
from collections import Counter
import copy
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote, unquote, urlsplit

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import answered_batch_report as common
from result_columns import columns

ROOT = Path(__file__).resolve().parents[2]
TYPES = common.TYPES
METHOD_NAMES = {'r3': '原 r3：47 螺絲＋65 正常、雙圖',
                '4r': '固定 4r：curated_v5_review'}
read, save, sha, esc, table = common.read, common.save, common.sha, common.esc, common.table
STYLE = common.STYLE + '\npre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}.metrics{font-size:1.15em}.answer-hit{color:#176b46}.answer-miss{color:#a33d1f}'


def safe_key(value):
    value = str(value)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
        raise ValueError('Report keys must be safe ASCII identifiers: ' + value)
    return value


def flow_for(result, shape):
    flow = np.zeros((*shape, 2), np.float32)
    for region in result['local_alignment']:
        x, y, X, Y = region['bbox']
        flow[y:Y, x:X] = [region['dx'], region['dy']]
    return cv2.GaussianBlur(flow, (0, 0), 12)


def matching(poly, marks):
    """Use the established central-overlap rule, but expose ambiguous matches.

The legacy helper asserts when one candidate encloses multiple answer centres.
For a new corpus that is a review condition, not permission to credit multiple
screws or select the answer most favourable to the evaluated model.
"""
    cp = common.hull(poly)
    center = tuple(float(v) for v in cp.mean(axis=0))
    yes, edge = [], []
    for mark in marks:
        ap = common.hull(mark['polygon'])
        ac = np.float32(mark['center'])
        inter, _ = cv2.intersectConvexConvex(ap, cp)
        if inter <= 0:
            continue
        inner = common.hull(ac + (ap - ac) * .8)
        central = (cv2.pointPolygonTest(inner, center, False) >= 0 or
                   cv2.pointPolygonTest(cp, tuple(float(v) for v in ac), False) >= 0)
        (yes if central else edge).append(mark['id'])
    return (yes, edge, []) if len(yes) <= 1 else ([], edge, yes)


def category_for(candidate, rules):
    mapping = [('wire', 'wire'), ('r4_wire_motion', 'wire'),
               ('border', 'edge'), ('corner', 'edge'),
               ('component', 'component'), ('r4_weak_object_extent', 'component'),
               ('u_shape', 'structure'), ('r4_u_structure', 'structure')]
    for rule, category in mapping:
        if rule in rules:
            return category
    if 'r4_part_boundary' in rules:
        return 'edge' if max(candidate['w'], candidate['h']) <= 9 else 'component'
    return 'unknown'


def compound_region(mark):
    flags = ('compound', 'multi_object_possible', 'multiple_objects_possible', 'possible_multiple_objects',
             'needs_object_count_review', 'requires_object_count_review')
    return (any(mark.get(key) is True for key in flags) or
            mark.get('annotation_kind', mark.get('kind')) in
            ('compound_region', 'multi_object_region', 'possible_multiple_objects'))


def position_consistency(marks, rows, methods):
    """Group answer positions only, before considering prediction outcomes.

    A fixed 1/15 of image width/height is used in normalized source coordinates.
    Neighbouring answer rings in one photograph may belong to one location;
    coverage is therefore reported as X/Y regions for each photograph.
    """
    photos = {row['key']:row for row in rows}
    groups = []
    for mark in sorted(marks, key=lambda m:(m['center'][1], m['center'][0], m['photo'], m['id'])):
        height, width = photos[mark['photo']]['source_shape'][:2]
        center = np.asarray(mark['center'], dtype=float)/[width, height]
        choices = [(float(np.linalg.norm(center-np.mean(g['centers'], axis=0))), i)
                   for i, g in enumerate(groups)]
        near = min(choices, default=(float('inf'), None))
        if near[0] > 1/15:
            groups.append(dict(centers=[], marks=[])); index = len(groups)-1
        else:
            index = near[1]
        groups[index]['centers'].append(center)
        groups[index]['marks'].append(mark)
    result = []
    for number, group in enumerate(groups, 1):
        per_photo = []
        for photo in sorted({mark['photo'] for mark in group['marks']}):
            selected = [mark for mark in group['marks'] if mark['photo']==photo]
            metrics = {method:dict(covered_regions=sum(bool(m['methods'][method]) for m in selected),
                                   answer_regions=len(selected),
                                   pending_regions=sum(bool(m.get('ambiguous_methods',{}).get(method)) and not m['methods'][method] for m in selected),
                                   all_regions_covered=all(bool(m['methods'][method]) for m in selected))
                       for method in methods}
            per_photo.append(dict(photo=photo, answer_ids=[m['id'] for m in selected],
                                  compound_ids=[m['id'] for m in selected if compound_region(m)], methods=metrics))
        for mark in group['marks']:
            mark['position_group'] = number
        first = group['marks'][0]
        result.append(dict(id=number, normalized_source_center=np.mean(group['centers'],axis=0).tolist(),
                           threshold_fraction=1/15, method='Greedy nearest mean, answer coordinates only; no verdict-dependent threshold',
                           representative=dict(photo=first['photo'],answer_id=first['id']),
                           observations=len(group['marks']), photos=len(per_photo), per_photo=per_photo,
                           methods={method:dict(fully_covered_photos=sum(p['methods'][method]['all_regions_covered'] for p in per_photo),
                                                covered_regions=sum(p['methods'][method]['covered_regions'] for p in per_photo),
                                                answer_regions=sum(p['methods'][method]['answer_regions'] for p in per_photo)) for method in methods}))
    return result


def preview(source, destination, size=(1400, 1400)):
    with Image.open(source) as image:
        image = image.convert('RGB')
        image.thumbnail(size)
        image.save(destination, quality=90)


def actual_overlay(source, evaluated, destination):
    """Show retained canonical ranges in native target-image coordinates.

    Detector all_overlay.png intentionally preserves proposal polygons. Those
    polygons can differ from the object actually classified by 4r, so keep
    that original image for traceability and render this separate report view.
    Exact same polygons share a label listing their candidate IDs; no verdict,
    geometry or candidate count is changed by this display-only grouping.
    """
    with Image.open(source) as original:
        image = original.convert('RGB')
    native_width, native_height = image.size
    image.thumbnail((1400, 1400))
    sx, sy = image.width/native_width, image.height/native_height
    groups = {}
    for value in evaluated:
        if not value['keep']:
            continue
        polygon = np.asarray(value['source_polygon'], dtype=float)
        if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3 or not np.isfinite(polygon).all():
            raise ValueError('Invalid native canonical polygon for report overlay')
        key = tuple(tuple(point) for point in polygon.tolist())
        group = groups.setdefault(key, dict(polygon=polygon.tolist(), candidate_ids=[]))
        group['candidate_ids'].append(value['id'])
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=16)
    for group in groups.values():
        points = [(x*sx, y*sy) for x, y in group['polygon']]
        draw.line(points+[points[0]], fill='#00a5dd', width=3)
        label = ','.join(str(i) for i in group['candidate_ids'])
        bounds = draw.textbbox((0,0), label, font=font, stroke_width=1)
        label_width, label_height = bounds[2]-bounds[0], bounds[3]-bounds[1]
        left = max(0, min(min(x for x,y in points), image.width-label_width-2))
        top = max(0, min(min(y for x,y in points)-label_height-4, image.height-label_height-2))
        draw.text((left,top),label,font=font,fill='#007fae',stroke_width=1,stroke_fill='white')
    image.save(destination, quality=92)
    return dict(source_size=[native_width,native_height],display_size=list(image.size),
                coordinate_frame='native target pixels; canonical source polygons',
                kept_candidate_ids=[v['id'] for v in evaluated if v['keep']],
                displayed_ranges=list(groups.values()))


def padded_crop(image, window):
    left, top, right, bottom = window
    result = Image.new('RGB', (right-left, bottom-top), 'white')
    clipped = (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))
    if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
        result.paste(image.crop(clipped), (clipped[0]-left, clipped[1]-top))
    return result


def diagnostic_file(out, relative):
    """Resolve an optional diagnostic attachment inside this experiment only."""
    if not isinstance(relative, str) or not relative or ':' in relative:
        raise ValueError('Diagnostic attachments must be relative file paths')
    normalized = relative.replace('\\', '/')
    part = Path(normalized)
    if part.is_absolute() or '..' in part.parts:
        raise ValueError('Diagnostic attachment escapes experiment output: '+relative)
    path = (out/part).resolve()
    if not path.is_relative_to(out.resolve()) or not path.is_file():
        raise ValueError('Missing or external diagnostic attachment: '+relative)
    return path, '../'+quote(path.relative_to(out).as_posix(), safe='/')


def pair_image(ref, target, case, destination):
    x, y, width, height = case['box']
    pred = case['classification']
    dx, dy = pred.get('correspondence_experiment', {}).get('reference_offset', [0, 0])
    cx, cy, cw, ch = case['canonical_box']
    # Use a shared base window containing both actual evidence and the query.
    # The reference viewport is shifted by offset, so query-offset must also
    # fit this base window for its unchanged original red box to stay visible.
    xmin, ymin = min(x, cx, x-dx), min(y, cy, y-dy)
    xmax, ymax = max(x+width, cx+cw, x+width-dx), max(y+height, cy+ch, y+height-dy)
    span = math.ceil(max(120, xmax-xmin+48, ymax-ymin+48))
    left = math.floor((xmin+xmax-span)/2)
    top = math.floor((ymin+ymax-span)/2)
    canvas = Image.new('RGB', (800, 400), 'white')
    windows = {}
    for side, image, offx, offy, index in [('reference', ref, dx, dy, 0),
                                          ('target', target, 0, 0, 1)]:
        window = [int(round(left+offx)), int(round(top+offy)),
                  int(round(left+offx))+span, int(round(top+offy))+span]
        crop = padded_crop(image, window)
        draw = ImageDraw.Draw(crop)
        draw.rectangle((x-window[0], y-window[1], x+width-window[0], y+height-window[1]),
                       outline='#ed2346', width=1)
        # Reference correspondence is sampled at canonical_box + offset.
        draw.rectangle((cx+offx-window[0], cy+offy-window[1],
                        cx+cw+offx-window[0], cy+ch+offy-window[1]),
                       outline='#00a5dd', width=1)
        canvas.paste(crop.resize((400, 400)), (index*400, 0))
        windows[side] = window
    canvas.save(destination, quality=86)
    case['report_windows'] = windows
    case['report_padding'] = 'Only out-of-image display pixels are filled white; no detector input is modified.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    os.environ['XRAY_WORKSPACE'] = str(out/'report-runtime')
    os.environ['XRAY_CONFIG'] = str(out/'isolated-settings.json')
    sys.path.insert(0, str(ROOT))
    cv2.setNumThreads(4)
    plan = read(out/'plan.json')
    assert read(out/'run-complete.json')['complete'] is True
    methods = list(plan.get('methods', ['r3', '4r']))
    assert methods == ['r3', '4r'], methods
    machine = safe_key(plan['machine'])
    machine_title = machine + (' / SKU='+str(plan['sku']) if plan.get('sku') else '')
    assert all(item.get('machine', machine) == machine for item in plan['items']), 'Use one machine per report'
    assert len({item['key'] for item in plan['items']}) == len(plan['items'])
    answers = read(out/'answers.json')
    diagnostics_path = out/'diagnostics.json'
    diagnostics = read(diagnostics_path) if diagnostics_path.is_file() else None
    diagnostic_hashes = {str(diagnostics_path):sha(diagnostics_path)} if diagnostics is not None else {}
    report = out/'report'
    images = report/'images'
    images.mkdir(parents=True, exist_ok=True)
    nav = ('<nav><a href="index.html">完整結果</a>'
           f'<a href="machine-{machine}.html">{esc(machine_title)}</a>'
           '<a href="answers.html">全部答案</a>'
           '<a href="comparison.html">附加：版本比較</a>'+
           ('<a href="diagnosis.html">附加：漏抓原因</a>' if diagnostics is not None else '')+
           '<a href="provenance.html">資料與核對證據</a></nav>')
    pages = set()

    def page(name, title, body):
        text = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{esc(title)}</title><style>{STYLE}</style></head><body><main>'
                f'{nav}<h1>{esc(title)}</h1>{body}</main></body></html>')
        (report/name).write_text(text, encoding='utf-8')
        pages.add(name)

    allcases, rows, markrows, method_cases = [], [], [], {}
    result_hashes = {}
    for item in plan['items']:
        key = safe_key(item['key'])
        marks = answers.get(key, {}).get('marks', [])
        assert len({m['id'] for m in marks}) == len(marks), key
        isref = bool(item.get('is_reference', item.get('label') == 'REF'))
        label = 'REF' if isref else item.get('label', 'UNLABELED')
        has_answers = not isref and (bool(item.get('answer')) or bool(marks) or (key in answers and label=='OK'))
        metrics, current = {}, None
        for method in methods:
            folder = out/'runs'/method/key
            result = read(folder/'result.json')
            digest = sha(folder/'result.json')
            assert digest == read(folder/'complete.json')['result_sha256'], (method, key)
            result_hashes[str((folder/'result.json').relative_to(out))] = digest
            candidates = sorted(result['candidates']+result['filtered_candidates'], key=lambda c:c['id'])
            assert len({c['id'] for c in candidates}) == len(candidates)
            assert len(candidates) == result['pre_ai_count']
            assert len(result['candidates']) == result['proposal_count']
            assert len(result['filtered_candidates']) == result['filtered_count']
            with Image.open(folder/'reference.png') as im:
                ref = im.convert('RGB')
            flow = flow_for(result, (ref.height, ref.width))
            evaluated = []
            actual_keep_ids = {c['id'] for c in result['candidates']}
            for c in candidates:
                pred = c['classification']
                keep = pred['filter_recommendation'] == 'keep'
                assert keep == (c['id'] in actual_keep_ids), (method, key, c['id'])
                polygon = common.native(c, result, flow)
                matched, edge, ambiguous = matching(polygon, marks)
                proposal_polygon = common.native(dict(c,classification={}), result, flow)
                proposal_matched, proposal_edge, proposal_ambiguous = matching(proposal_polygon, marks)
                evaluated.append(dict(id=c['id'], keep=keep, answers=matched,
                                      edge_answers=edge, ambiguous_answers=ambiguous,
                                      source_polygon=polygon.tolist(),
                                      proposal_source_polygon=proposal_polygon.tolist(),
                                      proposal_answers=proposal_matched, proposal_edge_answers=proposal_edge,
                                      proposal_ambiguous_answers=proposal_ambiguous, candidate=c))
            method_cases[(method, key)] = evaluated
            hits = sorted({m for c in evaluated if c['keep'] for m in c['answers']})
            metrics[method] = dict(candidate_count=len(evaluated), kept=sum(c['keep'] for c in evaluated),
                                   excluded=sum(not c['keep'] for c in evaluated), answer_hits=hits,
                                   answer_total=len(marks),
                                   unmatched=sum(c['keep'] and not c['answers'] and not c['ambiguous_answers'] for c in evaluated) if has_answers else None,
                                   edge_only=sum(c['keep'] and bool(c['edge_answers']) and not c['answers'] and not c['ambiguous_answers'] for c in evaluated),
                                   ambiguous_candidates=sum(bool(c['ambiguous_answers']) for c in evaluated),
                                   ambiguous_kept=sum(c['keep'] and bool(c['ambiguous_answers']) for c in evaluated),
                                   alignment_warning=result['alignment_warning'])
            if method == '4r':
                with Image.open(folder/'aligned.png') as im:
                    target = im.convert('RGB')
                current = result
                actual_overlay_meta = actual_overlay(item['path'], evaluated, images/f'{key}-actual-overlay.jpg')
                for value in evaluated:
                    c = value['candidate']
                    pred = copy.deepcopy(c['classification'])
                    rules = pred.get('overkill_pilot', {}).get('rules', []) + pred.get('r4_experiment', {}).get('rules', [])
                    box = list(common.geom(c))
                    canonical = pred.get('canonical_object', {}).get('box', box)
                    case = {k:copy.deepcopy(v) for k, v in value.items() if k != 'candidate'}
                    case.update(key=f'{key}-{c["id"]}', photo=key, machine=machine, label=label,
                                is_reference=isref, box=box, canonical_box=canonical,
                                category=category_for(c, rules), rules=rules,
                                classification_source='規則自動推測' if category_for(c, rules) != 'unknown' else '待確認（未人工分類）',
                                paired_evidence=pred.get('paired_evidence', {}),
                                reason=pred.get('decision_reason', ''), classification=pred)
                    pair_image(ref, target, case, images/f'{case["key"]}.jpg')
                    allcases.append(case)
                for suffix, source in [('reference', folder/'reference.png'),
                                       ('overlay', folder/'all_overlay.png'), ('source', Path(item['path']))]:
                    preview(source, images/f'{key}-{suffix}.jpg')
        cc = [c for c in allcases if c['photo'] == key]
        row = dict(key=key, name=item.get('name', Path(item['path']).name), machine=machine,
                   label=label, is_reference=isref, path=item['path'], answer=item.get('answer'),
                   has_answers=has_answers, answer_count=len(marks), answers=len(marks),
                   candidates=len(cc), kept=metrics['4r']['kept'], excluded=metrics['4r']['excluded'],
                   hits=metrics['4r']['answer_hits'], baseline_hits=metrics['r3']['answer_hits'],
                   unmatched=metrics['4r']['unmatched'], metrics=metrics,
                   source_shape=current['source_shape'],
                   actual_overlay=actual_overlay_meta,
                   alignment_warning=current['alignment_warning'], structure_changes=current['structure_changes'])
        rows.append(row)
        if item.get('answer'):
            preview(item['answer'], images/f'{key}-supplied-answer.jpg')
        if marks:
            with Image.open(item['path']) as im:
                original = im.convert('RGB')
            annotated = original.copy()
            draw = ImageDraw.Draw(annotated)
            for mark in marks:
                pts = [tuple(p) for p in mark['polygon']]
                draw.line(pts+[pts[0]], fill='#ed2346', width=5)
                draw.text(tuple(mark['center']), str(mark['id']), fill='#ed2346', stroke_width=2)
                entry = dict(photo=key, **copy.deepcopy(mark))
                entry['methods'] = {method:[c['id'] for c in method_cases[(method, key)]
                                            if c['keep'] and mark['id'] in c['answers']] for method in methods}
                entry['ambiguous_methods'] = {method:[c['id'] for c in method_cases[(method, key)]
                                                      if c['keep'] and mark['id'] in c['ambiguous_answers']] for method in methods}
                entry['all_4r_candidates'] = [c['id'] for c in cc if mark['id'] in c['answers']]
                entry['excluded_4r_candidates'] = [c['id'] for c in cc if not c['keep'] and mark['id'] in c['answers']]
                entry['ambiguous_4r_candidates'] = [c['id'] for c in cc if mark['id'] in c['ambiguous_answers']]
                entry['edge_4r_candidates'] = [c['id'] for c in cc if mark['id'] in c['edge_answers']]
                entry['proposal_4r_candidates'] = [c['id'] for c in cc if mark['id'] in c['proposal_answers']]
                entry['proposal_ambiguous_4r_candidates'] = [c['id'] for c in cc if mark['id'] in c['proposal_ambiguous_answers']]
                entry['proposal_edge_4r_candidates'] = [c['id'] for c in cc if mark['id'] in c['proposal_edge_answers']]
                entry['hit'] = bool(entry['methods']['4r'])
                entry['compound'] = compound_region(mark)
                entry['has_4r_candidate'] = bool(entry['all_4r_candidates'])
                entry['has_4r_proposal'] = bool(entry['proposal_4r_candidates'] or entry['proposal_ambiguous_4r_candidates'])
                entry['miss_reason'] = ('hit' if entry['hit'] else 'classifier_excluded' if entry['has_4r_candidate']
                                        else 'ambiguous_matching' if entry['ambiguous_4r_candidates']
                                        else 'canonical_moved_away' if entry['has_4r_proposal'] else 'no_candidate')
                markrows.append(entry)
                cx, cy = mark['center']
                extent = np.ptp(np.asarray(mark['polygon']), axis=0).max()
                span = int(max(180, extent+80))
                left = int(max(0, min(original.width-span, cx-span/2)))
                top = int(max(0, min(original.height-span, cy-span/2)))
                crop = padded_crop(original, [left, top, left+span, top+span])
                d = ImageDraw.Draw(crop)
                p = [(x-left, y-top) for x, y in mark['polygon']]
                d.line(p+[p[0]], fill='#ed2346', width=3)
                for case in cc:
                    if mark['id'] not in case['answers']+case['edge_answers']+case['ambiguous_answers']:
                        continue
                    p = [(x-left, y-top) for x, y in case['source_polygon']]
                    d.line(p+[p[0]], fill='#0088dd' if case['keep'] else '#d49c00', width=2)
                crop.resize((360, 360)).save(images/f'{key}-answer-{mark["id"]}.jpg', quality=90)
            annotated.thumbnail((1400, 1400))
            annotated.save(images/f'{key}-answers.jpg', quality=92)
        print('REPORT', key, '4r candidates', len(cc), 'hits', len(row['hits']), '/', len(marks), flush=True)

    totals = {}
    tested = [r for r in rows if not r['is_reference']]
    for method in methods:
        totals[method] = dict(answer_hits=sum(len(r['metrics'][method]['answer_hits']) for r in tested),
                             answer_total=sum(r['answer_count'] for r in tested),
                             kept=sum(r['metrics'][method]['kept'] for r in tested),
                             candidate_count=sum(r['metrics'][method]['candidate_count'] for r in tested),
                             excluded=sum(r['metrics'][method]['excluded'] for r in tested),
                             unmatched=sum(r['metrics'][method]['unmatched'] or 0 for r in tested if r['has_answers']),
                             unmatched_evaluated_photos=sum(r['has_answers'] for r in tested),
                             unlabeled_alerts=sum(r['metrics'][method]['kept'] for r in tested if r['label']=='UNLABELED'),
                             good_alarms=sum(r['metrics'][method]['kept'] for r in tested if r['label']=='OK'),
                             reference_alarms=sum(r['metrics'][method]['kept'] for r in rows if r['is_reference']),
                             ambiguous_candidates=sum(r['metrics'][method]['ambiguous_candidates'] for r in tested),
                             ambiguous_kept=sum(r['metrics'][method]['ambiguous_kept'] for r in tested),
                             edge_only=sum(r['metrics'][method]['edge_only'] for r in tested))
    positions = position_consistency(markrows, rows, methods)
    missing = [m for m in markrows if not m['hit']]
    lost = [f'{m["photo"]}#{m["id"]}' for m in markrows if m['methods']['r3'] and not m['methods']['4r']]
    gained = [f'{m["photo"]}#{m["id"]}' for m in markrows if m['methods']['4r'] and not m['methods']['r3']]
    summary = dict(machine=machine, sku=plan.get('sku'), photos=len(rows), test_photos=len(tested),
                   good_photos=sum(r['label']=='OK' for r in tested),
                   bad_photos=sum(r['label']=='NG' for r in tested),
                   unlabeled_photos=sum(r['label']=='UNLABELED' for r in tested),
                   reference_self_photos=sum(r['is_reference'] for r in rows),
                   candidates=len(allcases), answer_marks=len(markrows), methods=totals, totals=totals,
                   answer_hits=totals['4r']['answer_hits'], answer_total=totals['4r']['answer_total'],
                   metric_unit='annotated_region_observations_not_independent_physical_screws',
                   compound_answer_regions=sum(compound_region(m) for m in markrows),
                   ordinary_answer_regions=sum(not compound_region(m) for m in markrows),
                   region_subsets={method:dict(compound_covered=sum(compound_region(m) and bool(m['methods'][method]) for m in markrows),
                                               ordinary_covered=sum(not compound_region(m) and bool(m['methods'][method]) for m in markrows)) for method in methods},
                   position_groups=len(positions),
                   lost_r3_answers=lost, gained_vs_r3=gained, r3_answers_preserved=not lost,
                   misses=dict(total=len(missing), no_candidate=sum(m['miss_reason']=='no_candidate' for m in missing),
                               classifier_excluded=sum(m['miss_reason']=='classifier_excluded' for m in missing),
                               canonical_moved_away=sum(m['miss_reason']=='canonical_moved_away' for m in missing),
                               ambiguous_matching=sum(m['miss_reason']=='ambiguous_matching' for m in missing)),
                   production_changed=False, frozen_new_batch_evaluation=True,
                   independent_new_scans='See provenance; not inferred from folder name',
                   counting_rule='Central overlap, conservative unique region matching; ambiguous multi-answer candidates are disclosed separately, receive no coverage credit, and are excluded from unmatched-alarm counts')
    for name, value in [('rows.json', rows), ('cases.json', allcases), ('answer-matches.json', markrows), ('summary.json', summary), ('position-consistency.json',positions)]:
        save(out/name, value)

    def card(case):
        outcome = '保留警報' if case['keep'] else '排除'
        answer = ('答案 '+', '.join(map(str, case['answers'])) if case['answers'] else
                  '一框對到多處答案，配對待複核' if case['ambiguous_answers'] else
                  '僅擦到答案邊緣' if case['edge_answers'] else '未對到答案')
        pair = case['paired_evidence']
        labels = '；'.join(('參照' if side=='reference' else '待測')+'：'+
                          ('像螺絲' if pair.get(side, {}).get('label')=='screw' else
                           '不像螺絲' if pair.get(side, {}).get('label') in ('normal','non_screw') else
                           str(pair.get(side, {}).get('label', '未提供'))) for side in ('reference','target'))
        detail = dict(raw_candidate_box=case['box'], actual_object_box=case['canonical_box'],
                      source_polygon=case['source_polygon'], original_proposal_source_polygon=case['proposal_source_polygon'],
                      report_windows=case['report_windows'],
                      classification=case['classification'])
        return (f'<article id="case-{case["key"]}"><h3>{esc(case["photo"])}／候選 #{case["id"]}：{outcome}</h3>'
                f'<p>{TYPES[case["category"]]} · {case["classification_source"]} · {esc(answer)}</p>'
                f'<p><a href="photo-{case["photo"]}.html#case-{case["key"]}">查看照片</a> · '
                f'<a href="category-{case["category"]}.html#case-{case["key"]}">查看同類案例</a> · '
                f'<a href="machine-{machine}.html">返回機種</a></p><p>左：參照圖　右：待測圖</p>'
                f'<img class="pair" src="images/{case["key"]}.jpg" alt="{esc(case["key"])} 參照與待測對照">'
                f'<p>{esc(labels)}。{esc(case["reason"])}</p>'
                '<p class="muted">紅框：原候選；藍框：實際判斷物件範圍。參照位移依原判斷紀錄呈現；越界顯示區補白，不改偵測輸入。</p>'
                f'<details><summary>判斷依據與實際範圍</summary><p>自動規則：{esc(", ".join(case["rules"]) or "無")}</p>'
                f'<pre>{esc(json.dumps(detail,ensure_ascii=False,indent=2))}</pre></details></article>')

    def photo_table(selected):
        return table(['照片','標示','保留候選框','排除候選框','答案區域覆蓋','未對答案警報','本張分類'], [
            [f'<a href="photo-{r["key"]}.html">{esc(r["name"])}</a>',
             {'NG':'不良品（有答案）','OK':'良品','UNLABELED':'未標示良／不良','REF':'參照自比'}.get(r['label'],esc(r['label'])),
             r['kept'],r['excluded'],f'{len(r["hits"])}/{r["answer_count"]}' if r['has_answers'] else '不適用／未提供答案',
             r['unmatched'] if r['has_answers'] else '不作誤報認定',
             '、'.join(f'<a href="category-{kind}.html">{TYPES[kind]} {sum(c["photo"]==r["key"] and c["category"]==kind for c in allcases)}</a>' for kind in TYPES)] for r in selected])

    caveat = ('<p class="warn">本頁計算「答案區域覆蓋次數」，不是獨立實體螺絲顆數。同樣位置在多張影像被標記，會分開計算各張覆蓋；'
              '候選框數也不是螺絲顆數。可能含多物件的大圈只表示該區域有警報，不能解讀為圈內所有螺絲都抓到。'
              '覆蓋數採保守單一配對；一框對多區域的歧義另列「配對待複核」，不算框外警報，也不直接認定漏抓。'
              '未對到答案的警報僅列為待複核／疑似誤報，沒有另造人工標籤。'
              '沒有答案不代表良品；參照圖自比獨立列出，不當作一般良品成績。此輪使用固定版本，未以本批結果調整模型或範例。</p>')
    stats = totals['4r']
    limitations = []
    if (out/'provenance.json').exists():
        limitations = read(out/'provenance.json').get('novelty',{}).get('limitations',[])
    provenance_note = '<div class="box"><p>本批資料能支持的判斷範圍：</p><ul>'+''.join('<li>'+esc(s)+'</li>' for s in limitations)+'</ul></div>' if limitations else ''
    body = (f'<p class="metrics">本次 {esc(machine_title)}：{len(tested)} 張待測、{summary["reference_self_photos"]} 張參照自比；'
                     f'答案區域覆蓋 {stats["answer_hits"]}/{stats["answer_total"]}，待測保留 {stats["kept"]} 個候選框，'
                     f'已提供答案照片的未對答案警報 {stats["unmatched"]} 個。</p>'
                     '<p>數字為答案區域的覆蓋次數，並非螺絲顆數；大圈與歧義配對另列複核。未對答案警報尚未逐框人工確認，Golden 自比不計一般良品成績。</p>')
    body += (f'<p>一般答案區域覆蓋 {summary["region_subsets"]["4r"]["ordinary_covered"]}/{summary["ordinary_answer_regions"]}；'
             f'可能含多物件的大圈覆蓋 {summary["region_subsets"]["4r"]["compound_covered"]}/{summary["compound_answer_regions"]}，'
             '<a href="answers.html#compound-review">另列人工複核</a>。</p>')

    def consistency_section(include_ids=False, compare=False):
        shown_methods = methods if compare else ['4r']
        heading = '相近位置的 r3／4r 覆蓋比較' if compare else '本次 4r：答案相近位置的覆蓋一致性'
        text = '<h2>'+heading+'</h2><p>只依答案原圖座標分組，距離門檻為圖寬／高的1/15，沒有用判斷結果挑分組。每格為該張覆蓋區域／該位置全部標註區域；中間相接雙圈仍各自保留，不合併答案。</p>'
        text += table(['位置群','標註區域次數','有標註照片數']+[m+'全部區域覆蓋的照片' for m in shown_methods], [[
            f'<a href="index.html#position-{p["id"]}">位置 {p["id"]}</a>',p['observations'],p['photos']]+
            [f'{p["methods"][m]["fully_covered_photos"]}/{p["photos"]}' for m in shown_methods] for p in positions])
        for p in positions:
            anchor = f' id="position-{p["id"]}"' if include_ids else ''
            rep = p['representative']
            text += f'<details{anchor}><summary>位置 {p["id"]}：展開全部照片的區域覆蓋</summary>'
            text += f'<img src="images/{rep["photo"]}-answer-{rep["answer_id"]}.jpg" width="220">'
            text += table(['照片','本位置答案區域']+[m+'區域覆蓋' for m in shown_methods]+['複合大圈'], [[
                f'<a href="answers.html#answer-{z["photo"]}">{esc(z["photo"])}</a>',','.join(map(str,z['answer_ids']))]+
                [f'{z["methods"][m]["covered_regions"]}/{z["methods"][m]["answer_regions"]}'+
                 (f'；待複核 {z["methods"][m]["pending_regions"]}' if z['methods'][m]['pending_regions'] else '') for m in shown_methods]+
                [','.join(map(str,z['compound_ids'])) or '無'] for z in p['per_photo']])+'</details>'
        return text

    for ident,title,predicate in [('good','良品完整結果',lambda r:r['label']=='OK'),
                                 ('bad','不良品完整結果',lambda r:r['label']=='NG'),
                                 ('unlabeled','未標示良／不良的完整結果',lambda r:r['label']=='UNLABELED'),
                                 ('references','參照圖自比',lambda r:r['is_reference'])]:
        selected = [r for r in rows if predicate(r)]
        body += f'<h2 id="{ident}">{title}（{len(selected)} 張）</h2>'
        body += photo_table(selected) if selected else '<p>0 張；本次未提供，不推估此類成績。</p>'
    body += f'<p><a href="machine-{machine}.html">{machine} → 五種類型 → 相近位置</a></p>'
    if diagnostics is not None:
        body += '<p><a href="diagnosis.html">附加：漏抓原因與具體影像證據 →</a></p>'
    body += ('<details><summary>評估版本、計數方式與資料限制</summary>'
             '<p>固定 4r 整合主庫 51 螺絲＋90 正常，沿用既有副庫與雙圖規則；正式流程未更動。</p>'+
             caveat+provenance_note+'</details>')
    body += consistency_section(True)
    page('index.html', f'{machine_title}｜4r 全圖資完整結果', body)
    counts = Counter(c['category'] for c in allcases)
    page(f'machine-{machine}.html', f'{machine_title} → 誤報類型', caveat+
         table(['類型','全部候選框','人工確認分類'], [[f'<a href="category-{kind}.html">{label}</a>',counts[kind],0] for kind,label in TYPES.items()])+
         '<p>類型只依實際規則自動推測；無法分類的保留為待確認。相近位置以參照座標中心距離45像素分組。</p>'+photo_table(rows))
    for kind,title in TYPES.items():
        selected = [c for c in allcases if c['category']==kind]
        body = f'<p><a href="machine-{machine}.html">返回此機種</a>；共 {len(selected)} 個候選。</p>'
        for number, group in enumerate(common.grouped(copy.deepcopy(selected)),1):
            body += f'<section><h2>相近位置 {number}／{len(group)} 個候選</h2>'+columns(group,card,lambda c:c['keep'],True)+'</section>'
        if not selected:
            body += '<p>0 個案例。</p>'
        page(f'category-{kind}.html', f'{machine_title} → {title} → 相近位置', body)
    for row in rows:
        key = row['key']
        cases = [c for c in allcases if c['photo']==key]
        alignment_note = '有，請檢查對位' if row['alignment_warning'] else '無'
        body = (f'<p><a href="machine-{machine}.html">返回此機種</a> · '+
                ' · '.join(f'<a href="category-{kind}.html">查看{label}同類案例</a>' for kind,label in TYPES.items())+'</p>'+
                f'<p>分類：'+esc('、'.join(f'{label} {sum(c["category"]==kind for c in cases)}' for kind,label in TYPES.items()))+
                f'。保留 {row["kept"]}、排除 {row["excluded"]}。對位提醒：{alignment_note}。</p>'+
                f'<div class="grid"><div>參照圖<img src="images/{key}-reference.jpg"></div>'
                f'<div>藍框：實際判斷並保留的物件範圍<img src="images/{key}-actual-overlay.jpg"></div></div>'
                '<p class="muted">藍框使用實際判斷物件換回原圖後的範圍；完全相同的範圍共用框線並列候選號碼，不改候選統計，也不表示獨立螺絲顆數。</p>'
                f'<details><summary>原提案保留框，可能與實際取圖範圍不同</summary><p>此圖保留偵測器原始輸出供追溯；原提案框涵蓋答案不代表實際判斷物件已覆蓋該答案。</p><img src="images/{key}-overlay.jpg"></details>'
                f'<details><summary>查看完整原始照片</summary><img src="images/{key}-source.jpg"></details>')
        if row['has_answers']:
            body += f'<p><a href="answers.html#answer-{key}">本張全部答案核對</a>：{len(row["hits"])}/{row["answer_count"]}</p>'
        body += '<h2>全部保留與排除候選</h2>'+columns(cases,card,lambda c:c['keep'])
        if row['structure_changes']:
            body += '<details><summary>其他結構變化（不當作螺絲）</summary><pre>'+esc(json.dumps(row['structure_changes'],ensure_ascii=False,indent=2))+'</pre></details>'
        page(f'photo-{key}.html', f'{machine_title}／{row["name"]}', body)

    body = caveat+('<p>答案由提供的標記圖獨立配準到原圖，沒有依偵測結果移動答案。使用既有中心重疊規則，擦邊不算覆蓋；'
            '同一候選對到多處答案時另列歧義，不把一框當多顆。下圖紅框為答案、藍框為保留候選、褐框為排除候選。</p>')
    body += consistency_section()
    compound_marks = [m for m in markrows if compound_region(m)]
    body += f'<h2 id="compound-review">可能含多物件的大圈（{len(compound_marks)} 個區域）</h2><p>大圈有警報只表示區域覆蓋，不能據此確認圈內全部物件已抓到；原標記不拆成新的人工答案。</p>'
    for m in compound_marks:
        key=m['photo']; ids=m['methods']['4r']
        body += (f'<article><h3><a href="#mark-{key}-{m["id"]}">{key} 答案區域 {m["id"]}</a></h3>'
                 f'<img src="images/{key}-answer-{m["id"]}.jpg" width="360"><p>保留候選：'+
                 ('、'.join(f'<a href="photo-{key}.html#case-{key}-{i}">#{i}</a>' for i in ids) or '無')+
                 '。'+esc(m.get('annotation_note',m.get('visual_review_note',m.get('note','圈內實體物件數待人工確認。'))))+'</p></article>')
    reason_names = {'hit':'區域已覆蓋','classifier_excluded':'已有候選，但分類排除',
                    'canonical_moved_away':'原提案有涵蓋，實際判斷範圍移開',
                    'no_candidate':'原提案與實際判斷範圍都未對到答案中心',
                    'ambiguous_matching':'有候選涵蓋多處答案，配對待複核'}
    for row in rows:
        if not row['has_answers']:
            continue
        key=row['key']
        body += f'<section id="answer-{key}"><h2>{esc(row["name"])}</h2><p><a href="photo-{key}.html">返回完整照片</a></p>'
        if row['answer_count']:
            body += f'<img src="images/{key}-answers.jpg">'
        if row['answer']:
            body += f'<details><summary>使用者提供的原答案圖</summary><img src="images/{key}-supplied-answer.jpg"></details>'
        for mark in [m for m in markrows if m['photo']==key]:
            ids = sorted(set(mark['all_4r_candidates']+mark['edge_4r_candidates']+mark['ambiguous_4r_candidates']+
                             mark['proposal_4r_candidates']+mark['proposal_ambiguous_4r_candidates']+mark['proposal_edge_4r_candidates']))
            links = '、'.join(f'<a href="photo-{key}.html#case-{key}-{i}">#{i}</a>' for i in ids) or '無'
            body += (f'<article id="mark-{key}-{mark["id"]}"><h3>答案 {mark["id"]}：{reason_names[mark["miss_reason"]]}</h3>'
                     f'<img src="images/{key}-answer-{mark["id"]}.jpg" width="360">'
                     f'<p>本次 4r：'+('區域已覆蓋' if mark['hit'] else '未覆蓋')+f'。相關4r候選：{links}。'+
                     ('原提案對到本區域的候選：'+esc(', '.join(map(str,mark['proposal_4r_candidates']+mark['proposal_ambiguous_4r_candidates'])))+
                      '；此處不據原提案框給覆蓋分，仍以實際判斷物件為準。' if mark['has_4r_proposal'] else '')+
                     ('此為可能涵蓋多物件的大圈，不能視為圈內全部物件命中。' if compound_region(mark) else '')+'</p></article>')
        body += '</section>'
    page('answers.html', f'{machine_title}｜全部 {len(markrows)} 次答案區域核對', body)

    body = caveat+'<p>兩版各自由原圖重新執行對位、候選生成與分類，並各自換回原圖座標核對同一份答案；沒有假設兩版候選或對位相同。此頁為附加比較，不替代完整結果。</p>'
    body += table(['指標']+[METHOD_NAMES[m] for m in methods], [[name]+[totals[m][field] for m in methods] for name,field in
                  [('答案區域覆蓋','answer_hits'),('答案區域總次數','answer_total'),('待測候選總數','candidate_count'),('待測保留候選框','kept'),
                   ('已附答案照片的未對答案警報','unmatched'),('其中僅擦到答案邊緣','edge_only'),('未標示照片的保留警報（不認定誤報）','unlabeled_alerts'),
                   ('一般良品警報','good_alarms'),('參照自比警報','reference_alarms'),('配對待複核警報（不算框外警報）','ambiguous_kept'),('全部配對歧義候選','ambiguous_candidates')]])
    body += f'<p>原 r3 已覆蓋而 4r 未覆蓋：{len(lost)} 次；4r 新覆蓋：{len(gained)} 次。這是本批實測，不以報告完整性通過代替模型效能驗收，也不代表獨立螺絲顆數。</p>'
    body += consistency_section(compare=True)
    for title, selected in [('原 r3 覆蓋但4r未覆蓋的答案區域',[m for m in markrows if m['methods']['r3'] and not m['hit']]),
                            ('4r新增覆蓋的答案區域',[m for m in markrows if m['hit'] and not m['methods']['r3']])]:
        body += f'<h2>{title}（{len(selected)}）</h2><p>'+('、'.join(f'<a href="answers.html#mark-{m["photo"]}-{m["id"]}">{m["photo"]} 答案{m["id"]}</a>' for m in selected) or '無')+'</p>'
    body += table(['照片','r3區域覆蓋','4r區域覆蓋','r3未對答案警報','4r未對答案警報','原始判斷紀錄'], [[
        f'<a href="photo-{r["key"]}.html">{esc(r["name"])}</a>',len(r['metrics']['r3']['answer_hits']),len(r['hits']),
        r['metrics']['r3']['unmatched'] if r['has_answers'] else '未提供答案',r['unmatched'] if r['has_answers'] else '未提供答案',
        ' · '.join(f'<a href="../runs/{m}/{r["key"]}/result.json">{m} 全部判斷</a>' for m in methods)] for r in rows])
    page('comparison.html', f'{machine_title}｜附加：原 r3 與固定 4r 比較', body)

    body = '<p>原始圖、答案、模型、範例及政策以凍結計畫的SHA核對；本報告只整理實際結果，不變更判斷。未完成來源去重前，不宣稱獨立盲測。</p>'
    body += '<p>評估範圍：'+esc(plan.get('scope','請見凍結計畫'))+'</p>'
    provenance_paths = [p for p in (out/'audit/provenance.json',out/'provenance.json',out/'audit/duplicate-audit.json') if p.is_file()]
    for p in provenance_paths:
        body += f'<details><summary>來源去重與資料核對：{esc(p.name)}</summary><pre>'+esc(json.dumps(read(p),ensure_ascii=False,indent=2))+'</pre></details>'
    if not provenance_paths:
        body += '<p>目前尚無來源去重紀錄；不能據此判定這批從未參與先前開發。</p>'
    body += table(['照片','答案配準證據'], [[esc(key),'<pre>'+esc(json.dumps(value.get('registration',{}),ensure_ascii=False,indent=2))+'</pre>'] for key,value in answers.items()])
    body += table(['來源圖','SHA-256'],[[esc(item['path']),esc(item.get('sha256','未提供'))] for item in plan['items']])
    body += '<p>'+' · '.join(f'<a href="../{name}">{label}</a>' for name,label in [('plan.json','凍結計畫'),('answers.json','答案座標'),('summary.json','統計'),('rows.json','逐張結果'),('cases.json','全部4r候選'),('answer-matches.json','逐處答案配對'),('position-consistency.json','相近位置覆蓋一致性'),('verification.json','完整性核對')])+'</p>'
    page('provenance.html', f'{machine_title}｜圖資與核對證據', body)
    if diagnostics is not None:
        body = '<p>'+esc(diagnostics.get('intro','')).replace('\n','<br>')+'</p>'
        body += '<p><a href="index.html">返回完整結果</a> · <a href="answers.html">全部答案區域</a></p>'
        for number, finding in enumerate(diagnostics.get('findings', []),1):
            body += (f'<section id="finding-{number}"><h2>'+esc(finding.get('title',f'診斷 {number}'))+
                     '</h2><p>'+esc(finding.get('text','')).replace('\n','<br>')+'</p>')
            if finding.get('image'):
                path, href = diagnostic_file(out, finding['image'])
                diagnostic_hashes[str(path)] = sha(path)
                body += '<img src="'+esc(href)+'" alt="'+esc(finding.get('title','漏抓診斷影像'))+'">'
            if finding.get('evidence'):
                path, href = diagnostic_file(out, finding['evidence'])
                diagnostic_hashes[str(path)] = sha(path)
                body += '<p><a href="'+esc(href)+'">查看完整診斷證據</a></p>'
            case_links = []
            for link in finding.get('case_links', []):
                photo, ident = safe_key(link['photo']), safe_key(link['id'])
                case_links.append(f'<a href="photo-{photo}.html#case-{photo}-{ident}">'+
                                  esc(link.get('label', f'{photo} 候選 #{ident}'))+'</a>')
            if case_links:
                body += '<p>對應候選：'+' · '.join(case_links)+'</p>'
            body += '</section>'
        body += '<p><a href="../diagnostics.json">診斷內容與證據清單</a></p>'
        page('diagnosis.html', diagnostics.get('title',f'{machine_title}｜附加：漏抓原因'), body)
    verify(out, plan, pages, allcases, rows, markrows, summary, result_hashes, diagnostic_hashes)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


def verify(out, plan, expected_pages, cases, rows, marks, summary, result_hashes, diagnostic_hashes=None):
    report=out/'report'
    save(out/'verification.json',dict(status='checking'))
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(); self.ids=[]; self.links=[]; self.images=[]; self.stack=[]; self.outcomes={}; self.columns=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if 'id' in a:self.ids.append(a['id'])
            self.links.extend(a[k] for k in ('href','src') if k in a)
            if tag=='img' and 'src' in a:self.images.append(a['src'])
            if tag=='section':
                self.stack.append(a.get('data-result'))
                if a.get('data-result'):self.columns.append(a['data-result'])
            if tag=='article' and a.get('id','').startswith('case-'):
                self.outcomes[a['id'][5:]]=next((v for v in reversed(self.stack) if v),None)
        def handle_endtag(self,tag):
            if tag=='section':self.stack.pop()
    assert {p.name for p in report.glob('*.html')}==expected_pages, 'Unexpected stale report pages'
    parsed={}; index={c['key']:c for c in cases}
    assert len(index)==len(cases)
    for path in report.glob('*.html'):
        p=Parser();p.feed(path.read_text(encoding='utf-8'))
        assert len(p.ids)==len(set(p.ids)),path
        assert all(p.columns[i:i+2]==['exclude','keep'] for i in range(0,len(p.columns),2)),path
        for key,side in p.outcomes.items():assert side==('keep' if index[key]['keep'] else 'exclude'),(path,key)
        parsed[path.resolve()]=p
    links=0; displayed_images=set()
    for path,p in parsed.items():
        for link in p.links:
            if urlsplit(link).scheme:
                raise AssertionError(('Unexpected external report link',path,link))
            name,_,anchor=link.partition('#')
            dest=(path.parent/unquote(name)).resolve() if name else path
            assert dest.exists(),(path,link)
            if anchor:assert dest in parsed and unquote(anchor) in parsed[dest].ids,(path,link)
            links+=1
        for image in p.images:
            dest=(path.parent/unquote(image)).resolve()
            if dest not in displayed_images:
                with Image.open(dest) as im:im.load()
                displayed_images.add(dest)
    for row in rows:
        assert set(parsed[(report/f'photo-{row["key"]}.html').resolve()].outcomes)=={c['key'] for c in cases if c['photo']==row['key']}
    for kind in TYPES:
        assert set(parsed[(report/f'category-{kind}.html').resolve()].outcomes)=={c['key'] for c in cases if c['category']==kind}
    for path in (report/'images').glob('*.jpg'):
        with Image.open(path) as image:image.verify()
    assert len(rows)==len(plan['items']) and len(cases)==sum(r['candidates'] for r in rows)
    assert len(marks)==sum(r['answer_count'] for r in rows)
    assert summary['answer_hits']==sum(m['hit'] for m in marks)
    assert summary['misses']['total']==sum(value for key,value in summary['misses'].items() if key!='total')
    assert all(sha(Path(path))==digest for path,digest in plan['hashes'].items()), 'Frozen source/model/policy changed'
    assert all(not Path(path).exists() for path in plan.get('protected_absent',[])), 'A protected production file was unexpectedly created'
    assert all(sha(out/path)==digest for path,digest in result_hashes.items()), 'Detection results changed during report'
    assert all(sha(Path(path))==digest for path,digest in (diagnostic_hashes or {}).items()), 'Diagnostic evidence changed during report'
    result=dict(status='passed',photos=len(rows),candidates=len(cases),answers=len(marks),
                html_pages=len(parsed),links_checked=links,images_checked=len(displayed_images),
                all_photos_included=True,all_photo_and_category_candidates_covered=True,
                all_candidates_in_correct_outcome_column=True,left='exclude',right='keep',
                source_model_policy_hashes_unchanged=True,result_sha256=result_hashes,
                diagnostic_evidence_sha256=diagnostic_hashes or {},
                report_integrity_only=True,model_r3_answers_preserved=not summary['lost_r3_answers'])
    save(out/'verification.json',result)
    print('VERIFIED',len(parsed),'pages',links,'links',len(cases),'candidates',flush=True)


if __name__=='__main__':
    main()
