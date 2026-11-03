"""Machine -> visually reviewed false-alarm type -> nearby-location review galleries."""
import json,sys,math,re
from pathlib import Path
from collections import Counter
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.current_dataset_review.report import OUT,read,save,esc,pair,stats,NAV
CATEGORIES={'wire':('線材位移／線束外觀','兩圖可見線材走向、彎曲或線束輪廓不同。'),'edge':('板件邊界差異','細長候選位於既有板件邊界，兩圖邊界位置或灰階不同。'),'component':('原有元件灰階／外觀差異','候選位於電路元件或紋理區，兩圖灰階或元件外觀不同。'),'structure':('U 形結構／輪廓差異','兩圖的 U 形固定結構位置或輪廓不同。'),'unknown':('局部深色點：待確認','局部深色點的來源僅靠這組裁圖仍不明確，保留單獨檢視。')}
def machine_link(m):return f'good-{m}.html'
def category_link(m,k):return f'good-{m}-{k}.html'
def gallery_card(z):
 row,c=z['row'],z['candidate'];prefix='photos/'+z['sha']+'/'
 with Image.open(OUT/prefix/'aligned.png') as im:w,h=im.size
 comparison=pair(c,w,h).replace('href="reference.png"',f'href="{prefix}reference.png"').replace('href="aligned.png"',f'href="{prefix}aligned.png"')
 name=Path(row['path']).name
 return f'<article id="case-{z["sha"]}-{z["id"]}"><h3>{esc(name)} · 位置 {z["id"]}</h3>'+comparison+f'<p><a href="{prefix}report.html#candidate-{z["id"]}">查看這張完整照片與所有框 →</a></p></article>'
def clusters(items):
 groups=[]
 for z in sorted(items,key=lambda z:(z['y'],z['x'],z['name'])):
  cx,cy=z['x']+z['w']/2,z['y']+z['h']/2
  group=next((g for g in groups if math.hypot(cx-g[0]['x']-g[0]['w']/2,cy-g[0]['y']-g[0]['h']/2)<=45),None)
  if group is None:groups.append([z])
  else:group.append(z)
 return sorted(groups,key=lambda g:-len(g))
def main():
 rows=[r for r in read(OUT/'report-rows.json') if r['label']=='OK' and not r['is_reference']]
 indexed={r['sha256']:r for r in rows};items=read(Path(__file__).with_name('good_visual_categories.json'));seen=set()
 for z in items:
  z['row']=indexed[z['sha']];r=read(OUT/'photos'/z['sha']/'result.json');z['candidate']=next(c for c in r['candidates'] if c['id']==z['id'])
  assert all(z[k]==z['candidate'][k] for k in ('x','y','w','h'))
  assert (z['sha'],z['id']) not in seen;seen.add((z['sha'],z['id']))
 assert len(seen)==sum(r['count'] for r in rows)==106
 machines=sorted({r['machine'] for r in rows},key=lambda x:(x!='MPT10',x!='MPT12',x))
 body=NAV+'<h1>良品誤報 Review：先選機種</h1><p>139 張良品，79 張有誤報，共 106 個位置。以下按機種、誤報外觀類型整理。</p><p>類型來自本次逐框目視對照，與 CLIP 的分類分開；相近畫面位置再排成一組，方便比較重複誤報。</p><table><tr><th>機種</th><th>良品張數</th><th>有誤報照片</th><th>誤報位置</th><th>開始檢視</th></tr>'
 for m in machines:
  rs=[r for r in rows if r['machine']==m];s=stats(rs)
  body+=f'<tr><td>{m}</td><td>{len(rs)}</td><td>{s["positive"]}</td><td>{s["after"]}</td><td><a href="{machine_link(m)}">進入 {m} →</a></td></tr>'
 body+='</table><h2>按誤報類型比較機種</h2><table><tr><th>誤報類型</th>'+''.join(f'<th>{m}</th>' for m in machines)+'<th>合計</th></tr>'
 for k,(title,_) in CATEGORIES.items():
  body+=f'<tr><td>{title}</td>'
  for m in machines:
   n=sum(z['machine']==m and z['category']==k for z in items)
   body+=f'<td><a href="{category_link(m,k)}">{n} 個位置 →</a></td>' if n else '<td>0</td>'
  body+=f'<td>{sum(z["category"]==k for z in items)}</td></tr>'
 body+='</table>';save('good.html','良品誤報：按機種與類型檢視',body)
 pages=['good.html'];categories={}
 for m in machines:
  rs=[r for r in rows if r['machine']==m];zs=[z for z in items if z['machine']==m];s=stats(rs)
  body='<nav><a href="good.html">所有機種</a><a href="index.html">總結果</a></nav>'+f'<h1>{m}：良品誤報</h1><div class="answer">{len(rs)} 張良品，{s["positive"]} 張有誤報、{s["zero"]} 張零誤報；剩餘 {s["after"]} 個誤報位置。</div>'
  if not zs:body+='<p>這個機種目前沒有剩餘誤報。</p>'
  for k,(title,description) in CATEGORIES.items():
   subset=[z for z in zs if z['category']==k]
   if not subset:continue
   clusters_count=len(clusters(subset));categories[m+'/'+k]=len(subset)
   body+=f'<article><h2><a href="{category_link(m,k)}">{title} →</a></h2><p>{len(subset)} 個位置 · {len({z["sha"] for z in subset})} 張照片 · {clusters_count} 組相近位置</p><p>{description}</p></article>'
   detail=f'<nav><a href="good.html">所有機種</a><a href="{machine_link(m)}">{m} 類型總覽</a></nav><h1>{m} / {title}</h1><p>{description}</p><p>{len(subset)} 個位置，依畫面中的相近位置整理。每組先顯示一張，展開即可逐張比較。</p><p><button onclick="document.querySelectorAll(\'details\').forEach(d=>d.open=true)">展開所有照片</button> <button onclick="document.querySelectorAll(\'details\').forEach(d=>d.open=false)">收合重複照片</button></p>'
   for n,group in enumerate(clusters(subset),1):
    detail+=f'<section><h2>相近位置 {n} · {len(group)} 個框／{len({z["sha"] for z in group})} 張照片</h2>'+gallery_card(group[0])
    if len(group)>1:detail+=f'<details><summary>展開另外 {len(group)-1} 個位置對照</summary>'+''.join(gallery_card(z) for z in group[1:])+'</details>'
    detail+='</section>'
   save(category_link(m,k),m+' / '+title,detail,"const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));let node=target;while(node){if(node.tagName==='DETAILS')node.open=true;node=node.parentElement}if(target)target.scrollIntoView();");pages.append(category_link(m,k))
  body+='<details><summary>依照片查看此機種完整清單（含零誤報照片）</summary><table><tr><th>照片</th><th>誤報類型</th><th>剩餘框</th><th>已排除</th></tr>'
  for r in sorted(rs,key=lambda r:(r['count']==0,Path(r['path']).name)):
   cats=Counter(z['category'] for z in zs if z['sha']==r['sha256']);desc='、'.join(CATEGORIES[k][0]+f' {n}' for k,n in cats.items()) or '零誤報'
   url='photos/'+r['sha256']+'/report.html'
   body+=f'<tr><td><a href="{url}">{esc(Path(r["path"]).name)}</a></td><td>{desc}</td><td>{r["count"]}</td><td><a href="{url}#removed">{r["filtered_count"]}</a></td></tr>'
  body+='</table></details>';save(machine_link(m),m+' 良品誤報分類',body);pages.append(machine_link(m))
 # Add type navigation directly to each original single-photo review page.
 for row in rows:
  m=row['machine'];path=OUT/'photos'/row['sha256']/'report.html';text=path.read_text(encoding='utf-8')
  text=re.sub(r'<!--good-review-start-->.*?<!--good-review-end-->','',text,flags=re.S)
  zs=[z for z in items if z['sha']==row['sha256']];counts=Counter(z['category'] for z in zs)
  links=' · '.join(f'<a href="../../{category_link(m,k)}">{CATEGORIES[k][0]} {n} 個</a>' for k,n in counts.items()) or '這張沒有剩餘誤報'
  block=f'<!--good-review-start--><div class="answer"><a href="../../{machine_link(m)}">← 回到 {m} 誤報總覽</a><p>本張類型：{links}</p></div><!--good-review-end-->'
  text=text.replace('</nav>','</nav>'+block,1)
  for z in zs:
   marker=f'<!--type-{z["id"]}-start-->';end=f'<!--type-{z["id"]}-end-->'
   text=re.sub(re.escape(marker)+'.*?'+re.escape(end),'',text,flags=re.S)
   tag=marker+f'<p><a href="../../{category_link(m,z["category"])}#case-{z["sha"]}-{z["id"]}">目視分類：{CATEGORIES[z["category"]][0]} · 查看同類案例</a></p>'+end
   pattern=r'(<article data-label="[^"]+" id="candidate-'+str(z['id'])+r'">)'
   text=re.sub(pattern,lambda match:match[1]+tag,text,count=1)
  path.write_text(text,encoding='utf-8')
 (OUT/'good-review-index.json').write_text(json.dumps(dict(total=106,categories=categories,pages=pages,classification='manual visual appearance review',items=[{k:v for k,v in z.items() if k not in ('row','candidate')} for z in items]),ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(total=106,categories=categories,pages=len(pages))))
if __name__=='__main__':main()
