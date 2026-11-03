"""Frozen DINOv2 CLS features and an immutable example bank."""
import numpy as np
from PIL import Image

POLICY = 'dino-top3-examples-v1'
PAIRED_POLICY = 'dino-top3-target-and-reference-v1'


def validate(m, output):
    if m.get('input_size') != [224, 224] or m.get('classes') != ['screw', 'non_screw'] or output.shape != (1, 257, 384):
        raise ValueError('DINO 需要 224×224 輸入與 [1,257,384] 特徵輸出')
    if m.get('resize_shortest') not in (224, 256) or m.get('decision_policy') not in (POLICY, PAIRED_POLICY):
        raise ValueError('不支援的 DINO 取圖或判斷設定')
    if m.get('neighbors') != 3 or m.get('decision_margin') != 0:
        raise ValueError('DINO 範例比較設定不符')
    for name in ('mean', 'std'):
        a = np.asarray(m.get(name), dtype=float)
        if a.shape != (3,) or not np.isfinite(a).all() or (name == 'std' and np.any(a <= 0)):
            raise ValueError('DINO 正規化設定無效')
    for label in ('screw', 'normal'):
        group = m.get('example_bank', {}).get(label, {})
        a = np.asarray(group.get('embeddings'), dtype=np.float32)
        ids = group.get('ids', [])
        if a.ndim != 2 or a.shape[1] != 384 or not 3 <= len(ids) == len(a) <= 2000 or not all(isinstance(x, str) for x in ids) or len(set(ids)) != len(ids) or not np.isfinite(a).all() or not np.allclose(np.linalg.norm(a, axis=1), 1, atol=.001):
            raise ValueError('DINO 範例庫無效')


def input_image(m, crop):
    im = Image.fromarray(np.rint(np.clip(crop, 0, 1)*255).astype('uint8')).convert('RGB')
    w, h = im.size
    edge = m['resize_shortest']
    im = im.resize((edge, int(edge*h/w)) if w <= h else (int(edge*w/h), edge), Image.Resampling.BICUBIC)
    x, y = (im.width-224)//2, (im.height-224)//2
    return im.crop((x, y, x+224, y+224))


def embedding(m, session, crop):
    a = np.asarray(input_image(m, crop), np.float32)/255
    a = (a-np.asarray(m['mean'], np.float32))/np.asarray(m['std'], np.float32)
    output = np.asarray(session.run(None, {session.get_inputs()[0].name: a.transpose(2, 0, 1)[None]})[0])
    if output.shape != (1, 257, 384) or not np.isfinite(output).all():
        raise ValueError('DINO 推論輸出無效')
    vector = output[0, 0]
    norm = np.linalg.norm(vector)
    if norm < 1e-8:
        raise ValueError('DINO 特徵向量無效')
    return vector/norm


def classify(m, session, crop):
    vector = embedding(m, session, crop)
    return classify_vector(m, vector)


def classify_vector(m, vector):
    evidence = {}
    for label in ('screw', 'normal'):
        group = m['example_bank'][label]
        scores = np.asarray(group['embeddings'], np.float32)@vector
        indexes = np.argsort(scores)[-m['neighbors']:][::-1]
        evidence[label] = dict(similarity=float(scores[indexes].mean()), neighbors=[group['ids'][i] for i in indexes])
    margin = evidence['screw']['similarity']-evidence['normal']['similarity']
    keep = margin >= m['decision_margin']
    return dict(label='screw' if keep else 'non_screw', probabilities=None,
                screw_margin=margin, score_kind='cosine_similarity', dino_evidence=evidence,
                decision_policy=POLICY, filter_recommendation='keep' if keep else 'exclude',
                decision_reason='外型較接近螺絲範例，保留' if keep else '外型較接近非螺絲範例，排除')


def paired_decision(target, reference):
    """The exact rule used in the full 47+65 paired-image report."""
    target_screw = target['label'] == 'screw'
    reference_screw = reference['label'] == 'screw'
    keep = target_screw and not reference_screw
    reason = ('待測圖像螺絲、參照圖不像螺絲，保留' if keep else
              '待測圖與參照圖都像螺絲，依雙圖規則排除' if target_screw else
              '待測圖較接近正常範例，排除')
    return dict(target, label='screw' if keep else 'non_screw',
                decision_policy=PAIRED_POLICY, filter_recommendation='keep' if keep else 'exclude',
                decision_reason=reason, paired_evidence=dict(target=target, reference=reference))


def classify_pair(m, session, crop, reference_crop):
    if reference_crop is None or not reference_crop.size:
        raise ValueError('雙圖 DINO 缺少同位置參照小圖，保留候選供人工確認')
    return paired_decision(classify(m, session, crop), classify(m, session, reference_crop))
