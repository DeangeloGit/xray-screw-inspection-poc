"""Render DINO reports as machine -> appearance -> nearby position galleries."""
import sys,json,re,hashlib
from pathlib import Path
from collections import Counter
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.current_dataset_review import report as R
from experiments.current_dataset_review.good_review import clusters
OUT=ROOT/'workspace/windows-check/diagnostics/dino-full-evaluation-20261103';R.OUT=OUT
TYPES={'wire':('線材／細長外觀','沿用既有目視分類；未目視確認者只依線材提示或細長比例列為檢視線索，不代表確定是線材。'),'edge':('板件邊界','沿用先前逐框目視分類，並核對候選座標相同。'),'component':('元件外觀','沿用先前逐框目視分類，並核對候選座標相同。'),'structure':('U 形結構','僅沿用已有的 U 形結構目視分類，不以一般輪廓相似就判定。'),'unknown':('待確認','尚未確認外觀類型，不強行歸入其他類型。'),'screw':('DINO 螺絲外型候選','DINO 保留，且未落入上述外觀線索；不是人工確認的螺絲。'),'suspected':('既有疑似螺絲仍被排除','既有目視標記或前次疑似誤刪位置，本次仍排除，優先回查。')}
OPEN="const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));let n=target;while(n){if(n.tagName==='DETAILS')n.open=true;n=n.parentElement}if(target)target.scrollIntoView();"
read=R.read;esc=R.esc

def file(kind,m,key=None):return f'{kind}-{m}'+('-'+key if key else '')+'.html'
def card(z):
 prefix='photos/'+z['sha']+'/';c=z['candidate'];anchor=('removed-' if z['removed'] else 'candidate-')+str(z['id'])
 pair=R.pair(c,*z['size']).replace('href="reference.png"',f'href="{prefix}reference.png"').replace('href="aligned.png"',f'href="{prefix}aligned.png"')
 return f'<article id="case-{z["sha"]}-{z["id"]}"><h3>{esc(z["name"])} · 位置 {z["id"]}</h3><p><b>{"已排除" if z["removed"] else "保留候選"}</b> · 分類依據：{z["basis"]}</p>'+pair+f'<p><a href="{prefix}report.html#{anchor}">查看完整照片與此位置 →</a></p></article>'

def main():
 rows=read(OUT/'report-rows.json');before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [OUT/'results.json',OUT/'summary.json']}
 visual={(z['sha'],z['id']):z for z in read(ROOT/'experiments/current_dataset_review/good_visual_categories.json')}
 suspected={(z['sha256'],i) for z in read(OUT/'visual-issues.json') for i in z['removed_ids']}
 for r in rows:
  for mark in r['known_checks']:suspected.update((r['sha256'],i) for i in mark['removed_ids'])
 allitems=[];pages=[]
 for kind,label in [('good','OK'),('bad','NG')]:
  rs=[r for r in rows if r['label']==label and not r['is_reference']];items=[]
  for r in rs:
   result=read(OUT/'photos'/r['sha256']/'result.json')
   with Image.open(OUT/'photos'/r['sha256']/'aligned.png') as im:size=im.size
   for removed,cs in [(False,result['candidates']),(True,result['filtered_candidates'])]:
    for c in cs:
     old=visual.get((r['sha256'],c['id']));key='unknown';basis='尚未逐框目視確認'
     if old and all(old[k]==c[k] for k in ['x','y','w','h']):key=old['category'];basis='沿用先前目視分類，座標已核對'
     elif label=='NG' and removed and (r['sha256'],c['id']) in suspected:key='suspected';basis='既有疑似螺絲位置追蹤'
     elif label=='NG' and (c.get('wire_review') or c.get('aspect',0)>5):key='wire';basis='自動外觀線索，尚未確認是線材'
     elif label=='NG' and not removed and c['classification']['label']=='screw':key='screw';basis='DINO 判定，尚非人工確認'
     items.append(dict(kind=kind,machine=r['machine'],sha=r['sha256'],id=c['id'],name=r['relative'],category=key,basis=basis,removed=removed,candidate=c,size=size,**{k:c[k] for k in ['x','y','w','h']}))
  assert len(items)==sum(r['pre_ai_count'] for r in rs)
  machines=sorted({r['machine'] for r in rs},key=lambda m:(['MPT10','MPT12','KPH33','MPT11'].index(m) if m in ['MPT10','MPT12','KPH33','MPT11'] else 9,m))
  title='良品誤報' if kind=='good' else '不良品檢測';total=sum(r['count'] for r in rs)
  body=R.NAV+f'<h1>{title}：先選機種</h1><div class="answer"><b>{len(rs)} 張照片；保留 {total} 框、排除 {len(items)-total} 框。</b><p>依「機種 → 類型 → 相近位置」檢視；每組先看一組參照／待測圖，可展開同類照片。</p></div>'
  if kind=='good':body+='<p><b>本次良品全部零誤報。</b> 下方類型是已排除候選的回查分類，不是剩餘誤報。106 個沿用先前目視類型，其餘未確認者列待確認。</p>'
  else:body+='<p>本批不良品只有 MPT11；其他機種未提供不良品。外觀類型、DINO 判斷與保留／排除分開呈現。</p>'
  body+='<table><tr><th>機種</th><th>張數</th><th>保留框</th><th>排除框</th><th>開始檢視</th></tr>'
  for m in machines:
   mrows=[r for r in rs if r['machine']==m];zs=[z for z in items if z['machine']==m];keep=sum(not z['removed'] for z in zs)
   body+=f'<tr><td>{m}</td><td>{len(mrows)}</td><td>{keep}</td><td>{len(zs)-keep}</td><td><a href="{file(kind,m)}">進入 {m} →</a></td></tr>'
   overview=R.NAV+f'<h1>{m}：{title}分類檢視</h1><div class="answer">{len(mrows)} 張；保留 {keep} 框、排除 {len(zs)-keep} 框。</div>'
   if kind=='good':overview+='<p>本機種沒有剩餘誤報；以下檢視已被 DINO 排除的位置。</p>'
   for key,(tt,desc) in TYPES.items():
    sub=[z for z in zs if z['category']==key]
    if not sub and key in ['screw','suspected']:continue
    groups=clusters(sub);filename=file(kind,m,key);nk=sum(not z['removed'] for z in sub)
    overview+=f'<article><h2><a href="{filename}">{tt} →</a></h2><p>{len(sub)} 個位置 · {len({z["sha"] for z in sub})} 張照片 · {len(groups)} 組相近位置；保留 {nk}／排除 {len(sub)-nk}</p><p>{desc}</p></article>'
    detail=R.NAV+f'<p><a href="{file(kind,m)}">← 返回 {m} 類型總覽</a></p><h1>{m} / {tt}</h1><p>{desc}</p><p>保留 {nk}／排除 {len(sub)-nk}；相近位置以對齊圖中心距離 45 像素分組，僅用於瀏覽，不代表同一物件。</p><button onclick="document.querySelectorAll(\'details\').forEach(d=>d.open=true)">展開全部同類照片</button> <button onclick="document.querySelectorAll(\'details\').forEach(d=>d.open=false)">收合同類照片</button>'
    if not groups:detail+='<p>目前沒有確認屬於此類型的候選。</p>'
    for i,g in enumerate(groups,1):
     # Prefer retained examples in mixed groups, but include every removed candidate.
     g=sorted(g,key=lambda z:(z['removed'],z['name'],z['id']))
     detail+=f'<section id="group-{i}"><h2>相近位置 {i} · {len(g)} 個框／{len({z["sha"] for z in g})} 張照片</h2>'+card(g[0])
     if len(g)>1:detail+=f'<details><summary>展開另外 {len(g)-1} 個位置對照</summary>'+''.join(card(z) for z in g[1:])+'</details>'
     detail+='</section>'
    R.save(filename,m+' / '+tt,detail,OPEN);pages.append(filename)
   overview+='<details><summary>依照片查看完整清單（含零候選照片）</summary><table><tr><th>照片</th><th>類型</th><th>保留</th><th>排除</th></tr>'
   for r in sorted(mrows,key=lambda r:r['relative']):
    cnt=Counter(z['category'] for z in zs if z['sha']==r['sha256']);links='、'.join(f'<a href="{file(kind,m,k)}">{TYPES[k][0]} {n}</a>' for k,n in cnt.items()) or '無差分候選'
    overview+=f'<tr><td><a href="photos/{r["sha256"]}/report.html">{esc(Path(r["path"]).name)}</a></td><td>{links}</td><td>{r["count"]}</td><td>{r["filtered_count"]}</td></tr>'
   R.save(file(kind,m),m+' 分類總覽',overview+'</table></details>');pages.append(file(kind,m))
  body+='</table><h2>按類型比較機種</h2><table><tr><th>類型</th>'+''.join(f'<th>{m}（保留／排除）</th>' for m in machines)+'</tr>'
  for k,(tt,_) in TYPES.items():
   if k in ['screw','suspected'] and not any(z['category']==k for z in items):continue
   body+='<tr><td>'+tt+'</td>'
   for m in machines:
    sub=[z for z in items if z['category']==k and z['machine']==m];nk=sum(not z['removed'] for z in sub)
    body+=f'<td><a href="{file(kind,m,k)}">{nk}／{len(sub)-nk}</a></td>' if sub or k not in ['screw','suspected'] else '<td>0／0</td>'
   body+='</tr>'
  R.save(kind+'.html',title+'分類檢視',body+'</table>');pages.append(kind+'.html')
  for r in rs:
   m=r['machine'];zs=[z for z in items if z['sha']==r['sha256']];cnt=Counter(z['category'] for z in zs);p=OUT/'photos'/r['sha256']/'report.html';s=p.read_text(encoding='utf-8')
   s=re.sub(r'<!--dino-group-start-->.*?<!--dino-group-end-->','',s,flags=re.S);s=re.sub(r'<!--dino-type-start-->.*?<!--dino-type-end-->','',s,flags=re.S)
   links=' · '.join(f'<a href="../../{file(kind,m,k)}">{TYPES[k][0]} {n} 個</a>' for k,n in cnt.items()) or '沒有差分候選'
   block=f'<!--dino-group-start--><div class="answer"><a href="../../{file(kind,m)}">← 返回 {m} 類型總覽</a><p>本張分類（含排除位置）：{links}</p></div><!--dino-group-end-->'
   s=s.replace('</nav>','</nav>'+block,1)
   for z in zs:
    anchor=('removed-' if z['removed'] else 'candidate-')+str(z['id']);tag=f'<!--dino-type-start--><p>檢視類型：{TYPES[z["category"]][0]} · {z["basis"]} · <a href="../../{file(kind,m,z["category"])}#case-{z["sha"]}-{z["id"]}">查看同類案例 →</a></p><!--dino-type-end-->'
    s,n=re.subn(r'(<article[^>]*id="'+anchor+r'">)',lambda a:a[1]+tag,s,count=1);assert n==1,(r['relative'],anchor)
   p.write_text(s,encoding='utf-8')
  allitems+=items
 assert len(allitems)==2793 and sum(not z['removed'] for z in allitems)==330
 (OUT/'grouped-review-index.json').write_text(json.dumps(dict(total=len(allitems),pages=pages,items=[{k:v for k,v in z.items() if k not in ['candidate','size']} for z in allitems]),ensure_ascii=False,indent=2),encoding='utf-8')
 assert all(hashlib.sha256((OUT/n).read_bytes()).hexdigest()==v for n,v in before.items())
 print('PASS grouped',len(allitems),'positions;',len(pages),'pages; numerical results unchanged')
if __name__=='__main__':main()
