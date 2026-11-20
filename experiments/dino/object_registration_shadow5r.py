"""Visible-region instances and bounded object-wise registration, shadow only.

Stable X-ray intensity regions are not reconstructed physical layers. Unknown
overlap, part identity and normality remain unknown even after a successful fit.
"""
import cv2
import numpy as np
from structure_shadow5r import RULES
from structure_cause_shadow5r import correlation, fit_exposure
from split_registration_shadow5r import warp, transform_points
from ok_reference_shadow5r import unit

VERSION='5r-visible-object-shadow-20261120'
LEVELS=(.2,.3,.4,.5)
STABILITY_IOU=.8
ROI_PAD=96
SUPPORT_RADII=(4,8)
HOLDOUT_BLOCK=4


def iou(a,b):
    return float(np.count_nonzero(a&b)/max(np.count_nonzero(a|b),1))


def segment(image,c):
    x,y,w,h=[int(c[k]) for k in ('x','y','w','h')]
    x0,y0=max(0,x-ROI_PAD),max(0,y-ROI_PAD);X,Y=min(image.shape[1],x+w+ROI_PAD),min(image.shape[0],y+h+ROI_PAD)
    roi=unit(image[y0:Y,x0:X]);levels=[];border_count=0
    for cutoff in LEVELS:
        n,labels,stats,_=cv2.connectedComponentsWithStats((roi<cutoff).astype('uint8'))
        regions=[]
        for i in range(1,n):
            a,b,u,v,area=map(int,stats[i])
            if area<RULES['minimum_component_area']:continue
            if a==0 or b==0 or a+u==roi.shape[1] or b+v==roi.shape[0]:border_count+=1;continue
            regions.append(dict(box=[a+x0,b+y0,u,v],area=area,cutoff=cutoff,mask=labels==i))
        levels.append(regions)
    stable=[];unresolved_merges=[]
    for lo,hi in zip(levels,levels[1:]):
        for a in lo:
            matches=[(iou(a['mask'],b['mask']),b) for b in hi]
            if not matches:continue
            score,b=max(matches,key=lambda z:z[0])
            if score<STABILITY_IOU:continue
            if any(iou(a['mask'],q['mask'])>=STABILITY_IOU for q in stable):continue
            if any(np.any(a['mask']&q['mask']) for q in stable):
                unresolved_merges.append(dict(box=a['box'],thresholds=[a['cutoff'],b['cutoff']],reason='merged_with_existing_visible_core'))
                continue
            stable.append(dict(a,thresholds=[a['cutoff'],b['cutoff']],stability_iou=score,
                               semantic_identity_confirmed=False,normal_state_confirmed=False))
    stable.sort(key=lambda r:(r['box'][1],r['box'][0],r['area']))
    for i,r in enumerate(stable,1):r['object_id']=i
    union=np.zeros(roi.shape,bool)
    for r in stable:union|=r['mask']
    q=union[y-y0:y-y0+h,x-x0:x-x0+w]
    return dict(box=[x0,y0,X,Y],objects=stable,border_components_unresolved=border_count,
                unresolved_merged_regions=unresolved_merges,
                query_visible_coverage=float(q.mean()),segmentation_scope='stable visible dark regions; not physical layer separation')


def public_segments(seg):
    return dict(seg,objects=[{k:v for k,v in obj.items() if k!='mask'} for obj in seg['objects']])


def fit_object(reference,target,c,seg,obj,ref_seg,ref_obj,radius):
    """Fit only target object's visible support; exclude all other segmented cores."""
    r=RULES['search'];x,y,w,h=[int(c[k]) for k in ('x','y','w','h')]
    a,b,u,v=obj['box'];x0,y0,X,Y=a-radius,b-radius,a+u+radius,b+v+radius
    record=dict(valid=False,support_radius=radius,box=[x0,y0,X,Y])
    if min(x0-r,y0-r)<0 or X+r>reference.shape[1] or Y+r>reference.shape[0]:return dict(record,reason='image_boundary')
    sx,sy,sX,sY=seg['box'];local=obj['mask'][b-sy:b-sy+v,a-sx:a-sx+u]
    mask=np.zeros((v+2*radius,u+2*radius),np.uint8);mask[radius:radius+v,radius:radius+u]=local
    mask=cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*radius+1,2*radius+1)))>0
    # Other visible cores must not steer this object's registration.
    for other in seg['objects']:
        if other['object_id']==obj['object_id']:continue
        ox,oy=max(x0,sx),max(y0,sy);oX,oY=min(X,sX),min(Y,sY)
        if oX>ox and oY>oy:mask[oy-y0:oY-y0,ox-x0:oX-x0]&=~other['mask'][oy-sy:oY-sy,ox-sx:oX-sx]
    yy,xx=np.mgrid[y0:Y,x0:X];border=RULES['exclude_border']
    excluded=(xx>=x-border)&(xx<x+w+border)&(yy>=y-border)&(yy<y+h+border)
    parity=((xx//HOLDOUT_BLOCK+yy//HOLDOUT_BLOCK)%2)==0
    train=mask&~excluded&parity;held=mask&~excluded&~parity;actual=unit(target[y0:Y,x0:X])
    if min(train.sum(),held.sum())<100 or actual[train].std()<.025 or actual[held].std()<.025:
        return dict(record,reason='insufficient_independent_visible_support')
    py,px=np.where(mask);corners=np.array([[px.min(),py.min()],[px.max(),py.min()],[px.max(),py.max()],[px.min(),py.max()]],np.float64);centre=corners.mean(axis=0);extent=float(np.linalg.norm(corners-centre,axis=1).max())
    limit=np.degrees(2*np.arcsin(min(1.,r/max(2*extent,1))))
    area=unit(reference[y0-r:Y+r,x0-r:X+r]);weights=train.astype('float32');n=float(weights.sum());values=actual[train].astype('float64');bc=(actual-float(values.mean()))*weights;bn=float(((values-values.mean())**2).sum())
    shifts=np.stack(np.meshgrid(np.arange(-r,r+1),np.arange(-r,r+1)),axis=-1).reshape(-1,2);best=None
    for angle in np.linspace(-limit,limit,2*r+1):
        rot=cv2.getRotationMatrix2D(tuple(centre+r),float(angle),1.);rotated=cv2.warpAffine(area,rot,(area.shape[1],area.shape[0]),flags=cv2.INTER_LINEAR|cv2.WARP_INVERSE_MAP)
        sums=cv2.matchTemplate(rotated,weights,cv2.TM_CCORR);squares=cv2.matchTemplate(rotated*rotated,weights,cv2.TM_CCORR);num=cv2.matchTemplate(rotated,bc,cv2.TM_CCORR);den=np.sqrt(np.maximum(squares-sums*sums/n,0)*bn);scores=np.divide(num,den,out=np.full(num.shape,-2.,np.float32),where=den>1e-8)
        R=rot[:,:2];base=(corners-centre)@R.T+centre;moved=base[None]+(shifts@R.T)[:,None];motions=np.abs(moved-corners[None]).max(axis=(1,2)).reshape(scores.shape);scores[motions>r]=-2
        iy,ix=np.unravel_index(np.argmax(scores),scores.shape);score=float(scores[iy,ix])
        if best is None or score>best[0]:best=(score,float(angle),shifts[iy*(2*r+1)+ix],R,float(motions[iy,ix]))
    score,angle,shift,R,motion=best
    if score<=-1:return dict(record,reason='no_bounded_transform')
    origin=np.array([x0,y0]);matrix=np.column_stack((R,centre-R@centre+R@shift+origin-R@origin));aligned=warp(reference,matrix,[x0,y0,X,Y]);gain,offset=fit_exposure(aligned,actual,train)
    # Confirm the transformation maps this core to the proposed reference core.
    tx,ty=seg['box'][:2];qy,qx=np.where(obj['mask']);points=np.column_stack((qx+tx,qy+ty));mapped=np.unique(np.rint(transform_points(matrix,points)).astype(int),axis=0);rx,ry,rX,rY=ref_seg['box'];valid=(mapped[:,0]>=rx)&(mapped[:,0]<rX)&(mapped[:,1]>=ry)&(mapped[:,1]<rY);inside=np.zeros(len(mapped),bool);inside[valid]=ref_obj['mask'][mapped[valid,1]-ry,mapped[valid,0]-rx]
    inter=int(inside.sum());mask_iou=inter/max(len(mapped)+ref_obj['area']-inter,1)
    training=correlation(aligned[train],actual[train]);heldout=correlation(aligned[held],actual[held])
    accepted=motion<RULES['search'] and heldout>=RULES['minimum_correlation'] and RULES['gain_bounds'][0]<=gain<=RULES['gain_bounds'][1] and mask_iou>=STABILITY_IOU
    return dict(record,valid=True,matrix=matrix.tolist(),angle_degrees=angle,maximum_motion=motion,
                training_correlation=training,heldout_correlation=heldout,gain=gain,offset=offset,mask_iou=mask_iou,
                accepted_geometry=bool(accepted),candidate_pixels_used=False,train_pixels=int(train.sum()),heldout_pixels=int(held.sum()))


def review(original_reference,target,c,alternative,selection):
    from enclosure_rescue5r import geometry
    row=dict(candidate_id=c['id'],recommendation='retain',mode='shadow_only',normal_state_confirmed=False,automatic_exclusion_allowed=False)
    if max(c['w'],c['h'])>RULES['maximum_candidate_side']:return dict(row,reason='outside_review_size')
    core=geometry(target,c)
    if core is not None:return dict(row,reason='independent_object_protected',core=core)
    if alternative is None:return dict(row,reason='no_compatible_OK_reference')
    ts,rs=segment(target,c),segment(alternative,c);pairs=[]
    for t in ts['objects']:
        tc=np.array(t['box'][:2])+np.array(t['box'][2:])/2
        for r in rs['objects']:
            rc=np.array(r['box'][:2])+np.array(r['box'][2:])/2
            if np.max(np.abs(tc-rc))>RULES['search']:continue
            fits=[fit_object(alternative,target,c,ts,t,rs,r,p) for p in SUPPORT_RADII]
            rank=min(f['training_correlation'] for f in fits) if all(f['valid'] and f['mask_iou']>=STABILITY_IOU for f in fits) else -2.
            pairs.append(dict(target_id=t['object_id'],reference_id=r['object_id'],fits=fits,rank=rank))
    matches=[]
    for p in pairs:
        if p['rank']<=-1:continue
        left=sorted([q for q in pairs if q['target_id']==p['target_id']],key=lambda q:(-q['rank'],q['reference_id']))
        right=sorted([q for q in pairs if q['reference_id']==p['reference_id']],key=lambda q:(-q['rank'],q['target_id']))
        if p is not left[0] or p is not right[0]:continue
        t=next(t for t in ts['objects'] if t['object_id']==p['target_id']);x,y,w,h=t['box'];points=np.array([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
        disagreement=float(np.abs(transform_points(p['fits'][0]['matrix'],points)-transform_points(p['fits'][1]['matrix'],points)).max())
        matches.append(dict(p,transform_disagreement=disagreement,accepted_geometry=bool(all(f['accepted_geometry'] for f in p['fits']) and disagreement<=RULES['maximum_offset_disagreement'])))
    x,y,w,h=[int(c[k]) for k in ('x','y','w','h')];sx,sy=ts['box'][:2];owners=[]
    for t in ts['objects']:
        coverage=float(t['mask'][y-sy:y-sy+h,x-sx:x-sx+w].mean())
        if coverage>=.5:owners.append(dict(object_id=t['object_id'],query_coverage=coverage))
    row.update(selected_reference_id=selection['selected_reference_id'],target_segmentation=public_segments(ts),reference_segmentation=public_segments(rs),pairs=pairs,matches=matches,query_owners=owners,
               reason='overlap_or_unresolved_query_object' if len(owners)!=1 else 'visible_object_not_confirmed_physical_normal',geometric_evidence_passed=False)
    # No invisible layer reconstruction and no borrowing a neighbour's match.
    if len(owners)!=1:return row
    matched=next((p for p in matches if p['target_id']==owners[0]['object_id'] and p['accepted_geometry']),None)
    if matched is None:return row
    evaluations=[]
    before=np.maximum(unit(original_reference[y:y+h,x:x+w])-unit(target[y:y+h,x:x+w]),0);active=before>RULES['residual_threshold']
    for fit in matched['fits']:
        predicted=warp(alternative,fit['matrix'],[x,y,x+w,y+h])*fit['gain']+fit['offset'];residual=np.maximum(predicted-unit(target[y:y+h,x:x+w]),0);_,_,stats,_=cv2.connectedComponentsWithStats((residual>RULES['residual_threshold']).astype('uint8'))
        evaluations.append(dict(support_radius=fit['support_radius'],remaining_fraction=float(residual[active].sum()/max(float(before[active].sum()),1e-12)) if active.any() else None,largest_residual_component=int(stats[1:,4].max()) if len(stats)>1 else 0))
    passed=all(v['remaining_fraction'] is not None and v['remaining_fraction']<=RULES['maximum_remaining_fraction'] and v['largest_residual_component']<RULES['minimum_component_area'] for v in evaluations)
    row.update(evaluation=evaluations,geometric_evidence_passed=bool(passed),reason='geometry_supported_but_normality_unconfirmed' if passed else 'object_residual_not_explained')
    return row
