"""NG review uses the same machine/type/location navigation as good-image review."""
import sys,json,re
from pathlib import Path
from collections import Counter
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.current_dataset_review.report import OUT,read,save,esc,pair,NAV
from experiments.current_dataset_review.good_review import clusters
TYPES={'suspected_delete':('疑似螺絲誤刪：目視發現','本次目視抽查發現的 6 處問題，優先檢視。'),'screw':('螺絲外型候選','AI 判為螺絲，且沒有落入以下細長或相似輪廓線索組；尚不是人工確認結果。'),'wire_edge':('細長／線材邊界線索','依既有線材提示或細長輪廓分組；這是檢視線索，不能直接當成非螺絲。'),'structure':('既有輪廓差異線索','差分結果記錄附近有相似輪廓，集中對照原有結構與新增物體。'),'uncertain':('其他待確認位置','AI 尚無明確螺絲判定，且沒有上述分組線索。'),'removed':('其餘 AI 已排除位置','AI 已判成非螺絲；保留參照／待測對照供檢查誤刪。')}
def card(z):
 prefix='photos/'+z['sha']+'/';c=z['candidate']
 with Image.open(OUT/prefix/'aligned.png') as im:w,h=im.size
 comparison=pair(c,w,h).replace('href="reference.png"',f'href="{prefix}reference.png"').replace('href="aligned.png"',f'href="{prefix}aligned.png"')
 anchor=('removed-' if z['removed'] else 'candidate-')+str(z['id'])
 label={'screw':'疑似螺絲','uncertain':'不確定','circuit_board':'電路板','cable':'線材','hole':'孔洞','background':'背景','metal_plate':'金屬板'}.get(c['classification']['label'],c['classification']['label'])
 return f'<article id="case-{z["sha"]}-{z["id"]}"><h3>{esc(Path(z["name"]).name)} · 位置 {z["id"]}</h3><p>{"已排除" if z["removed"] else "保留候選"} · AI：{label}</p>'+comparison+f'<a href="{prefix}report.html#{anchor}">查看完整照片與此位置 →</a></article>'
OPEN="const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));let node=target;while(node){if(node.tagName==='DETAILS')node.open=true;node=node.parentElement}if(target)target.scrollIntoView();"
def main():
 rows=[r for r in read(OUT/'report-rows.json') if r['label']=='NG' and not r['is_reference']]
 issues={(z['sha256'],z['candidate_id']) for z in read(OUT/'visual-issues.json')};items=[]
 for r in rows:
  result=read(OUT/'photos'/r['sha256']/'result.json')
  for removed,cs in [(False,result['candidates']),(True,result['filtered_candidates'])]:
   for c in cs:
    key=('suspected_delete' if (r['sha256'],c['id']) in issues else 'removed') if removed else 'wire_edge' if c.get('wire_review') or c.get('aspect',0)>5 else 'structure' if any('附近有相似輪廓' in s for s in c.get('reasons',[])) else 'screw' if c['classification']['label']=='screw' else 'uncertain'
    items.append(dict(machine=r['machine'],sha=r['sha256'],id=c['id'],name=r['relative'],category=key,removed=removed,candidate=c,**{k:c[k] for k in ('x','y','w','h')}))
 assert len(items)==2665 and sum(z['removed'] for z in items)==195
 body=NAV+'<h1>不良品 Review：先選機種</h1><p>與良品相同，按「機種 → 類型 → 相近位置」檢視，並附每個位置的參照／待測圖。</p><p>目前 NG 圖資只有 MPT11；MPT10、MPT12、KPH33 尚無 NG 圖。<a href="stage2-review.html">第二階段 AI 是否達到構想？</a></p><table><tr><th>機種</th><th>張數</th><th>保留候選</th><th>AI 排除</th><th>開始檢視</th></tr>'
 pages=['bad.html'];counts={}
 for m in sorted({r['machine'] for r in rows}):
  rs=[r for r in rows if r['machine']==m];zs=[z for z in items if z['machine']==m]
  body+=f'<tr><td>{m}</td><td>{len(rs)}</td><td>{sum(r["count"] for r in rs)}</td><td>{sum(r["filtered_count"] for r in rs)}</td><td><a href="bad-{m}.html">進入 {m} →</a></td></tr>'
  overview=f'<nav><a href="bad.html">所有機種</a><a href="index.html">總結果</a></nav><h1>{m}：不良品分類檢視</h1><p>{len(rs)} 張照片；保留 {sum(r["count"] for r in rs)} 框，AI 排除 {sum(r["filtered_count"] for r in rs)} 框。</p><p>疑似誤刪組為目視發現；其他組依 AI 判定與既有輪廓線索初分，供逐圖檢視。</p>'
  for k,(title,description) in TYPES.items():
   subset=[z for z in zs if z['category']==k]
   if not subset:continue
   counts[m+'/'+k]=len(subset);groups=clusters(subset);file=f'bad-{m}-{k}.html'
   overview+=f'<article><h2><a href="{file}">{title} →</a></h2><p>{len(subset)} 個位置 · {len({z["sha"] for z in subset})} 張照片 · {len(groups)} 組相近位置</p><p>{description}</p></article>'
   detail=f'<nav><a href="bad.html">所有機種</a><a href="bad-{m}.html">{m} 類型總覽</a></nav><h1>{m} / {title}</h1><p>{description}</p><p>{len(subset)} 個位置。每組先顯示一組對照，可展開其他照片。</p><p><button onclick="document.querySelectorAll(\'details\').forEach(d=>d.open=true)">展開所有照片</button> <button onclick="document.querySelectorAll(\'details\').forEach(d=>d.open=false)">收合重複照片</button></p><details><summary>跳到指定相近位置</summary>'
   detail+=' · '.join(f'<a href="#group-{i}">{i}（{len(g)} 框）</a>' for i,g in enumerate(groups,1))+'</details>'
   for i,g in enumerate(groups,1):
    detail+=f'<section id="group-{i}"><h2>相近位置 {i} · {len(g)} 個框／{len({z["sha"] for z in g})} 張照片</h2>'+card(g[0])
    if len(g)>1:detail+=f'<details><summary>展開另外 {len(g)-1} 個位置對照</summary>'+''.join(card(z) for z in g[1:])+'</details>'
    detail+='</section>'
   save(file,m+' / '+title,detail,OPEN);pages.append(file)
  overview+='<details><summary>依照片查看此機種完整清單</summary><table><tr><th>照片</th><th>保留</th><th>排除</th></tr>'
  for r in sorted(rs,key=lambda r:r['relative']):overview+=f'<tr><td><a href="photos/{r["sha256"]}/report.html">{esc(Path(r["path"]).name)}</a></td><td>{r["count"]}</td><td>{r["filtered_count"]}</td></tr>'
  save(f'bad-{m}.html',m+' 不良品分類',overview+'</table></details>');pages.append(f'bad-{m}.html')
 body+='</table><h2>直接按類型檢視</h2><table><tr><th>類型</th><th>位置數</th></tr>'
 for k,(title,_) in TYPES.items():
  n=sum(z['category']==k for z in items)
  body+=f'<tr><td><a href="bad-MPT11-{k}.html">{title}</a></td><td>{n}</td></tr>'
 save('bad.html','不良品：按機種與類型檢視',body+'</table>')
 for r in rows:
  m=r['machine'];zs=[z for z in items if z['sha']==r['sha256']];types=Counter(z['category'] for z in zs);path=OUT/'photos'/r['sha256']/'report.html';text=path.read_text(encoding='utf-8')
  text=re.sub(r'<!--ng-review-start-->.*?<!--ng-review-end-->','',text,flags=re.S)
  links=' · '.join(f'<a href="../../bad-{m}-{k}.html">{TYPES[k][0]} {n} 個</a>' for k,n in types.items())
  block=f'<!--ng-review-start--><div class="answer"><a href="../../bad-{m}.html">← 回到 {m} 不良品類型總覽</a><p>{links}</p></div><!--ng-review-end-->'
  text=text.replace('</nav>','</nav>'+block,1)
  for z in zs:
   marker=f'<!--ng-type-{z["id"]}-start-->';end=f'<!--ng-type-{z["id"]}-end-->'
   text=re.sub(re.escape(marker)+'.*?'+re.escape(end),'',text,flags=re.S)
   tag=marker+f'<p><a href="../../bad-{m}-{z["category"]}.html#case-{z["sha"]}-{z["id"]}">檢視分組：{TYPES[z["category"]][0]} · 查看同類案例</a></p>'+end
   prefix='removed-' if z['removed'] else 'candidate-'
   pattern=r'(<article[^>]*id="'+prefix+str(z['id'])+r'">)'
   text=re.sub(pattern,lambda match:match[1]+tag,text,count=1)
  path.write_text(text,encoding='utf-8')
 stage=NAV+'<h1>第二階段 AI：構想與目前實作的落差</h1><p><b>目標流程：差分找候選 → 只看待測裁圖外型 → 螺絲保留、非螺絲排除。</b></p><h2>目前結果還沒有達到目標</h2><ul><li>良品原 128 個誤報只刪掉 22 個，剩 106 個。</li><li>剩餘 106 個中：94 個被 CLIP 判成螺絲，12 個不確定。</li><li>106 個的影像範例分數都更接近非螺絲，領先差距均超過 0.01；但目前範例層只會增加螺絲保留，不會推翻原判定來排除非螺絲。</li><li>NG 抽查又發現 6 處疑似真螺絲被刪，表示分類同時有誤報與誤刪問題。</li></ul><h2>實作問題</h2><p>我把外型範例層設成單向保護，沒有實現完整的螺絲／非螺絲雙向分類。原 CLIP 只要螺絲文字相似度略高，就會判為螺絲；這也不是經過 X 光資料校準的螺絲信心值。</p><h2>應如何對齊構想</h2><p>第二階段應改成用已標記 X 光螺絲與非螺絲訓練、驗證的分類器。可以保留 CLIP 影像特徵、訓練雙向分類層，或更換為專用 YOLO／分類模型；驗收同時看非螺絲排除與真螺絲保留。</p><p>不能把本報告的良品標籤或目視分類直接塞進正式推論，也不能看到這 106 個範例分數就直接全部刪除：NG 已出現誤刪，需要用分開的驗證照片檢查雙向判定。</p><p><a href="good.html">良品分類</a> · <a href="bad.html">不良品分類</a> · <a href="issues.html">6 處疑似誤刪對照</a></p>'
 save('stage2-review.html','第二階段 AI 成效檢視',stage);pages.append('stage2-review.html')
 (OUT/'bad-review-index.json').write_text(json.dumps(dict(total=len(items),retained=2470,removed=195,categories=counts,pages=pages,items=[{k:v for k,v in z.items() if k!='candidate'} for z in items]),ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(total=len(items),categories=counts,pages=len(pages))))
if __name__=='__main__':main()
