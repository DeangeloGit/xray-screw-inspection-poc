import json,sys,hashlib,shutil,html
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from model_manager import ModelManager
from model_adapters import clip_decision,refine_cable_shape,refine_screw_examples
WORK=ROOT/'workspace/windows-check';OUT=WORK/'diagnostics/clip-screw-examples'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
base=ROOT/'models/clip-shape-4bf2386067d8';m=read(base/'manifest.json');features=read(OUT/'features.json')
bank=dict(method='clip-visual-screw-bank-v1',neighbors=3,margin=.01,minimum_similarity=.85)
for label,source in [('screw','screw'),('normal','normal')]:
 rows=[r for r in features if r['split']=='bank' and r['label']==source]
 bank[label]=dict(ids=[r['name'] for r in rows],embeddings=[r['vector'] for r in rows])
m['screw_examples']=bank;m['model_id']='CLIP ViT-B/32 螺絲外型範例版'
m['example_provenance']=dict(sources=[dict(file=f'source-{i}.png',sha256=hashlib.sha256((OUT/f'source-{i}.png').read_bytes()).hexdigest()) for i in (1,2,3)],notes='Image 1 red-box X-ray crops used as screw exemplars; image 2 separately evaluated; image 3 physical-photo catalog retained for provenance only. Normal crops split by source image; user-reported wire reserved for validation. No reference image enters inference.')
name='clip-examples-'+hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest()[:12];directory=ROOT/'models'/name;directory.mkdir(exist_ok=True)
if not (directory/'model.onnx').exists():shutil.copy2(base/'model.onnx',directory/'model.onnx')
(directory/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
snapshot=ModelManager(ROOT/'models',allow_cpu=True).snapshot(name);assert not snapshot.error,snapshot.error
rows=[]
for f in features:
 if f['split']!='validation':continue
 v=np.asarray(f['vector'],np.float32);scores=np.asarray(m['text_embeddings'],np.float32)@v
 before=refine_cable_shape(m,v,clip_decision(m['classes'],scores),scores);after=refine_screw_examples(m,v,before)
 rows.append(dict(name=f['name'],label=f['label'],before=before['label'],after=after['label'],before_action=before['filter_recommendation'],after_action=after['filter_recommendation'],evidence=after['screw_example_evidence'],wire=f.get('wire',False)))
 assert not (before['filter_recommendation']!='non_screw_suggestion' and after['filter_recommendation']=='non_screw_suggestion')
normal=[r for r in rows if r['label']=='normal'];known=[r for r in rows if r['label']=='known_screw'];screens=[r for r in rows if r['label']=='screw']
assert not any(r['evidence']['supported'] for r in normal)
assert next(r for r in normal if r['wire'])['after_action']=='non_screw_suggestion'
# Eight known regions may overlap more than one detector candidate.
prior=read(WORK/'ai-trials/clip-tight-results/report.json');regions=[]
for s in prior['samples']:
 for region in s['known_regions']:
  ids=[i for i in region['candidate_ids'] if next(r for r in known if r['name']==s['name']+'-'+str(i))['after_action']!='non_screw_suggestion']
  assert ids,(s['name'],region)
  regions.append(dict(sample=s['name'],region=region['region'],retained_ids=ids))
summary=dict(model_directory=name,screw_bank=len(bank['screw']['ids']),normal_bank=len(bank['normal']['ids']),validation_normal=len(normal),normal_false_promotions=0,known_regions_retained=len(regions),known_screw_before=sum(r['before']=='screw' for r in known),known_screw_after=sum(r['after']=='screw' for r in known),screenshot_validation=len(screens),screenshot_screw_before=sum(r['before']=='screw' for r in screens),screenshot_screw_after=sum(r['after']=='screw' for r in screens),wire_still_removed=True,regions=regions,rows=rows)
(OUT/'evaluation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
body=f'<h1>CLIP 螺絲外型範例版</h1><p>已加入 {summary["screw_bank"]} 張 X 光螺絲範例與 {summary["normal_bank"]} 張良品誤報範例。保留原線材過濾；螺絲外型證據只能增加保留，不能新增刪除。</p><p>歷史 8 處已標記螺絲全部保留。對應 9 個候選中，判為螺絲由 {summary["known_screw_before"]} 個增加至 {summary["known_screw_after"]} 個。另 {len(normal)} 個未加入範例庫的良品誤報，沒有被新增判為螺絲；指定線材仍刪除。</p><p>另一頁截圖的 {len(screens)} 張清楚裁圖，螺絲判定由 {summary["screenshot_screw_before"]} 增至 {summary["screenshot_screw_after"]}。截圖可能包含相同來源或相似背景，不把此數字當成現場辨識率。</p><h2>實際加入的螺絲範例</h2>'
for id in bank['screw']['ids']:body+=f'<figure><img src="{id}"><figcaption>{html.escape(id)}</figcaption></figure>'
body+='<h2>歷史螺絲候選的判定變化</h2><table><tr><th>位置</th><th>原判定</th><th>新判定</th></tr>'
for r in known:body+=f'<tr><td>{r["name"]}</td><td>{r["before"]}</td><td>{r["after"]}</td></tr>'
body+='</table><p>CLIP 影像編碼器權重未重訓；更新的是使用影像特徵的範例分類層。實物照片未混入 X 光分類範例。</p>'
(OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px/1.7 sans-serif;max-width:1100px;margin:30px auto}figure{display:inline-block;margin:10px}img{width:120px;height:120px;object-fit:contain}figcaption{font-size:12px}td,th{border:1px solid #ddd;padding:8px}table{border-collapse:collapse}</style>'+body,encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ['regions','rows']}))
