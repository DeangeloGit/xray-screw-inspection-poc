"""Experimental terminal normal-structure review, after the frozen 79 pipeline.

No locations, candidate IDs, answer labels, or file names enter this policy.
The normal prototype is separately versioned, with human-label provenance.
"""
import copy, hashlib
import numpy as np
from dino_paired_optimized import adjusted_image, features
from dino_adapter import paired_decision
from example_audit_policy import square_crop
VERSION='4r-normal-connector-full-shape-four-view-v3-20261106'
PADS=(2,4,8,12)

def _score(snapshot, image, extent, pad, bank, normal_bank):
    im = adjusted_image(snapshot.manifest, square_crop(image, extent, pad))
    v = features(snapshot.manifest, snapshot.session, im)
    sims = [(bank[:, :, 0] @ v[0]).max(axis=1), bank[:, 0, 1] @ v[1]]
    margins = [float(np.sort(s[:47])[-3:].mean() - np.sort(s[47:])[-3:].mean()) for s in sims]
    ns = [float((normal_bank['bank'][:, :, i] @ v[i]).max()) for i in (0, 1)]
    ps = [float((bank[:47, :, i] @ v[i]).max()) for i in (0, 1)]
    return dict(screw_margin=sum(margins)/2, whole_margin=margins[0], local_margin=margins[1],
                normal_similarity=ns, strongest_screw_similarity=ps,
                normal_wins_both=all(n > p for n, p in zip(ns, ps)),
                input_sha256=hashlib.sha256(im.tobytes()).hexdigest())


def _mean_gaps(views):
    return [float(np.mean([v['normal_similarity'][i] - v['strongest_screw_similarity'][i]
                          for v in views])) for i in (0, 1)]


def review(snapshot, ref, target, extent, bank, normal_bank, *, decision_only=False):
    ratio = (max(extent[2:]) / min(extent[2:])) / normal_bank['aspect']
    aspect_compatible = .5 <= ratio <= 2
    target_views = {}
    if decision_only:
        if not aspect_compatible:
            return None
        for pad in PADS:
            score = _score(snapshot, target, extent, pad, bank, normal_bank)
            if not score['screw_margin'] < 0:
                return None
            target_views[pad] = score
        if not all(gap > 0 for gap in _mean_gaps(target_views.values())):
            return None
    views = []
    for pad in PADS:
        reference_score = _score(snapshot, ref, extent, pad, bank, normal_bank)
        target_score = target_views[pad] if decision_only else _score(snapshot, target, extent, pad, bank, normal_bank)
        views.append(dict(pad=pad, reference=reference_score, target=target_score))
    pair={}
    for side in ('reference','target'):
        s={k:float(np.mean([v[side][k] for v in views])) for k in ('screw_margin','whole_margin','local_margin')}
        pair[side]=dict(s,label='screw' if s['screw_margin']>=0 else 'non_screw',score_kind='47_65_full_shape_mean4',input_sha256=hashlib.sha256(''.join(v[side]['input_sha256'] for v in views).encode()).hexdigest())
    # Appearance corroboration is pooled over the same four views used by
    # the existing complete-shape review. Each base margin must still be <0.
    # Reject matches to shapes more than twice as thin/broad as the normal
    # exemplar, avoiding normal-texture transfer onto long wire+screw objects.
    mean_gaps = _mean_gaps([v['target'] for v in views])
    return dict(pair=pair, views=views, aspect_ratio_to_example=ratio,
                aspect_compatible=aspect_compatible, normal_mean_gaps=mean_gaps,
                exclude=aspect_compatible and all(g > 0 for g in mean_gaps)
                and all(v['target']['screw_margin'] < 0 for v in views))

def apply(snapshot,ref,target,previous,bank,normal_bank, *, decision_only=False):
    # This terminal stage can only remove a previously retained whole-object
    # alarm. B-part recognition and upstream duplicate suppression are fixed.
    if previous['filter_recommendation']!='keep' or 'visible_part_experiment' in previous:return previous,None
    checked=review(snapshot,ref,target,previous['canonical_object']['box'],bank,normal_bank,decision_only=decision_only)
    if checked is None or not checked['exclude']:return previous,checked
    pred=paired_decision(checked['pair']['target'],checked['pair']['reference'])
    pred.update(status='active',model_id=previous['model_id'],action='discard',canonical_object=copy.deepcopy(previous['canonical_object']),correspondence_experiment=copy.deepcopy(previous.get('correspondence_experiment',{})),normal_structure_review=dict(version=VERSION,views=checked['views'],previous=previous,normal_example='human-confirmed connector #22; separately versioned bank',aspect_ratio_to_example=checked['aspect_ratio_to_example'],normal_mean_gaps=checked['normal_mean_gaps'],rule='All four original 47/65 full-shape target margins < 0; mean confirmed-normal-minus-strongest-screw similarity > 0 in both channels; object aspect within factor 2 of normal exemplar'),decision_reason='4r 正常結構複核：保留完整外形的四個範圍都較接近正常範例；長寬比例符合正常接點，整體與局部特徵的四範圍平均也支持人工確認的正常接點，排除。')
    pred['correspondence_experiment']['reference_offset']=[0,0]
    assert pred['filter_recommendation']=='exclude'
    return pred,checked
