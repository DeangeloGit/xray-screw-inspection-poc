"""Bounded independent rigid registration of spatial part hypotheses.

No semantic part/normal label is inferred. No official result or exclusion is
produced. Candidate pixels are withheld from fitting; checkerboard blocks are
held out to check the fit. Motion/gain/correlation/residual gates are unchanged.
"""
import cv2
import numpy as np
from structure_shadow5r import RULES
from structure_cause_shadow5r import correlation, fit_exposure
from ok_reference_shadow5r import unit

VERSION='5r-split-rigid-shadow-20261120'
FIT_PADS=(64,96)
HOLDOUT_BLOCK=4


def separator(reference,c):
    x,y,w,h=[int(c[k]) for k in ('x','y','w','h')]
    p=max(RULES['pads']);context=FIT_PADS[-1]
    left,right=max(0,x-p),min(reference.shape[1],x+p+1)
    profile=np.median(unit(reference[max(0,y-context):min(reference.shape[0],y+h+context),left:right]),axis=0)
    cut=int(left+np.argmax(profile))
    return dict(x=cut,method='bright_vertical_separator_in_OK_reference',
                semantic_identity_confirmed=False,normal_state_confirmed=False,
                peak=float(profile.max()),median=float(np.median(profile)))


def transform_points(matrix,points):
    return np.asarray(points)@np.asarray(matrix)[:,:2].T+np.asarray(matrix)[:,2]


def warp(reference,matrix,box):
    x0,y0,X,Y=box
    yy,xx=np.mgrid[y0:Y,x0:X].astype('float32');m=np.asarray(matrix)
    mx=m[0,0]*xx+m[0,1]*yy+m[0,2];my=m[1,0]*xx+m[1,1]*yy+m[1,2]
    return unit(cv2.remap(reference,mx.astype('float32'),my.astype('float32'),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0))


def fit_part(reference,target,c,cut,pad,side):
    x,y,w,h=[int(c[k]) for k in ('x','y','w','h')];r=RULES['search'];b=RULES['exclude_border']
    x0,y0,X,Y=x-pad,y-pad,x+w+pad,y+h+pad;box=[x0,y0,X,Y]
    record=dict(side=side,pad=pad,box=box,valid=False)
    if min(x0-r,y0-r)<0 or X+r>reference.shape[1] or Y+r>reference.shape[0]:return dict(record,reason='image_boundary')
    yy,xx=np.mgrid[y0:Y,x0:X]
    part=(xx<cut) if side=='left' else (xx>=cut)
    if not part.any():return dict(record,reason='empty_part')
    py,px=np.where(part);corners=np.array([[px.min(),py.min()],[px.max(),py.min()],[px.max(),py.max()],[px.min(),py.max()]],np.float64)
    centre=corners.mean(axis=0);radius=float(np.linalg.norm(corners-centre,axis=1).max())
    excluded=(xx>=x-b)&(xx<x+w+b)&(yy>=y-b)&(yy<y+h+b)
    parity=((xx//HOLDOUT_BLOCK+yy//HOLDOUT_BLOCK)%2)==0
    train=part&~excluded&parity;held=part&~excluded&~parity
    target_roi=unit(target[y0:Y,x0:X])
    if min(train.sum(),held.sum())<100 or target_roi[train].std()<.025 or target_roi[held].std()<.025:
        return dict(record,reason='insufficient_texture')
    # Bound rotation by the same maximum pixel motion as translation.
    limit=np.degrees(2*np.arcsin(min(1.,r/max(2*radius,1))))
    angles=np.linspace(-limit,limit,2*r+1)
    area=unit(reference[y0-r:Y+r,x0-r:X+r]);mask=train.astype('float32');n=float(mask.sum())
    values=target_roi[train].astype('float64');mean=float(values.mean());bc=(target_roi-mean)*mask;bn=float(((values-mean)**2).sum())
    shifts=np.stack(np.meshgrid(np.arange(-r,r+1),np.arange(-r,r+1)),axis=-1).reshape(-1,2)
    best=None
    for angle in angles:
        rot=cv2.getRotationMatrix2D(tuple(centre+r),float(angle),1.)
        rotated=cv2.warpAffine(area,rot,(area.shape[1],area.shape[0]),flags=cv2.INTER_LINEAR|cv2.WARP_INVERSE_MAP)
        sums=cv2.matchTemplate(rotated,mask,cv2.TM_CCORR);squares=cv2.matchTemplate(rotated*rotated,mask,cv2.TM_CCORR)
        numerator=cv2.matchTemplate(rotated,bc,cv2.TM_CCORR);denom=np.sqrt(np.maximum(squares-sums*sums/n,0)*bn)
        scores=np.divide(numerator,denom,out=np.full(numerator.shape,-2.,np.float32),where=denom>1e-8)
        R=rot[:,:2];base=(corners-centre)@R.T+centre
        moved=base[None,:,:]+(shifts@R.T)[:,None,:]
        maximum=np.abs(moved-corners[None,:,:]).max(axis=(1,2)).reshape(scores.shape)
        scores[maximum>r]=-2
        iy,ix=np.unravel_index(np.argmax(scores),scores.shape)
        score=float(scores[iy,ix])
        if best is None or score>best[0]:best=(score,float(angle),shifts[iy*(2*r+1)+ix],R,maximum[iy,ix])
    score,angle,shift,R,motion=best
    if score<=-1:return dict(record,reason='no_bounded_transform')
    origin=np.array([x0,y0],np.float64)
    translation=centre-R@centre+R@shift+origin-R@origin
    matrix=np.column_stack((R,translation));aligned=warp(reference,matrix,box)
    gain,offset=fit_exposure(aligned,target_roi,train)
    held_corr=correlation(aligned[held],target_roi[held]);training_corr=correlation(aligned[train],target_roi[train])
    valid=bool(motion<r and held_corr>=RULES['minimum_correlation'] and RULES['gain_bounds'][0]<=gain<=RULES['gain_bounds'][1])
    return dict(record,valid=True,matrix=matrix.tolist(),angle_degrees=angle,maximum_motion=float(motion),
                training_correlation=training_corr,heldout_correlation=held_corr,gain=gain,offset=offset,
                accepted_geometry=valid,train_pixels=int(train.sum()),heldout_pixels=int(held.sum()),
                candidate_pixels_used=False,shape_deformation=False)


def evaluate(original_reference,alternative,target,c,fit,pad,cut,side):
    x,y,w,h=[int(c[k]) for k in ('x','y','w','h')];b=RULES['exclude_border'];box=[x-pad,y-pad,x+w+pad,y+h+pad]
    predicted=warp(alternative,fit['matrix'],box)*fit['gain']+fit['offset'];actual=unit(target[box[1]:box[3],box[0]:box[2]])
    yy,xx=np.mgrid[box[1]:box[3],box[0]:box[2]]
    ring=((xx<cut) if side=='left' else (xx>=cut))&~((xx>=x-b)&(xx<x+w+b)&(yy>=y-b)&(yy<y+h+b))
    corr=correlation(predicted[ring],actual[ring]) if ring.sum()>=100 and actual[ring].std()>=.025 else None
    before=np.maximum(unit(original_reference[y:y+h,x:x+w])-unit(target[y:y+h,x:x+w]),0);active=before>RULES['residual_threshold']
    residual=np.maximum(predicted[pad:pad+h,pad:pad+w]-actual[pad:pad+h,pad:pad+w],0)
    _,_,stats,_=cv2.connectedComponentsWithStats((residual>RULES['residual_threshold']).astype('uint8'))
    return dict(pad=pad,context_correlation=corr,remaining_fraction=float(residual[active].sum()/max(float(before[active].sum()),1e-12)) if active.any() else None,
                largest_residual_component=int(stats[1:,4].max()) if len(stats)>1 else 0)


def review(original_reference,target,candidate,alternative,selection):
    from enclosure_rescue5r import geometry
    row=dict(candidate_id=candidate['id'],mode='shadow_only',recommendation='retain',
             normal_state_confirmed=False,automatic_exclusion_allowed=False)
    if max(candidate['w'],candidate['h'])>RULES['maximum_candidate_side']:return dict(row,reason='outside_review_size')
    core=geometry(target,candidate)
    if core is not None:return dict(row,reason='independent_object_protected',core=core)
    if alternative is None:return dict(row,reason='no_compatible_OK_reference')
    split=separator(alternative,candidate);cut=split['x'];x,y,w,h=[int(candidate[k]) for k in ('x','y','w','h')]
    owner='left' if x+w<=cut else 'right' if x>=cut else None
    row.update(separator=split,candidate_part=owner,selected_reference_id=selection['selected_reference_id'])
    fits=[]
    for pad in FIT_PADS:
        sides={side:fit_part(alternative,target,candidate,cut,pad,side) for side in ('left','right')}
        fits.append(dict(pad=pad,parts=sides))
    row['fits']=fits
    if owner is None:return dict(row,reason='candidate_crosses_unconfirmed_separator',geometric_evidence_passed=False)
    selected=[f['parts'][owner] for f in fits]
    if not all(f['valid'] for f in selected):return dict(row,reason='insufficient_fit',geometric_evidence_passed=False)
    corners=np.array([[x,y],[x+w,y],[x+w,y+h],[x,y+h]],np.float64)
    consistency=float(np.max(np.abs(transform_points(selected[0]['matrix'],corners)-transform_points(selected[1]['matrix'],corners))))
    views=[dict(fit_pad=f['pad'],views=[evaluate(original_reference,alternative,target,candidate,f,p,cut,owner) for p in RULES['pads']]) for f in selected]
    passed=all(f['accepted_geometry'] for f in selected) and consistency<=RULES['maximum_offset_disagreement'] and all(
        v['context_correlation'] is not None and v['context_correlation']>=RULES['minimum_correlation'] and
        v['remaining_fraction'] is not None and v['remaining_fraction']<=RULES['maximum_remaining_fraction'] and
        v['largest_residual_component']<RULES['minimum_component_area'] for rowviews in views for v in rowviews['views'])
    row.update(transform_disagreement=consistency,evaluation=views,geometric_evidence_passed=bool(passed),
               reason='geometry_supported_but_structure_state_unconfirmed' if passed else 'split_registration_insufficient')
    return row
