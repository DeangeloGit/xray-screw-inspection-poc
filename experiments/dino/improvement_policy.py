"""Image-only 4r experiments. No answer files, filenames or coordinates are read here."""
import os
import hashlib
import cv2
import numpy as np
from dino_paired_optimized import adjusted_image
import overkill_pilot as pilot

VERSION='4r-fragment-consensus-20261106'
RULES=dict(pads=[4,8],target_margin=.04,reference_margin=0.,minimum_object_share=.15,
           preserve_r3_keeps=True,small_part_max_side=18,part_inner_share=.8,part_outer_share=.2,
           wire_min_aspect=4.,wire_match=.7,wire_max_motion=12)


def supplemental(ref,target,mask,predicted,previous):
    """Join nearby 1px-tolerance dark fragments before the small-fragment veto."""
    residual=cv2.erode(predicted,np.ones((3,3),np.uint8))-target
    raw=((residual>.13)&mask).astype('uint8')
    raw=cv2.morphologyEx(raw,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    joined=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    n,labels,stats,_=cv2.connectedComponentsWithStats(joined)
    rows=[]
    for i in range(1,n):
        x,y,w,h,_=map(int,stats[i]);component=(labels[y:y+h,x:x+w]==i)&(raw[y:y+h,x:x+w]>0)
        area=int(component.sum())
        if not (25<=area<=600 and 5<=min(w,h) and max(w,h)<=50 and max(w,h)<=4*min(w,h) and area/(w*h)>=.2):continue
        if float(mask[y:y+h,x:x+w].mean())<.95:continue
        duplicate=False
        for c in previous+rows:
            a,b,u,v=[c[k] for k in ('x','y','w','h')]
            inter=max(0,min(x+w,a+u)-max(x,a))*max(0,min(y+h,b+v)-max(y,b))
            if inter>.25*min(w*h,u*v) and max(w*h,u*v)<3*min(w*h,u*v):duplicate=True;break
        if duplicate:continue
        signed=(predicted-target)[max(0,y-5):y+h+5,max(0,x-5):x+w+5]
        bipolar=float(np.maximum(-signed,0).sum()/max(float(np.maximum(signed,0).sum()),1e-6))
        if bipolar>.7:continue
        rows.append(dict(x=x,y=y,w=w,h=h,area=area,score=round(float(np.percentile(residual[y:y+h,x:x+w][component],90)),4),normal_support=0.,aspect=round(max(w,h)/min(w,h),2),fill=round(area/(w*h),3),bipolar=round(bipolar,3),contrast=round(float(np.median((predicted-target)[y:y+h,x:x+w][component])),4),shape_similarity=0.,recovery='r4_joined_fragments',change_type='experimental_fragment_candidate'))
    # A closing kernel can leave diagonal fragments apart. Also join pairs of
    # small nearby components, bounding the union before it can absorb a board.
    n,labels,stats,_=cv2.connectedComponentsWithStats(raw)
    small=[(i,tuple(map(int,stats[i]))) for i in range(1,n) if 12<=stats[i,4]<40]
    for j,(i,(x,y,w,h,area)) in enumerate(small):
        for ii,(a,b,u,v,aa) in small[j+1:]:
            gapx=max(0,a-x-w,x-a-u);gapy=max(0,b-y-h,y-b-v)
            if max(gapx,gapy)>8:continue
            x0,y0=min(x,a),min(y,b);X,Y=max(x+w,a+u),max(y+h,b+v);ww,hh=X-x0,Y-y0
            if max(ww,hh)>32 or min(ww,hh)<5 or max(ww,hh)>3*min(ww,hh):continue
            if (area+aa)/(ww*hh)<.2:continue
            duplicate=False
            for c in previous+rows:
                xx,yy,cw,ch=[c[k] for k in ('x','y','w','h')]
                inter=max(0,min(X,xx+cw)-max(x0,xx))*max(0,min(Y,yy+ch)-max(y0,yy))
                if inter>.25*min(ww*hh,cw*ch) and max(ww*hh,cw*ch)<3*min(ww*hh,cw*ch):duplicate=True;break
            if duplicate:continue
            signed=(predicted-target)[max(0,y0-5):Y+5,max(0,x0-5):X+5]
            bipolar=float(np.maximum(-signed,0).sum()/max(float(np.maximum(signed,0).sum()),1e-6))
            if bipolar>.7:continue
            selected=np.isin(labels[y0:Y,x0:X],[i,ii])
            rows.append(dict(x=x0,y=y0,w=ww,h=hh,area=area+aa,score=round(float(np.percentile(residual[y0:Y,x0:X][selected],90)),4),normal_support=0.,aspect=round(max(ww,hh)/min(ww,hh),2),fill=round((area+aa)/(ww*hh),3),bipolar=round(bipolar,3),contrast=round(float(np.median((predicted-target)[y0:Y,x0:X][selected])),4),shape_similarity=0.,recovery='r4_joined_fragments',change_type='experimental_fragment_candidate'))
    return sorted(rows,key=lambda c:-c['score'])


def scores(snapshot,ref,target,c,pad, *, stop_on_target_failure=False):
    left,right=[im[pilot.select(c,pad)] for im in (ref,target)]
    m=snapshot.manifest;weights=pilot.core_mask(m,left,right)
    if weights is None:return None
    bank=snapshot.feature_bank;n=len(m['example_bank']['screw']['ids']);result=[]
    crops = (right, left) if stop_on_target_failure else (left, right)
    for crop in crops:
        im=adjusted_image(m,crop)
        from engineering_trace import model_image
        model_image(im)
        a=np.asarray(im,np.float32)/255
        a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
        raw=snapshot.session.run(None,{snapshot.session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0]
        v=np.stack([raw[0],raw[1:].mean(axis=0),(raw[1:]*weights[:,None]).sum(axis=0)])
        v/=np.maximum(np.linalg.norm(v,axis=1)[:,None],1e-9)
        similarities=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1],bank[:,0,1]@v[2]]
        margins=[float(np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean()) for s in similarities]
        result.append(dict(whole=margins[0],local=margins[1],focused=margins[2],input_sha256=hashlib.sha256(im.tobytes()).hexdigest()))
        if stop_on_target_failure and len(result) == 1 and not sum(margins)/3 >= .04:
            return dict(target=result[0], reference=dict(
                evaluated=False, reason='target_below_two_crop_threshold'))
    if stop_on_target_failure:
        result.reverse()
    return dict(reference=result[0],target=result[1])


def extra_geometry(ref,target,c):
    # Expand to a brighter contour to identify a tiny corner attached to a large part.
    x,y,w,h=pilot.candidate_box(c);p=32;x0=max(0,x-p);y0=max(0,y-p)
    a=target[y0:y+h+p,x0:x+w+p];inside=np.zeros(a.shape,bool);inside[y-y0:y-y0+h,x-x0:x-x0+w]=True
    features=[]
    for offset in (.12,.22,.32):
        cutoff=min(.9,float(np.median(a[inside]))+offset)
        n,labels,stats,_=cv2.connectedComponentsWithStats((a<cutoff).astype('uint8'))
        mass=np.bincount(labels[inside],minlength=n);mass[0]=0
        if not mass.max():features.append({});continue
        i=int(mass.argmax());xx,yy,ww,hh,area=map(int,stats[i]);component=labels==i
        near=np.zeros(a.shape,bool);near[max(0,y-y0-4):y-y0+h+4,max(0,x-x0-4):x-x0+w+4]=True
        features.append(dict(box=[xx+x0,yy+y0,ww,hh],area=area,near_share=float((near&component).sum()/area),cutoff=cutoff))
    return features


def rejection_rules(ref,target,c,views,geometry):
    """Only checks pilot-added keeps; original r3 keeps are immutable."""
    if not views.get('4') or not views.get('8') or not geometry or not geometry[0]:return [],{}
    t4,t8=views['4']['target'],views['8']['target'];g0=geometry[0];g1=geometry[1]
    w,h=c['w'],c['h'];rules=[];evidence={}
    if (g1 and max(w,h)<=18 and g0['near_share']>.8 and g1['near_share']<.2
            and max(g1['box'][2:])>=3*max(w,h) and t4['whole']<0 and t8['local']<0):
        rules.append('r4_part_boundary')
    if (max(g0['box'][2:])/min(g0['box'][2:])>=4 and t4['whole']<0
            and t4['local']<0 and t8['local']<0):
        match=pilot.measure_match(ref,target,c,2,12);evidence['wire_match']=match
        if match.get('score',0)>=.7 and max(abs(match['dx']),abs(match['dy']))<12:
            rules.append('r4_wire_motion')
    return rules,evidence


def geometry_qualifies(geometry):
    return bool(geometry and geometry[0] and not geometry[0]['near_share'] < .15)


def view_qualifies(pair):
    if pair is None or pair['reference'].get('evaluated') is False:
        return False
    margins = {side: sum(pair[side][k] for k in ('whole','local','focused'))/3
               for side in ('reference','target')}
    return margins['reference'] < 0 and margins['target'] >= .04


def qualifies(views, geometry):
    return geometry_qualifies(geometry) and all(view_qualifies(views.get(p)) for p in ('4', '8'))


def improve(snapshot,ref,target,c,prediction,original_apply):
    """Executable fixed policy, independent of evaluation labels and photo identity."""
    from dino_adapter import paired_decision
    new=c.get('recovery')=='r4_joined_fragments'
    previous=original_apply(snapshot,ref,target,c,prediction) if not new else prediction
    if not new and prediction['filter_recommendation']=='keep' and c.get('recovery')!='overkill_pilot_similarity':
        return previous
    if max(c['w'],c['h'])>80:return previous
    promotion_only = new or previous['filter_recommendation'] != 'keep'
    short_circuit = promotion_only and os.environ.get('XRAY_5R_LOCAL_REVIEW') == '1'
    geometry = extra_geometry(ref, target, c)
    views = {}
    meta = dict(version=VERSION, new_proposal=new, views=views, geometry=geometry, rules=[])
    if short_circuit and not geometry_qualifies(geometry):
        meta['skipped'] = 'geometry_ineligible'
    else:
        for pad in (4, 8):
            value = scores(snapshot, ref, target, c, pad, stop_on_target_failure=short_circuit)
            views[str(pad)] = value
            if short_circuit and not view_qualifies(value):
                if pad == 4:
                    meta['skipped_pads'] = [8]
                break
    if not new and previous['filter_recommendation']=='keep':
        rules,evidence=rejection_rules(ref,target,c,views,geometry);meta.update(rules=rules,filter_evidence=evidence)
        if rules:
            return dict(previous,label='non_screw',action='discard',filter_recommendation='exclude',decision_reason='4r 結構複核：小區域接到大板件或可位移對上的線材結構；排除新增警報',r4_experiment=meta)
        return dict(previous,r4_experiment=meta)
    if qualifies(views,geometry):
        sides=[]
        for side in ('reference','target'):
            values=[sum(views[p][side][k] for k in ('whole','local','focused'))/3 for p in ('4','8')]
            value=max(values) if side=='reference' else min(values)
            sides.append(dict(label='screw' if value>=0 else 'non_screw',screw_margin=value,score_kind='two_crop_minimum_consensus',input_sha256=[views[p][side]['input_sha256'] for p in ('4','8')]))
        meta['promoted']=True
        # Retain the former rules only as history, not as active vetoes.
        updated=dict(previous)
        updated.update(paired_decision(sides[1],sides[0]))
        updated.update(action='manual_review',r4_experiment=meta,decision_reason='4r 雙尺寸重看：兩種取圖皆待測像螺絲、參照不像螺絲，且具有足夠物件範圍；保留')
        if updated.get('overkill_pilot',{}).get('rules'):
            updated['overkill_pilot']=dict(updated['overkill_pilot'],previous_rules=updated['overkill_pilot']['rules'],rules=[])
        return updated
    if new:
        meta['rules']=['r4_no_consensus']
        return dict(previous,label='non_screw',action='discard',filter_recommendation='exclude',decision_reason=('4r 補提候選物件範圍未達門檻，雙尺寸分數未計算' if meta.get('skipped') else '4r 補提候選未通過雙尺寸螺絲共識或物件範圍檢查；排除'),r4_experiment=meta)
    return dict(previous,r4_experiment=meta)
