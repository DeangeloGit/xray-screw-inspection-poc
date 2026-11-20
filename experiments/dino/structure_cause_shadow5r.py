"""Diagnostic ablation of position, exposure and spatial correspondence.

Never returns an exclusion. Existing gates are used to describe evidence, not
to waive a failed match. Grid boxes are image-relative, not photo-specific.
"""
import cv2
import numpy as np
from ok_reference_shadow5r import unit
from structure_shadow5r import RULES

VERSION='5r-structure-cause-audit-20261120'
GRID_PADDING=96
GRID_DIVISIONS=3


def correlation(a,b):
    a=a.astype(np.float64);b=b.astype(np.float64)
    a-=a.mean();b-=b.mean()
    return float(a@b/max(np.linalg.norm(a)*np.linalg.norm(b),1e-12))


def fit_exposure(a,b,mask):
    a=a[mask].astype(np.float64);b=b[mask].astype(np.float64)
    ac=a-a.mean();bc=b-b.mean()
    gain=float(ac@bc/max(ac@ac,1e-12))
    return gain,float(b.mean()-gain*a.mean())


def ablation(original_reference,alternative,target,c,pad,dx,dy):
    x,y,w,h=[int(c[k]) for k in ('x','y','w','h')]
    b=unit(target[y-pad:y+h+pad,x-pad:x+w+pad])
    ring=np.ones(b.shape,bool);border=RULES['exclude_border']
    ring[pad-border:pad+h+border,pad-border:pad+w+border]=False
    before=np.maximum(unit(original_reference[y:y+h,x:x+w])-unit(target[y:y+h,x:x+w]),0)
    active=before>RULES['residual_threshold'];denom=float(before[active].sum())
    records=[]
    for name,shift,exposure in [('identity',(0,0),False),('translation_only',(dx,dy),False),
                                ('exposure_only',(0,0),True),('translation_and_exposure',(dx,dy),True)]:
        sx,sy=shift;a=unit(alternative[y-pad+sy:y+h+pad+sy,x-pad+sx:x+w+pad+sx])
        gain,offset=fit_exposure(a,b,ring) if exposure else (1.,0.)
        predicted=a*gain+offset;res=np.maximum(predicted[pad:pad+h,pad:pad+w]-b[pad:pad+h,pad:pad+w],0)
        _,_,stats,_=cv2.connectedComponentsWithStats((res>RULES['residual_threshold']).astype('uint8'))
        records.append(dict(stage=name,dx=int(sx),dy=int(sy),gain=gain,offset=offset,
                            outside_MAE=float(np.mean(np.abs(predicted[ring]-b[ring]))),
                            outside_correlation=correlation(predicted[ring],b[ring]),
                            remaining_fraction=float(res[active].sum()/denom) if denom>0 else None,
                            largest_residual_component=int(stats[1:,4].max()) if len(stats)>1 else 0))
    return dict(pad=pad,original_active_pixels=int(active.sum()),stages=records)


def grid_match(alternative,target,c,box):
    x0,y0,X,Y=box;r=RULES['search'];border=RULES['exclude_border']
    if min(x0-r,y0-r)<0 or X+r>alternative.shape[1] or Y+r>alternative.shape[0]:
        return dict(box=box,valid=False,reason='image_boundary')
    b=unit(target[y0:Y,x0:X]);mask=np.ones(b.shape,np.float32)
    x,y,w,h=[int(c[k]) for k in ('x','y','w','h')]
    a0,b0=max(x-border,x0)-x0,max(y-border,y0)-y0
    a1,b1=min(x+w+border,X)-x0,min(y+h+border,Y)-y0
    if a1>a0 and b1>b0:mask[b0:b1,a0:a1]=0
    selected=b[mask>0].astype(np.float64)
    if len(selected)<100 or selected.std()<.025:
        return dict(box=box,valid=False,reason='insufficient_texture')
    area=unit(alternative[y0-r:Y+r,x0-r:X+r]);n=float(mask.sum())
    bc=(b-float(selected.mean()))*mask;bn=float(((selected-selected.mean())**2).sum())
    sums=cv2.matchTemplate(area,mask,cv2.TM_CCORR);squares=cv2.matchTemplate(area*area,mask,cv2.TM_CCORR)
    numerator=cv2.matchTemplate(area,bc,cv2.TM_CCORR);denominator=np.sqrt(np.maximum(squares-sums*sums/n,0)*bn)
    scores=np.divide(numerator,denominator,out=np.full(numerator.shape,-1.,np.float32),where=denominator>1e-8)
    iy,ix=np.unravel_index(np.argmax(scores),scores.shape);dx,dy=int(ix-r),int(iy-r)
    a=unit(alternative[y0+dy:Y+dy,x0+dx:X+dx]);score=correlation(a[mask>0],b[mask>0]);gain,offset=fit_exposure(a,b,mask>0)
    return dict(box=box,valid=True,score=score,dx=dx,dy=dy,gain=gain,offset=offset,
                search_boundary=max(abs(dx),abs(dy))==r,
                reliable=score>=RULES['minimum_correlation'] and max(abs(dx),abs(dy))<r,
                candidate_pixels_used=False)


def diagnose(original_reference,target,candidate,alternative,selection):
    from enclosure_rescue5r import geometry
    row=dict(candidate_id=candidate['id'],mode='diagnostic_only',recommendation='retain',
             automatic_exclusion_allowed=False)
    core=geometry(target,candidate) if max(candidate['w'],candidate['h'])<=RULES['maximum_candidate_side'] else None
    if core is not None:return dict(row,advice='protect_independent_object',core=core)
    if alternative is None or not selection.get('selected_views'):
        return dict(row,advice='no_eligible_reference_or_outside_review_scope')
    views=selection['selected_views'];row['selected_reference_id']=selection['selected_reference_id']
    row['ablation']=[ablation(original_reference,alternative,target,candidate,v['pad'],v['dx'],v['dy']) for v in views]
    x,y,w,h=[int(candidate[k]) for k in ('x','y','w','h')]
    xx=np.linspace(x-GRID_PADDING,x+w+GRID_PADDING,GRID_DIVISIONS+1).astype(int)
    yy=np.linspace(y-GRID_PADDING,y+h+GRID_PADDING,GRID_DIVISIONS+1).astype(int)
    grid=[]
    for i in range(GRID_DIVISIONS):
        for j in range(GRID_DIVISIONS):
            box=[int(xx[j]),int(yy[i]),int(xx[j+1]),int(yy[i+1])]
            grid.append(dict(grid_match(alternative,target,candidate,box),cell=f'{i+1}-{j+1}'))
    reliable=[g for g in grid if g.get('reliable')]
    spread={k:max(g[k] for g in reliable)-min(g[k] for g in reliable) for k in ('dx','dy')} if len(reliable)>1 else None
    row.update(grid=grid,reliable_offset_spread=spread,
               advice='inspect_structure_state_and_separate_registration_anchors',
               limitation='Image correspondence differences do not establish physical component identity, pose or defect label')
    if selection.get('correspondence_passed'):
        row['advice']='inspect_residual_after_matched_context'
    return row
