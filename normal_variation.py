"""Conservative multi-normal confirmation for candidate-level experiments."""
import numpy as np
from detector import structure_change_evidence


def confirms_normal(normal,target,candidate,threshold):
    evidence=structure_change_evidence(normal,target,candidate,threshold)
    if not evidence or not evidence['context_supported'] or evidence['sim']<.85 or evidence['remaining']>=12:
        return None
    x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
    dx,dy=evidence['dx'],evidence['dy']
    predicted=np.clip(evidence['gain']*normal[y+dy:y+h+dy,x+dx:x+w+dx]+evidence['offset'],0,1)
    if predicted.shape!=(h,w):return None
    positive=np.maximum(predicted-target[y:y+h,x:x+w],0)
    if float(positive.mean())>.03 or float(np.percentile(positive,95))>.10:
        return None
    return dict(evidence,positive_mean=float(positive.mean()),positive_p95=float(np.percentile(positive,95)))


def separate(candidates,target,normals,threshold):
    unique=[];seen=set()
    for identity,normal in normals:
        if normal.shape!=target.shape:raise ValueError('正常樣本與待測圖必須使用同一座標尺寸')
        if identity not in seen:
            unique.append((identity,normal));seen.add(identity)
    kept=[];explained=[]
    for candidate in candidates:
        supports=[]
        for identity,normal in unique:
            evidence=confirms_normal(normal,target,candidate,threshold)
            if evidence is not None:supports.append(dict(reference=identity,evidence=evidence))
            if len(supports)>=2:break
        if len(supports)>=2:
            explained.append(dict(candidate,normal_variation_evidence=supports))
        else:kept.append(candidate)
    return kept,explained
