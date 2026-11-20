"""Target-first contour hypotheses. Correspondence never deletes an input."""
from boundary_shadow6r import analyze


def organize(target, seeds):
    evidence = analyze(target, seeds)
    groups = {}
    for row in evidence['rows']:
        row['formal_action'] = 'unchanged'
        row['unresolved_action'] = 'preserve_for_review'
        if not row['stable_pairs']:
            continue
        pair = max(row['stable_pairs'], key=lambda p: max(b[2]*b[3] for b in p['boxes']))
        levels = [next(v for v in row['levels'] if v['level'] == k) for k in pair['levels']]
        # Identity at both levels avoids joining different components by proximity.
        key = (levels[0]['level'], levels[0]['component'], levels[1]['component'])
        row['object_box'] = levels[1]['box']
        g = groups.setdefault(key, dict(box=row['object_box'], members=[], contour_key=list(key)))
        g['members'].append(row['id'])
    return dict(rows=evidence['rows'], groups=[dict(g, id=i, official_alarm=False,
        complete_object_verified=False) for i, g in enumerate(groups.values(), 1)],
        mode='target_first_offline', unresolved_action='preserve_for_review')
