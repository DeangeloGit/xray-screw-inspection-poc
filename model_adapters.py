"""Additional candidate classifiers. Scores never replace human decisions."""
import cv2
import numpy as np
from PIL import Image

TIGHT_PREPROCESSING = 'aligned-gray-tight12-v1'
CLIP_DECISION_POLICY = 'non-screw-auto-filter-v2'
CLIP_REVIEW_MARGIN = .01


def clip_decision(labels, scores):
    """Do not turn a near-tie into non-screw evidence; scores are not probabilities."""
    scores = np.asarray(scores, dtype=float)
    if scores.shape != (len(labels),) or len(labels)<2 or labels[0]!='screw' or not np.isfinite(scores).all():
        raise ValueError('CLIP 類別分數無效')
    raw_label = labels[int(scores.argmax())]
    margin = float(scores[0]-max(scores[1:]))
    near_tie = raw_label != 'screw' and margin >= -CLIP_REVIEW_MARGIN - 1e-7
    label = 'uncertain' if near_tie else raw_label
    return dict(label=label, raw_label=raw_label, screw_margin=margin,
                review_margin=CLIP_REVIEW_MARGIN, decision_policy=CLIP_DECISION_POLICY,
                filter_recommendation='review' if near_tie else 'keep' if label=='screw' else 'non_screw_suggestion',
                decision_reason='螺絲與其他類別分數接近，保留候選' if near_tie else '螺絲類別分數最高' if label=='screw' else '非螺絲類別分數領先超過門檻，自動排除候選')


def refine_cable_shape(manifest, vector, decision, scores):
    """Resolve cable/screw ambiguity using target-image appearance, never a reference."""
    shape = manifest.get('cable_shape')
    if not shape or decision['label'] != 'uncertain' or decision['raw_label'] != 'cable':
        return decision
    similarity = float(np.asarray(shape['embedding'], np.float32) @ vector)
    margin = float(scores[0] - similarity)
    evidence = dict(method='clip-cable-shape-v1', similarity=similarity,
                    screw_margin=margin, initial_screw_margin=decision['screw_margin'])
    if margin < -CLIP_REVIEW_MARGIN - 1e-7:
        return dict(decision, label='cable', screw_margin=margin,
                    filter_recommendation='non_screw_suggestion', shape_evidence=evidence,
                    decision_reason='CLIP 線材外型描述領先螺絲超過原門檻，自動排除')
    return dict(decision, shape_evidence=evidence)


def refine_screw_examples(manifest, vector, decision):
    """Positive visual evidence can retain a screw; unfamiliar examples never delete it."""
    bank = manifest.get('screw_examples')
    if not bank:
        return decision
    evidence = dict(method='clip-visual-screw-bank-v1')
    for label in ('screw', 'normal'):
        scores = np.asarray(bank[label]['embeddings'], np.float32) @ vector
        indexes = np.argsort(scores)[-bank['neighbors']:][::-1]
        evidence[label+'_similarity'] = float(scores[indexes].mean())
        evidence[label+'_neighbors'] = [bank[label]['ids'][i] for i in indexes]
    evidence['margin'] = evidence['screw_similarity']-evidence['normal_similarity']
    evidence['supported'] = (evidence['margin'] >= bank['margin'] and
                             evidence['screw_similarity'] >= bank['minimum_similarity'])
    if evidence['supported'] and decision['label'] != 'screw':
        return dict(decision, label='screw', filter_recommendation='keep',
                    screw_example_evidence=evidence,
                    decision_reason='CLIP 外型更接近已標記螺絲範例，保留候選')
    return dict(decision, screw_example_evidence=evidence)



def validate(manifest, session):
    m = manifest
    size = m.get('input_size')
    if not isinstance(size, list) or len(size)!=2 or any(type(n) is not int or not 32<=n<=1536 for n in size):
        raise ValueError('模型輸入尺寸需介於 32 與 1536')
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs)!=1 or inputs[0].type!='tensor(float)' or len(inputs[0].shape)!=4:
        raise ValueError('需要單一 float32 NCHW 輸入')
    expected=[1,3,*size]
    if any(isinstance(a,int) and a!=b for a,b in zip(inputs[0].shape,expected)):
        raise ValueError('模型輸入尺寸與設定不符')
    if len(outputs)!=1 or outputs[0].type!='tensor(float)':
        raise ValueError('需要單一 float32 輸出')
    labels=m.get('classes')
    if not isinstance(labels,list) or not 1<=len(labels)<=1000 or any(not isinstance(x,str) or not x.strip() for x in labels) or len(set(labels))!=len(labels):
        raise ValueError('類別名稱需為不重複的非空文字')
    output=np.asarray(session.run(None,{inputs[0].name:np.zeros(expected,np.float32)})[0])
    if not np.isfinite(output).all():
        raise ValueError('模型測試輸出不是有限數值')
    if m['backend']=='clip_onnx':
        text=np.asarray(m.get('text_embeddings'),np.float32)
        if len(labels)<2 or labels[0]!='screw' or size!=[224,224] or output.shape!=(1,512) or text.shape!=(len(labels),512) or not np.isfinite(text).all() or not np.allclose(np.linalg.norm(text,axis=1),1,atol=.001):
            raise ValueError('CLIP 影像／文字向量契約不符')
        for name in ('mean','std'):
            a=np.asarray(m.get(name),float)
            if a.shape!=(3,) or not np.isfinite(a).all() or (name=='std' and np.any(a<=0)):
                raise ValueError('CLIP 正規化設定不符')
        if 'cable_shape' in m:
            shape=m['cable_shape']; vector=np.asarray(shape.get('embedding'),np.float32)
            if shape.get('method')!='clip-cable-shape-v1' or 'cable' not in labels or vector.shape!=(512,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector),1,atol=.001):
                raise ValueError('CLIP 線材外型向量無效')
        if 'screw_examples' in m:
            bank=m['screw_examples']
            if bank.get('method')!='clip-visual-screw-bank-v1' or type(bank.get('neighbors')) is not int or not 1<=bank['neighbors']<=10 or not .001<=bank.get('margin',0)<=1 or not 0<=bank.get('minimum_similarity',-1)<=1:
                raise ValueError('CLIP 螺絲範例設定無效')
            for label in ('screw','normal'):
                group=bank.get(label,{})
                vectors=np.asarray(group.get('embeddings'),np.float32);ids=group.get('ids',[])
                if vectors.ndim!=2 or vectors.shape[1]!=512 or not bank['neighbors']<=len(ids)==len(vectors)<=2000 or not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors,axis=1),1,atol=.001):
                    raise ValueError('CLIP 螺絲範例特徵無效')
    elif m['backend']=='yolo_onnx':
        if output.ndim!=3 or output.shape[0]!=1 or output.shape[1]!=4+len(labels) or output.shape[2]<1:
            raise ValueError('目前支援 YOLO 原始偵測輸出 [1,4+類別數,N]，不支援分割或 end-to-end 輸出')
        index=m.get('screw_class_id')
        if type(index) is not int or not 0<=index<len(labels) or not .01<=m.get('confidence',0)<=.99:
            raise ValueError('螺絲類別編號或信心門檻無效')
        if np.any(output[:,4:]<0) or np.any(output[:,4:]>1):
            raise ValueError('YOLO 類別分數需在 0 到 1 之間')


def classify(manifest, session, crop):
    m=manifest
    if m['backend']=='clip_onnx':
        image=Image.fromarray(np.rint(np.clip(crop,0,1)*255).astype('uint8')).convert('RGB')
        w,h=image.size
        size=(224,int(224*h/w)) if w<=h else (int(224*w/h),224)
        image=image.resize(size,Image.Resampling.BICUBIC)
        left,top=(image.width-224)//2,(image.height-224)//2
        values=np.asarray(image.crop((left,top,left+224,top+224)),np.float32)/255
        values=(values-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
        tensor=values.transpose(2,0,1)[None]
        vector=np.asarray(session.run(None,{session.get_inputs()[0].name:tensor})[0])[0]
        if vector.shape!=(512,) or not np.isfinite(vector).all() or np.linalg.norm(vector)<1e-8:
            raise ValueError('CLIP 推論向量無效')
        vector=vector/np.linalg.norm(vector)
        scores=np.asarray(m['text_embeddings'],np.float32)@vector
        decision=refine_cable_shape(m, vector, clip_decision(m['classes'], scores), scores)
        decision=refine_screw_examples(m, vector, decision)
        return dict(**decision, probabilities=None,
                    similarities=dict(zip(m['classes'],map(float,scores))),
                    score_kind='cosine_similarity')
    height,width=m['input_size']
    scale=min(width/crop.shape[1],height/crop.shape[0])
    resized=cv2.resize(crop,(round(crop.shape[1]*scale),round(crop.shape[0]*scale)))
    canvas=np.full((height,width),114/255,np.float32)
    y,x=round((height-resized.shape[0])/2-.1),round((width-resized.shape[1])/2-.1)
    canvas[y:y+resized.shape[0],x:x+resized.shape[1]]=resized
    tensor=np.repeat(canvas[None,None],3,axis=1)
    output=np.asarray(session.run(None,{session.get_inputs()[0].name:tensor})[0])
    if output.ndim!=3 or output.shape[0]!=1 or output.shape[1]!=4+len(m['classes']) or not np.isfinite(output).all():
        raise ValueError('YOLO 推論輸出無效')
    scores=output[0,4:].max(axis=1)
    if np.any(scores<0) or np.any(scores>1):
        raise ValueError('YOLO 分數超出範圍')
    screw=float(scores[m['screw_class_id']])
    label='screw' if screw>=m['confidence'] else 'uncertain'
    return dict(label=label,probabilities=None,score_kind='detector_confidence',
                screw_score=screw,confidence_threshold=m['confidence'],
                class_scores=dict(zip(m['classes'],map(float,scores))))
