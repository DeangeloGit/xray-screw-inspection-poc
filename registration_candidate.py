"""Test a reflected image only when ordinary registration lacks strong support."""
import numpy as np


def choose_registration(ref, raw, register_one, machine_mask, correlation):
    ordinary=None;original_error=None
    try:ordinary=register_one(ref,raw)
    except ValueError as error:original_error=error
    mask=machine_mask(ref)
    def quality(reg):
        valid=mask&reg['valid']
        coverage=float(valid.sum())/max(int(mask.sum()),1)
        return correlation(ref,reg['aligned'],valid),coverage
    base_score,base_coverage=quality(ordinary) if ordinary is not None else (-1.,0.)
    if ordinary is not None and ordinary['inliers']>=100 and base_score>=.90 and base_coverage>=.95:
        ordinary['mirrored']=False
        return ordinary
    try:
        reflected=register_one(ref,np.fliplr(raw).copy())
        score,coverage=quality(reflected)
        supported=(reflected['inliers']>=max(50,2*ordinary['inliers'] if ordinary else 50)
                   and coverage>=.95 and score>=.65 and score>=base_score+.05)
        if supported:
            reflected['mirrored']=True
            reflected['orientation_evidence']=dict(ordinary_inliers=ordinary['inliers'] if ordinary else 0,
                                                   ordinary_correlation=base_score,mirrored_correlation=score)
            return reflected
    except ValueError:
        pass
    if ordinary is None:raise original_error
    ordinary['mirrored']=False
    return ordinary
