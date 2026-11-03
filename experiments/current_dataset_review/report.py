"""Current-model reports: before/after filtering, paired crops and discarded-position audit."""
import json,html,hashlib,sys
from pathlib import Path
from collections import defaultdict
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.full_dataset_review.readable_report import STYLE
OUT=ROOT/'workspace/windows-check/diagnostics/v11-examples-full-evaluation-20261103'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def esc(x):return html.escape(str(x))
def save(name,title,body,script=''):
 (OUT/name).write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE} figure{{margin:0}}.pill{{color:#007b85}}article[hidden]{{display:none}}.controls{{position:sticky;top:0;background:#edf4f5;z-index:2;padding:10px}}button{{font:inherit;padding:6px}}.pair svg{{max-height:380px}}.removed{{border-left:4px solid #7e8990}}.triple img{{max-height:580px;object-fit:contain}}</style>{body}<script>{script}</script></html>',encoding='utf-8')
NAV='<nav><a href="index.html">總結果</a><a href="good.html">良品誤報</a><a href="bad.html">不良品檢測</a></nav>'
LABEL={'screw':'疑似螺絲','uncertain':'不確定','cable':'線材','circuit_board':'電路板','metal_plate':'金屬板','hole':'孔洞','background':'背景'}
def stats(rows):
 return dict(images=len(rows),before=sum(r['pre_ai_count'] for r in rows),removed=sum(r['filtered_count'] for r in rows),after=sum(r['count'] for r in rows),zero=sum(r['count']==0 for r in rows),positive=sum(r['count']>0 for r in rows),high=sum(r['high'] for r in rows),ai_screw=sum(r['ai_screw'] for r in rows),errors=sum(r['ai_error'] for r in rows))
def overlap(a,b):
 inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
 return inter/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter)
def pair(c,width,height):
 x,y,w,h=(c[k] for k in ('x','y','w','h'));side=max(96,w+48,h+48)
 x0=max(0,min(width-side,x+w//2-side//2));y0=max(0,min(height-side,y+h//2-side//2));cw=min(side,width-x0);ch=min(side,height-y0)
 body='<div class="pair">'
 for title,file in [('參照圖：相同位置','reference.png'),('待測圖','aligned.png')]:
  body+=f'<figure><b>{title}</b><svg viewBox="{x0} {y0} {cw} {ch}"><image href="{file}" width="{width}" height="{height}"/><rect class="mark" x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#e1263b" stroke-width=".7"/></svg></figure>'
 return body+'</div>'
def photo(row,known):
 folder=OUT/'photos'/row['sha256'];r=read(folder/'result.json');image=Image.open(folder/'aligned.png');width,height=image.size
 for suffix,candidates in [('aligned_overlay',r['candidates']),('filtered_overlay',r['filtered_candidates'])]:
  overlay=image.convert('RGB');draw=ImageDraw.Draw(overlay)
  for c in candidates:
   x,y,w,h=(c[k] for k in ('x','y','w','h'));color='#e1263b' if c['priority']=='high' else '#d99a00'
   draw.rectangle((x-2,y-2,x+w+2,y+h+2),outline=color,width=2);draw.text((x,max(0,y-14)),str(c['id']),fill=color)
  overlay.save(folder/(suffix+'.png'))
 matches=[]
 for obj in known.get(row['sha256'],[]):
  before=r['candidates']+r['filtered_candidates'];matched=[c['id'] for c in r['candidates'] if overlap(c['source_bbox'],obj['bbox'])>.15]
  matches.append(dict(bbox=obj['bbox'],retained_ids=matched,removed_ids=[c['id'] for c in r['filtered_candidates'] if overlap(c['source_bbox'],obj['bbox'])>.15]))
 row['known_checks']=matches;(folder/'known-check.json').write_text(json.dumps(matches))
 title=row['machine']+' / '+row['label']+' / '+Path(row['path']).name
 body='<nav><a href="../../index.html">總結果</a><a href="../../good.html">良品誤報</a><a href="../../bad.html">不良品檢測</a></nav>'+f'<h1>{esc(title)}</h1><p>參照圖：{esc(Path(row["reference"]).name)}</p>'
 body+=f'<div class="answer"><b>差分 {r["pre_ai_count"]} 框 → AI 排除 {r["filtered_count"]} 框 → 保留 {r["proposal_count"]} 框</b>'
 body+=('<p>這是參照圖自比，不列入檢測成效。</p>' if row['is_reference'] else '<p>這張標為良品，保留的框都計入誤報。</p>' if row['label']=='OK' else f'<p>保留框中，AI 判為疑似螺絲 {row["ai_screw"]} 個、不確定 {row["ai_uncertain"]} 個。</p>')
 if matches:body+=f'<p>既有目視標記：{sum(bool(z["retained_ids"]) for z in matches)} / {len(matches)} 處仍有保留框。</p>'
 if row.get('visual_issue_count'):body+=f'<p><b>本次目視抽查：{row["visual_issue_count"]} 處疑似螺絲被刪除。</b><a href="../../issues.html">查看問題對照</a></p>'
 body+='</div><div class="triple">'
 for label,file in [('正常參照圖','reference.png'),('待測圖（已對齊）','aligned.png'),('AI 過濾後保留框','aligned_overlay.png')]:body+=f'<figure><b>{label}</b><a href="{file}"><img src="{file}"></a></figure>'
 body+='</div><h2>保留位置</h2><div class="controls"><label>顯示 <select id="filter"><option value="all">全部</option><option value="screw">AI 疑似螺絲</option><option value="uncertain">AI 不確定</option></select></label> <label><input id="boxes" type="checkbox" checked>顯示位置框</label></div>'
 if not r['candidates']:body+='<p>沒有保留候選。</p>'
 for c in r['candidates']:
  cl=c['classification'];label=LABEL.get(cl['label'],cl['label']);e=cl.get('screw_example_evidence',{})
  body+=f'<article data-label="{esc(cl["label"])}" id="candidate-{c["id"]}"><h3>位置 {c["id"]} · AI {label}</h3>'
  if e.get('supported'):body+='<p>螺絲外型範例支持保留。</p>'
  body+=pair(c,width,height)+'</article>'
 body+=f'<details id="removed"><summary><b>AI 已排除的 {len(r["filtered_candidates"])} 個位置：展開核對有沒有誤刪</b></summary><a href="filtered_overlay.png">查看排除位置總圖</a>'
 for c in r['filtered_candidates']:
  cl=c['classification'];label=LABEL.get(cl['label'],cl['label'])
  body+=f'<article class="removed" id="removed-{c["id"]}"><h3>原位置 {c["id"]} · AI 判為{label}，已排除</h3>'+pair(c,width,height)+'</article>'
 body+='</details><details><summary>執行資訊</summary><p>模型：CLIP 螺絲外型範例版；差分門檻 0.13。'+('這張照片曾提供非螺絲範例。' if row.get('example_source') else '這張照片未提供非螺絲範例。')+'</p><p>對齊：'+('部分區域品質不足' if r['alignment_warning'] else '未觸發品質警示')+'。</p><a href="result.json">原始結果</a></details>'
 script="if(location.hash.startsWith('#removed'))document.getElementById('removed').open=true;document.getElementById('filter').onchange=e=>{for(const a of document.querySelectorAll('article[data-label]'))a.hidden=e.target.value!=='all'&&a.dataset.label!==e.target.value};document.getElementById('boxes').onchange=e=>document.querySelectorAll('.mark').forEach(r=>r.style.display=e.target.checked?'':'none');"
 save(Path('photos')/row['sha256']/'report.html',title,body,script)
def listing(rows,good):
 title='良品誤報報告' if good else '不良品檢測報告';s=stats(rows)
 body=NAV+f'<h1>{title}</h1><div class="answer">{s["images"]} 張：原 {s["before"]} 框，AI 排除 {s["removed"]} 框，保留 {s["after"]} 框。'
 if good:body+=f'<p>{s["zero"]} 張沒有誤報；{s["positive"]} 張仍有誤報。</p>'
 body+='</div><input id="search" placeholder="搜尋機種或檔名"><table><thead><tr><th>機種／照片</th><th>差分框</th><th>AI 刪除</th><th>保留框</th><th>'+('樣本用途' if good else '保留框的 AI 分類')+'</th><th>看圖</th></tr></thead><tbody>'
 for r in sorted(rows,key=lambda r:(-r['count'],r['relative'])):
  url='photos/'+r['sha256']+'/report.html'
  extra=('曾提供非螺絲範例' if r['example_source'] else '未提供範例') if good else f'疑似螺絲 {r["ai_screw"]}／不確定 {r["ai_uncertain"]}'
  extra+=(f'；抽查疑似誤刪 {r["visual_issue_count"]} 處' if r.get('visual_issue_count') else '')
  body+=f'<tr data-search="{esc(r["relative"].lower())}"><td>{esc(r["relative"])}</td><td>{r["pre_ai_count"]}</td><td>{r["filtered_count"]}</td><td>{r["count"]}</td><td>{extra}</td><td><a href="{url}">保留位置</a> · <a href="{url}#removed">被刪位置</a></td></tr>'
 body+='</tbody></table>'
 save('good.html' if good else 'bad.html',title,body,"document.getElementById('search').oninput=e=>document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.dataset.search.includes(e.target.value.toLowerCase().trim()));")
def main():
 rows=read(OUT/'results.json');plan=read(OUT/'plan.json');assert len(rows)==190 and all(r['success'] for r in rows)
 model=read(ROOT/'models'/plan['model']['requested']/'manifest.json');bankshas={name.rsplit('-',1)[0] for name in model['screw_examples']['normal']['ids']}
 known={}
 for sample in read(ROOT/'review/annotations.json')['samples'].values():
  p=ROOT/'workspace/windows-check'/sample['file']
  if p.exists():known[hashlib.sha256(p.read_bytes()).hexdigest()]=sample['objects']
 issues=read(Path(__file__).with_name('visual_review.json'))
 (OUT/'visual-issues.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2),encoding='utf-8')
 for r in rows:
  r['example_source']=r['sha256'] in bankshas
  r['visual_issue_count']=sum(z['sha256']==r['sha256'] for z in issues)
  photo(r,known)
 tested=[r for r in rows if not r['is_reference']];good=[r for r in tested if r['label']=='OK'];bad=[r for r in tested if r['label']=='NG']
 groups={}
 for machine in sorted({r['machine'] for r in tested}):
  for label in ('OK','NG'):
   subset=[r for r in tested if r['machine']==machine and r['label']==label]
   if subset:groups[machine+'/'+label]=stats(subset)
 g,b=stats(good),stats(bad);knownchecks=[k for r in tested for k in r['known_checks']]
 regression=read(ROOT/'workspace/windows-check/diagnostics/clip-screw-examples/production-check.json')
 assert regression['model']['fingerprint']==plan['model']['fingerprint']
 summary=dict(visual_issue_count=len(issues),recommendation='not_ready_due_to_suspected_screw_deletions',complete=True,images=len(rows),tests=len(tested),good=g,bad=b,groups=groups,good_example_sources=stats([r for r in good if r['example_source']]),good_other_images=stats([r for r in good if not r['example_source']]),known_batch_regions=len(knownchecks),known_batch_retained=sum(bool(k['retained_ids']) for k in knownchecks),historical_regions=len(regression['known_regions']),historical_retained=sum(bool(k['retained_ids']) for k in regression['known_regions']),model=plan['model'])
 body=NAV+'<h1>目前版本：良品與不良品檢測結果</h1><p>CLIP 螺絲外型範例版 · 每機種一張參照圖 · 差分門檻 0.13</p>'
 body+=f'<div class="answer"><b>我的判斷：先不要定案。本次抽查發現 {len(issues)} 處疑似螺絲被 AI 誤刪。</b><p><a href="issues.html">先看這 {len(issues)} 處參照／待測對照 →</a></p><b>良品：{g["images"]} 張中，{g["zero"]} 張零誤報，{g["positive"]} 張仍有誤報。</b><p>誤報框由 {g["before"]} 個降為 {g["after"]} 個，AI 刪除 {g["removed"]} 個（{g["removed"]/g["before"]:.1%}）。</p><b>不良品：{b["images"]} 張，保留 {b["after"]} 個候選，AI 刪除 {b["removed"]} 個。</b><p>既有 8 處歷史螺絲標記仍保留 {summary["historical_retained"]} 處；本批另有 {len(knownchecks)} 處既有目視標記，保留 {summary["known_batch_retained"]} 處。</p></div>'
 body+='<h2>良品：還剩多少誤報？</h2><table><tr><th>機種</th><th>張數</th><th>原誤報框</th><th>AI 刪除</th><th>剩餘誤報框</th><th>零誤報照片</th></tr>'
 for key,s in groups.items():
  if key.endswith('/OK'):body+=f'<tr><td>{key[:-3]}</td><td>{s["images"]}</td><td>{s["before"]}</td><td>{s["removed"]}</td><td>{s["after"]}</td><td>{s["zero"]}</td></tr>'
 body+='</table><p><a href="good.html">逐張看剩餘誤報與已刪除位置 →</a></p>'
 a,h=summary['good_example_sources'],summary['good_other_images']
 body+=f'<p>其中 {a["images"]} 張曾提供非螺絲範例，剩 {a["after"]} 框；另 {h["images"]} 張未提供範例，剩 {h["after"]} 框。兩組已在照片清單中標明。</p>'
 body+=f'<h2>不良品：保留和刪掉哪些位置？</h2><p>全部來自 MPT11：差分 {b["before"]} 框 → AI 排除 {b["removed"]} 框 → 保留 {b["after"]} 框。保留框中，AI 判為疑似螺絲 {b["ai_screw"]} 個。</p><p><a href="bad.html">逐張看不良品，並核對被刪位置 →</a></p><p>這批 NG 沒有完整的逐顆螺絲標註，因此這裡呈現的是 AI 標記結果，不把候選框數當成抓到的螺絲顆數。每張都附保留與刪除位置的參照／待測對照。</p>'
 body+='<h2>為什麼我不建議定案？</h2><p>抽查中，參照圖沒有、待測圖新增的圓形／圓環狀螺絲外觀，被 AI 判成電路板、背景或孔洞後刪除。這些位置的原候選框內也沒有其他保留框。先前 8 處標記通過，沒有涵蓋這批新發現的問題。</p><p>以上是我本次的目視判讀，對照圖已完整列出供你核對；不是把沒有完整標註當成結論的替代品。</p>'
 body+='<details><summary>參照圖與執行紀錄</summary><p>190 張全數重新分析；4 張參照圖自比不列入成效。原始圖資、正式設定與參照圖均保留。</p><ul>'
 for machine,ref in plan['references'].items():body+=f'<li>{machine}：{esc(Path(ref["path"]).name)}</li>'
 body+='</ul><a href="plan.json">固定執行設定</a> · <a href="summary.json">統計數據</a></details>'
 save('index.html','目前版本完整檢測報告',body);listing(good,True);listing(bad,False)
 issuebody=NAV+'<h1>本次抽查：6 處疑似螺絲被 AI 誤刪</h1><p>左邊是參照圖，右邊是待測圖。這些新增的圓形／圓環狀物體有螺絲外觀，卻被模型當成非螺絲刪除；原候選框內沒有其他保留框。這是本次目視發現的案例，不是完整漏檢數。</p>'
 for z in issues:
  folder=OUT/'photos'/z['sha256'];rr=read(folder/'result.json');c=next(c for c in rr['filtered_candidates'] if c['id']==z['candidate_id'])
  with Image.open(folder/'aligned.png') as im:w,h=im.size
  prefix='photos/'+z['sha256']+'/'
  comparison=pair(c,w,h).replace('href="reference.png"','href="'+prefix+'reference.png"').replace('href="aligned.png"','href="'+prefix+'aligned.png"')
  issuebody+=f'<article><h3>{esc(z["relative"])} · 原位置 {c["id"]}</h3><p>AI 判定：{LABEL.get(z["ai_label"],z["ai_label"])}，已刪除。</p>'+comparison+f'<p><a href="{prefix}report.html#removed-{c["id"]}">查看這張的完整結果</a></p></article>'
 save('issues.html','疑似誤刪案例',issuebody)
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'report-rows.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':main()
