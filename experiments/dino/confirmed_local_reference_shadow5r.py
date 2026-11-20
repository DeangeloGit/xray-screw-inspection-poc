"""Offline comparison using explicitly confirmed *local* reference annotations.

No production integration. Context may locate a region but cannot expand its
normal label. Reuses the existing context fit, residual definition and gates.
"""
from structure_shadow5r import RULES
from ok_reference_shadow5r import context_match
from structure_cause_shadow5r import ablation

VERSION = '5r-confirmed-local-reference-offline-20261120'


def covered(candidate, bbox, dx=0, dy=0):
    x, y, w, h = [int(candidate[k]) for k in ('x', 'y', 'w', 'h')]
    a, b, X, Y = bbox
    return a <= x+dx and b <= y+dy and x+w+dx <= X and y+h+dy <= Y


def compare(original_reference, target, candidate, reference, annotation):
    views = []
    for pad in RULES['pads']:
        fit = context_match(reference, target, candidate, pad)
        if not fit['valid']:
            views.append(fit)
            continue
        inside = covered(candidate, annotation['confirmed_normal_bbox'], fit['dx'], fit['dy'])
        # Never evaluate normal-reference residuals outside the confirmed region.
        if not inside:
            views.append(dict(fit, normal_region_covered=False))
            continue
        measured = ablation(original_reference, reference, target, candidate,
                            pad, fit['dx'], fit['dy'])
        corrected = next(s for s in measured['stages'] if s['stage']=='translation_and_exposure')
        views.append(dict(fit, normal_region_covered=True,
                          original_active_pixels=measured['original_active_pixels'],
                          remaining_fraction=corrected['remaining_fraction'],
                          largest_residual_component=corrected['largest_residual_component']))
    coverage = all(v.get('normal_region_covered', False) for v in views)
    correspondence = all(v['valid'] and v['score'] >= RULES['minimum_correlation']
                         and max(abs(v['dx']), abs(v['dy'])) < RULES['search']
                         and RULES['gain_bounds'][0] <= v['gain'] <= RULES['gain_bounds'][1]
                         for v in views)
    consistent = all(v['valid'] for v in views) and all(
        abs(views[0][k]-views[1][k]) <= RULES['maximum_offset_disagreement'] for k in ('dx','dy'))
    explained = coverage and all(v['remaining_fraction'] is not None
                                and v['remaining_fraction'] <= RULES['maximum_remaining_fraction']
                                and v['largest_residual_component'] < RULES['minimum_component_area']
                                for v in views)
    return dict(reference_id=annotation['id'], views=views, local_label_covered=coverage,
                correspondence_passed=bool(correspondence), offset_consistent=bool(consistent),
                residual_explained=bool(explained), passed=bool(coverage and correspondence and consistent and explained))


def review(original_reference, target, candidate, references, query, load_image):
    from enclosure_rescue5r import geometry
    row = dict(candidate_id=candidate['id'], mode='offline_shadow_only',
               recommendation='retain', automatic_exclusion_allowed=False,
               target_human_normal_confirmed=False)
    if max(candidate['w'],candidate['h']) > RULES['maximum_candidate_side']:
        return dict(row, reason='outside_review_size')
    core = geometry(target, candidate)
    if core is not None:
        return dict(row, reason='independent_object_protected', core=core)
    eligible = []
    seen = set()
    for ref in references:
        if (not ref.get('local_normal_confirmed')
            or ref['machine'] != query['machine']
            or ref['reference_sha256'] != query['reference_sha256']
            or ref['source_sha256'] == query['source_sha256']
            or ref['source_sha256'] in seen
            or not covered(candidate, ref['confirmed_normal_bbox'])):
            continue
        seen.add(ref['source_sha256'])
        eligible.append(ref)
    # The requested experiment requires both distinct local references, not a
    # best-of-two selection that could conceal contradictory evidence.
    if len(eligible) != 2:
        return dict(row, reason='requires_two_compatible_confirmed_local_references',
                    eligible_reference_ids=[r['id'] for r in eligible])
    comparisons = []
    for ref in eligible:
        image = load_image(ref)
        if image.shape != target.shape:
            return dict(row, reason='reference_shape_mismatch')
        comparisons.append(compare(original_reference, target, candidate, image, ref))
    passed = all(c['passed'] for c in comparisons)
    return dict(row, comparisons=comparisons, both_references_passed=passed,
                recommendation='exclude_suggestion' if passed else 'retain',
                reason='two_confirmed_local_references_explain_difference' if passed else 'local_reference_evidence_failed')
