"""Build a target-only CLIP cable appearance refinement and audit cached candidates."""
import json,sys,hashlib,shutil,html
from pathlib import Path
import numpy as np
from PIL import Image
import onnxruntime as ort
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from model_manager import ModelManager
from model_adapters import classify,CLIP_REVIEW_MARGIN
WORK=ROOT/'workspace/windows-check';OUT=WORK/'diagnostics/clip-shape-study';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(WORK/'ai-trials/runtime'))
from tokenizers import Tokenizer
def read(p):return json.loads(p.read_text(encoding='utf-8'))
source=WORK/'ai-trials/clip-vit-base-patch32'
base=ROOT/'models/clip-tight-bf6e136950a6';manifest=read(base/'manifest.json')
prompts=['a close up x ray image of '+s+'.' for s in
         ('a thin flexible wire','a bent wire','a long thin cable','a thin strand of wire')]
tokenizer=Tokenizer.from_file(str(source/'tokenizer.json'))
tokenizer.enable_padding(pad_id=49407,pad_token='<|endoftext|>');tokenizer.enable_truncation(max_length=77)
tokens=tokenizer.encode_batch(prompts);options=ort.SessionOptions();options.intra_op_num_threads=4
session=ort.InferenceSession(str(source/'text_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
feed={i.name:np.asarray([t.ids if i.name=='input_ids' else t.attention_mask for t in tokens],np.int64) for i in session.get_inputs()}
vectors=session.run(None,feed)[0];vectors/=np.linalg.norm(vectors,axis=1,keepdims=True)
vector=vectors.mean(axis=0);vector/=np.linalg.norm(vector)
manifest['model_id']='CLIP ViT-B/32 線材外型辨識版'
manifest['cable_shape']=dict(method='clip-cable-shape-v1',prompts=prompts,embedding=vector.tolist())
name='clip-shape-'+hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:12]
directory=ROOT/'models'/name;directory.mkdir(exist_ok=True)
if not (directory/'model.onnx').exists():shutil.copy2(base/'model.onnx',directory/'model.onnx')
(directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
snapshot=ModelManager(ROOT/'models',allow_cpu=True).snapshot(name);assert not snapshot.error,snapshot.error
def predict(image):return classify(manifest,snapshot.session,np.asarray(image,dtype=np.float32)/255)
def crop(image,c):
    x,y,w,h=(c[k] for k in ('x','y','w','h'))
    return image.crop((max(0,x-12),max(0,y-12),min(image.width,x+w+12),min(image.height,y+h+12)))

# Re-evaluate all annotated candidate crops, including earlier false-deletion cases.
old=read(WORK/'ai-trials/clip-tight-results/report.json');known=[]
for sample in old['samples']:
    ids={i for region in sample['known_regions'] for i in region['candidate_ids']}
    preds={i:predict(Image.open(WORK/f'ai-trials/clip-tight-results/{sample["name"]}/crop_{i}.png')) for i in ids}
    for region in sample['known_regions']:
        retained=[i for i in region['candidate_ids'] if preds[i]['filter_recommendation']!='non_screw_suggestion']
        assert retained,(sample['name'],region)
        known.append(dict(sample=sample['name'],region=region['region'],retained_ids=retained))

# Only uncertain cable predictions can change; other original decisions are untouched.
batch=WORK/'diagnostics/v10-full-evaluation-20261103';rows=read(batch/'results.json');changes=[];tested=0;target=None
for row in rows:
    if row['is_reference']:continue
    folder=batch/'photos'/row['sha256'];result=read(folder/'result.json')
    with Image.open(folder/'aligned.png') as image:
        for c in result['candidates']:
            previous=c['classification']
            if previous.get('label')!='uncertain' or previous.get('raw_label')!='cable':continue
            patch=crop(image,c);prediction=predict(patch);tested+=1
            if prediction['filter_recommendation']=='non_screw_suggestion':
                key=f'{row["sha256"]}-{c["id"]}';patch.save(OUT/(key+'.png'))
                changes.append(dict(sample=row['relative'],label=row['label'],id=c['id'],before=previous['screw_margin'],after=prediction['screw_margin'],crop=key+'.png'))
            if '15_53_47_24' in row['path'] and c['id']==1:
                assert prediction['label']=='cable' and prediction['filter_recommendation']=='non_screw_suggestion'
                target=prediction
    if tested and tested%20==0:print('checked ambiguous cable crops',tested,flush=True)
assert target and len(known)==8 and CLIP_REVIEW_MARGIN==.01
report=dict(model_directory=name,threshold=CLIP_REVIEW_MARGIN,target=target,known_regions=known,
            tested_ambiguous_crops=tested,newly_removed=changes,
            scope='Target-only CLIP, unchanged image encoder and decision threshold; prompts developed using the reported wire example. Eight known regions are regression cases, not exhaustive screw labels.')
(OUT/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
body='<h1>CLIP 線材外型測試</h1><p>固定門檻 0.01。只使用待測圖，沒有使用參照圖。指定線材位置：原差距 0.00087，新差距 '+f'{abs(target["screw_margin"]):.5f}，判為線材並排除。</p><p>先前 8 處螺絲均保留命中框。以下列出全部新增排除位置；NG 圖中的其他位置尚未有完整螺絲標註。</p>'
for c in changes:
    body+=f'<article><h3>{html.escape(c["sample"])} · 位置 {c["id"]}</h3><img src="{c["crop"]}"><p>線材領先 {abs(c["after"]):.5f}</p></article>'
(OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px sans-serif;max-width:1100px;margin:35px auto}article{display:inline-block;width:320px;vertical-align:top;padding:15px;border:1px solid #ddd}img{width:220px;image-rendering:auto}h3{font-size:14px;overflow-wrap:anywhere}</style>'+body,encoding='utf-8')
print(json.dumps(dict(model=name,tested=tested,newly_removed=len(changes),good_removed=sum(c['label']=='OK' for c in changes),ng_removed=sum(c['label']=='NG' for c in changes),known_retained=len(known))))
