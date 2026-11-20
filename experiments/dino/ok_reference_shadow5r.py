"""Research-only OK-reference selection; never mutates official decisions.

Select by surrounding context only, before measuring candidate residuals.
Reuse the frozen structure-shadow gates without relaxing any threshold.
"""
import cv2
import numpy as np

from structure_shadow5r import RULES

VERSION = '5r-ok-context-reference-shadow-20261120'


def unit(image):
    return image.astype(np.float32)/255 if image.dtype == np.uint8 else image.astype(np.float32)


def context_match(reference, target, candidate, pad):
    x,y,w,h=[int(candidate[k]) for k in ('x','y','w','h')]
    radius=RULES['search'];border=RULES['exclude_border']
    x0,y0=x-pad,y-pad;X,Y=x+w+pad,y+h+pad
    if min(x0-radius,y0-radius)<0 or X+radius>reference.shape[1] or Y+radius>reference.shape[0]:
        return dict(valid=False,reason='image_boundary',pad=pad)
    b=unit(target[y0:Y,x0:X]);mask=np.ones(b.shape,np.float32)
    mask[pad-border:pad+h+border,pad-border:pad+w+border]=0
    selected=b[mask>0].astype(np.float64)
    if selected.std()<.025:
        return dict(valid=False,reason='insufficient_surrounding_texture',pad=pad)
    area=unit(reference[y0-radius:Y+radius,x0-radius:X+radius])
    n=float(mask.sum());mean=float(selected.mean())
    bc=(b-mean)*mask;bn=float(((selected-mean)**2).sum())
    sums=cv2.matchTemplate(area,mask,cv2.TM_CCORR)
    squares=cv2.matchTemplate(area*area,mask,cv2.TM_CCORR)
    numerator=cv2.matchTemplate(area,bc,cv2.TM_CCORR)
    denominator=np.sqrt(np.maximum(squares-sums*sums/n,0)*bn)
    scores=np.divide(numerator,denominator,out=np.full(numerator.shape,-1.,np.float32),where=denominator>1e-8)
    iy,ix=np.unravel_index(np.argmax(scores),scores.shape);dx,dy=int(ix-radius),int(iy-radius)
    a=unit(reference[y0+dy:Y+dy,x0+dx:X+dx])[mask>0].astype(np.float64)
    ac=a-a.mean();bc=selected-selected.mean();norm=float(ac@ac)
    score=float((ac@bc)/max(np.sqrt(norm*(bc@bc)),1e-12))
    gain=float((ac@bc)/max(norm,1e-12));offset=float(selected.mean()-gain*a.mean())
    return dict(valid=True,pad=pad,score=score,dx=dx,dy=dy,gain=gain,offset=offset,
                registration_uses_candidate=False)


def eligible_references(pool, query):
    # Fail closed on machine/reference mismatch, self, duplicate input or non-OK.
    result=[];seen=set()
    for entry in sorted(pool,key=lambda r:r['source_sha256']):
        if (entry['label']!='OK' or entry.get('is_reference',False)
                or entry['machine']!=query['machine']
                or entry['reference_sha256']!=query['reference_sha256']
                or entry['source_sha256']==query['source_sha256']
                or entry['source_sha256'] in seen):continue
        seen.add(entry['source_sha256']);result.append(entry)
    return result


def review(original_reference,target,candidate,pool,query,load_image):
    from enclosure_rescue5r import geometry
    row=dict(candidate_id=candidate['id'],recommendation='retain',reason='insufficient_evidence')
    if max(candidate['w'],candidate['h'])>RULES['maximum_candidate_side']:
        return dict(row,reason='outside_review_size')
    core=geometry(target,candidate)
    if core is not None:
        return dict(row,reason='independent_object_protected',core=core)
    ranked=[]
    for entry in eligible_references(pool,query):
        image=load_image(entry)
        if image.shape!=target.shape:continue
        views=[context_match(image,target,candidate,pad) for pad in RULES['pads']]
        if not all(v['valid'] for v in views):continue
        # Weakest-context score determines selection. No candidate pixels,
        # residuals, DINO scores or answer positions participate in ranking.
        ranked.append(dict(reference_id=entry['id'],source_sha256=entry['source_sha256'],
                           rank_score=min(v['score'] for v in views),views=views))
    ranked.sort(key=lambda r:(-r['rank_score'],r['source_sha256']))
    row.update(selection='highest_minimum_surrounding_correlation',ranking=ranked,
               eligible_count=len(ranked))
    if not ranked:return dict(row,reason='no_compatible_OK_reference')
    chosen=ranked[0];row['selected_reference_id']=chosen['reference_id']
    selected=load_image(next(e for e in pool if e['id']==chosen['reference_id']))
    x,y,w,h=[int(candidate[k]) for k in ('x','y','w','h')]
    target_roi=unit(target[y:y+h,x:x+w])
    before=np.maximum(unit(original_reference[y:y+h,x:x+w])-target_roi,0)
    active=before>RULES['residual_threshold'];views=[]
    for context in chosen['views']:
        dx,dy=context['dx'],context['dy']
        predicted=unit(selected[y+dy:y+h+dy,x+dx:x+w+dx])*context['gain']+context['offset']
        residual=np.maximum(predicted-target_roi,0)
        fraction=float(residual[active].sum()/max(float(before[active].sum()),1e-12)) if active.any() else None
        _,_,stats,_=cv2.connectedComponentsWithStats((residual>RULES['residual_threshold']).astype('uint8'))
        largest=int(stats[1:,4].max()) if len(stats)>1 else 0
        views.append(dict(context,original_active_pixels=int(active.sum()),remaining_fraction=fraction,
                          largest_residual_component=largest))
    row['selected_views']=views
    correspondence=all(v['score']>=RULES['minimum_correlation'] and
                       max(abs(v['dx']),abs(v['dy']))<RULES['search'] and
                       RULES['gain_bounds'][0]<=v['gain']<=RULES['gain_bounds'][1] for v in views)
    consistent=all(abs(views[0][k]-views[1][k])<=RULES['maximum_offset_disagreement'] for k in ('dx','dy'))
    explained=all(v['remaining_fraction'] is not None and
                  v['remaining_fraction']<=RULES['maximum_remaining_fraction'] and
                  v['largest_residual_component']<RULES['minimum_component_area'] for v in views)
    row.update(correspondence_passed=correspondence,offset_consistent=consistent,residual_explained=explained)
    if correspondence and consistent and explained:
        row.update(recommendation='exclude_suggestion',reason='OK_structure_explains_original_difference')
    return row
