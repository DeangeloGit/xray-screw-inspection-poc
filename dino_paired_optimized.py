"""Validated contrast/global/local paired DINO; one restricted geometric recheck."""
import hashlib
import numpy as np
from PIL import Image
from dino_adapter import input_image, paired_decision
from detection_runtime import CURRENT

STRATEGY = 'contrast-global-local-half-v1'


def adjusted_image(m, crop):
    im = input_image(m,crop)
    a = np.asarray(im.convert('L'),np.float32)
    low,high = np.percentile(a,[1,99])
    if high-low<1:
        return im.convert('RGB')
    return Image.fromarray(np.rint(np.clip((a-low)/(high-low),0,1)*255).astype('uint8')).convert('RGB')


def features(m, session, im):
    a=np.asarray(im,np.float32)/255
    a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
    raw=np.asarray(session.run(None,{session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0])
    if raw.shape!=(1,257,384) or not np.isfinite(raw).all():
        raise ValueError('DINO 特徵輸出無效')
    v=np.stack([raw[0,0],raw[0,1:].mean(axis=0)])
    norms=np.linalg.norm(v,axis=1)[:,None]
    if np.any(norms<1e-8):
        raise ValueError('DINO 特徵向量無效')
    return v/norms


def example_features(m, session, crop):
    im=adjusted_image(m,crop)
    views=[]
    for flip in (False,True):
        a=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if flip else im
        for angle in (0,90,180,270):
            views.append(features(m,session,a.rotate(angle)))
    return np.stack(views)


def validate_bank(m, bank):
    ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids']
    if bank.shape!=(len(ids),8,2,384) or not np.isfinite(bank).all() or not np.allclose(np.linalg.norm(bank,axis=-1),1,atol=.001):
        raise ValueError('DINO 整體／局部範例特徵無效')
    bank.flags.writeable=False
    return bank


def classify(m,session,crop,bank):
    im=adjusted_image(m,crop)
    v=features(m,session,im)
    groups=m['example_bank'];n=len(groups['screw']['ids'])
    scores=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
    margins=[];evidence={}
    for title,s in zip(('whole','local'),scores):
        margins.append(float(np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean()))
        evidence[title]={}
        for label,values in (('screw',s[:n]),('normal',s[n:])):
            indices=np.argsort(values)[-3:][::-1]
            evidence[title][label]=dict(similarity=float(values[indices].mean()),neighbors=[groups[label]['ids'][i] for i in indices])
    margin=sum(margins)/2
    return dict(label='screw' if margin>=0 else 'non_screw',probabilities=None,screw_margin=margin,
                whole_margin=margins[0],local_margin=margins[1],dino_evidence=evidence,
                input_sha256=hashlib.sha256(im.tobytes()).hexdigest(),feature_strategy=STRATEGY,
                score_kind='cosine_similarity',filter_recommendation='keep' if margin>=0 else 'exclude')


def classify_pair(m,session,crop,reference_crop,bank):
    if reference_crop is None or not reference_crop.size:
        raise ValueError('雙圖 DINO 缺少同位置參照小圖，保留候選供人工確認')
    # Keep reference then target inference order identical to the measured pipeline.
    reference=classify(m,session,reference_crop,bank)
    target=classify(m,session,crop,bank)
    return paired_decision(target,reference)


def classify_candidate(snapshot,target,reference,candidate):
    context=CURRENT.get()
    arrays=context.arrays(reference,target) if context else [(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in (reference,target)]
    x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
    region=(slice(max(0,y-12),y+h+12),slice(max(0,x-12),x+w+12))
    result=snapshot.classify(arrays[1][region],reference_crop=arrays[0][region])
    pair=result.get('paired_evidence',{})
    if result['status']!='active' or not all(pair.get(side,{}).get('label')=='screw' for side in ('reference','target')):
        return result
    from paired_geometry import extract
    ex=extract(*arrays,candidate)
    valid=False;box=None
    if ex.get('valid'):
        bx,by,s=ex['box'];box=[bx-2,by-2,bx+s+2,by+s+2];e=32
        search=[max(e,x-e),max(e,y-e),min(reference.shape[1]-e,x+w+e),min(reference.shape[0]-e,y+h+e)]
        ox,oy,ow,oh=ex['object_box']
        touch=ox<=search[0] or oy<=search[1] or ox+ow>=search[2] or oy+oh>=search[3]
        valid=ex['metrics']['context_reliable'] and ex['area']>=12 and not touch and min(box)>=0 and box[2]<=reference.shape[1] and box[3]<=reference.shape[0]
    if valid:
        checked=snapshot.classify(arrays[1][box[1]:box[3],box[0]:box[2]],reference_crop=arrays[0][box[1]:box[3],box[0]:box[2]])
        checked['paired_recheck']=dict(performed=True,box=box,initial=pair)
        return checked
    result['paired_recheck']=dict(performed=False,reason='geometry_not_eligible')
    return result
