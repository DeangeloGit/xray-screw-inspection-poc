"""Report all59 fixed cases. Explicit correct/wrong outcomes; no inference."""
import sys,json,html,re
from pathlib import Path
from collections import defaultdict
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.contrast_pair_pilot import OUT,PRIOR,read,save,sha
TYPES={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}
FONT='C:/Windows/Fonts/msjh.ttc'
def label(z):return '有螺絲' if z['screw'] else '沒有螺絲'
def main():
 rows=read(OUT/'results.json');base=read(PRIOR/'results.json');summary=read(OUT/'summary.json')
 assert len(rows)==len(base)==59 and all(a['key']==b['key'] for a,b in zip(rows,base))
 assert [rows[n-1]['correct'] for n in [1,2,10]]==[True,True,True]
 assert [n for n in range(5,10) if rows[n-1]['correct']]==[8]
 for z in base:z.setdefault('machine','MPT12');z.setdefault('category','unknown')
 # Generate a visible original-versus-adjusted input proof, without recomputing predictions.
 for n in [1,2,5,6,7,8,9,10]:
  z=base[n-1];canvas=Image.new('RGB',(1000,330),'#f4f7f8');d=ImageDraw.Draw(canvas)
  for col,(kind,side,title) in enumerate([('old','reference','調整前：參照'),('new','reference','調整後：參照'),('old','target','調整前：待測'),('new','target','調整後：待測')]):
   p=Path(z['image_base']+'-'+side+'.png') if kind=='old' else OUT/'images'/f'{n}-{side}.png'
   im=Image.open(p).convert('RGB');d.text((10+col*250,8),title,font=ImageFont.truetype(FONT,21),fill='#173e4b');canvas.paste(im,(10+col*250,50))
  d.text((10,287),'只調明暗；取圖位置、大小、物件形狀都沒改。',font=ImageFont.truetype(FONT,22),fill='#173e4b');canvas.save(OUT/'images'/f'{n}-comparison.png')
 css='''body{margin:0;background:#f4f7f8;color:#173e4b;font:19px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1200px;margin:auto;padding:28px}h1{font-size:32px}h2{font-size:27px}a{color:#007d89}nav{display:flex;gap:22px;flex-wrap:wrap}.answer{background:white;border-left:5px solid #007e88;padding:22px}.warn{border-left-color:#b52b32}article{background:white;border:1px solid #d7e2e6;border-radius:10px;padding:22px;margin:24px 0}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border:1px solid #d7e2e6;text-align:left}th{background:#e6eff2}img.pair{width:100%;max-width:1000px;height:auto}.note{font-size:16px;overflow-wrap:anywhere}summary{padding:12px;cursor:pointer}figure{display:inline-block;margin:8px 22px 8px 0}figure img{width:224px}.wrong{color:#b52b32}.right{color:#007565}pre{white-space:pre-wrap;font-size:14px}'''
 nav='<nav><a href="index.html">本輪結果</a><a href="screws.html#original">原本兩顆</a><a href="screws.html#five">五處逐張判對／判錯</a><a href="normal.html">線材與全部正常案例</a><a href="methods.html">做法與未採用實驗</a></nav>'
 def write(name,title,body):
  (OUT/name).write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style><main>{nav}{body}</main></html>',encoding='utf-8')
 def path(n):return 'normal.html' if base[n-1]['group']=='normal' else 'screws.html'
 def verdict(n,p):
  correct=not p['keep'] if base[n-1]['group']=='normal' else p['keep']
  return '判對' if correct else '判錯：誤報線材／正常物件' if base[n-1]['group']=='normal' else '判錯：漏報新增螺絲'
 def table(n):
  z=base[n-1];r=rows[n-1];b='<table><tr><th>方法</th><th>參照圖</th><th>待測圖</th><th>本例對不對？</th></tr>'
  for name,p in [('原本正式 DINO',z['baseline']),('上一輪：各占一半',z['equal']),('本輪：先統一明暗，再各占一半',r['new'])]:
   b+=f'<tr><td>{name}</td><td>{label(p["reference"])}</td><td>{label(p["target"])}</td><td><b>{verdict(n,p)}</b></td></tr>'
  return b+'</table>'
 def card(n):
  z=base[n-1];r=rows[n-1];b=f'<article id="case-{n}"><h3>{html.escape(z["name"])} · 位置 {z["id"]}</h3><p><b class="{"right" if r["correct"] else "wrong"}">本輪：{verdict(n,r["new"])}</b></p>'
  if z['group']=='five_visual_screws':b+='<p class="note">本例預期：參照沒有新增這顆螺絲，待測有；依助手對照圖核對。按此預期明確計算對錯，沒有更動使用者人工紀錄。</p>'
  b+=f'<img class="pair" loading="lazy" src="{Path(z["context"]).as_uri()}">'+table(n)
  if (OUT/'images'/f'{n}-comparison.png').exists():b+=f'<details><summary>看 AI 小圖明暗調整前後</summary><img class="pair" src="images/{n}-comparison.png"></details>'
  else:
   b+='<details><summary>看本輪 DINO 實際收到的兩張小圖</summary>'
   for side,title in [('reference','參照圖'),('target','待測圖')]:b+=f'<figure><figcaption>{title}</figcaption><img loading="lazy" src="images/{n}-{side}.png"></figure>'
   b+='</details>'
  if z['group']=='normal':back=f'<a href="normal.html#machine-{z["machine"]}">返回此機種</a> · <a href="normal.html#category-{z["machine"]}-{z["category"]}">查看同類案例</a>'
  else:back='<a href="screws.html#five">返回五處核對</a>' if z['group']=='five_visual_screws' else '<a href="screws.html#original">返回螺絲總覽</a>'
  b+=f'<p><a href="{(Path(z["source"])/"reference.png").as_uri()}">完整參照圖</a> · <a href="{(Path(z["source"])/"aligned.png").as_uri()}">完整待測圖</a> · {back}</p></article>'
  return b
 body='''<h1>原本兩顆保住了、線材不再誤報；五處漏判救回一處</h1><div class="answer"><b>這次改法：先統一圖片明暗，再用原本各占一半的方法。</b><p>完整47＋65張範例、參照圖、待測圖都做相同處理。取圖位置、大小和形狀不變，沒有把測試案例加進範例。</p></div><h2>先回答：那五個案例到底對不對？</h2><p><b>上一輪五個全錯，全部漏報。本輪一個改對，另外四個仍錯。</b>依本輪參照／待測圖核對，這五處都應報新增螺絲；不再用「0個判出」代替說明對錯。這是助手的目視預期，使用者原人工標記不變。</p><h2>同一批59個位置的結果</h2><table><tr><th>組別</th><th>原本正式 DINO</th><th>上一輪各占一半</th><th>本輪先調明暗</th></tr><tr><td>原本問題：斜螺絲#94、圓頭#34</td><td>0／2 判對</td><td>2／2 判對</td><td><b>2／2 判對</b></td></tr><tr><td>五個額外漏判位置</td><td>0／5 判對</td><td>0／5 判對</td><td><b>1／5 判對，4個仍錯</b></td></tr><tr><td>另外兩個已有螺絲標記</td><td>2／2 判對</td><td>2／2 判對</td><td>2／2 判對</td></tr><tr><td>50個正常位置</td><td>0個誤報</td><td>1個線材誤報</td><td><b>0個誤報</b></td></tr></table><p>螺絲「判對」必須參照判沒有、待測判有。所有結果都使用同一批位置，沒有換掉失敗案例。</p><h2>新增的線材誤報：本輪改對</h2>'''
 body+=f'<img class="pair" src="{Path(base[9]["context"]).as_uri()}">'+table(10)+'<p><a href="normal.html#case-10">看線材小圖調整前後及完整來源 →</a></p><h2>五處逐一看：一處改對、四處仍錯</h2><table><tr><th>照片／位置</th><th>上一輪</th><th>本輪</th><th>本輪錯在哪裡？</th></tr>'
 for n in range(5,10):
  z=base[n-1];p=rows[n-1]['new'];reason='已符合參照無、待測有' if p['keep'] else '待測仍判沒有螺絲' if not p['target']['screw'] else '兩張都判有螺絲，沒報新增'
  body+=f'<tr><td><a href="screws.html#case-{n}">{html.escape(z["name"])}／{z["id"]}</a></td><td>判錯</td><td><b>{"改對" if p["keep"] else "仍判錯"}</b></td><td>{reason}</td></tr>'
 body+='</table><h2>救回的是哪一顆？</h2><p>MPT11／3-10.tiff 位置1的長螺絲。調整前待測被判成沒有；調整後，參照判沒有、待測判有。</p>'+f'<img class="pair" src="{Path(base[7]["context"]).as_uri()}">'+table(8)+'<p><a href="screws.html#original">查看原本兩顆的前後結果</a> · <a href="screws.html#five">看五個額外位置的全部對照圖</a> · <a href="normal.html">看全部50個正常位置</a></p>'
 body+='<h2>具體做法</h2><p>同一張小圖可能偏暗，範例卻偏亮，讓外觀比較受影響。本輪把每張圖片的明暗範圍拉到一致，再送給 DINO。螺絲、正常範例及兩張測試圖全部用同一規則，沒有依答案決定怎麼處理。</p><p>這證明同批案例的分類確實有改善，但不能證明明暗差是所有錯誤的唯一原因。四處漏判仍未解決，也尚未驗證新照片。</p><div class="answer warn"><b>尚未改正式流程。</b>模型、47＋65範例、原始圖資和人工紀錄均保留。本輪只做離線小實驗，沒有重跑整批差分。</div>'
 write('index.html','同批改善：原本兩顆、線材與五處漏判',body)
 body='<h1>螺絲逐例：直接標示判對或判錯</h1><section id="original"><h2>原本沒判對的兩顆螺絲</h2>'+card(1)+card(2)+'</section><section id="five"><h2>五個額外漏判：上一輪全錯，本輪一對四錯</h2>'+''.join(card(n) for n in range(5,10))+'</section><section id="other"><h2>另外兩個原本就判對的位置</h2>'+card(3)+card(4)+'</section>'
 write('screws.html','螺絲對照：哪個改對、哪個仍錯',body)
 body='<h1>50個正常位置：沒有新增誤報</h1><p>先看指定線材誤報，再依機種 → 類型 → 相近位置檢視全部案例。類型沿用前輪助手目視分類。</p><p><a href="#case-10">直接看KPH33原誤報線材 →</a></p>'
 for machine in ['MPT10','MPT12','KPH33','MPT11']:
  nums=[n for n,z in enumerate(base,1) if z['group']=='normal' and z['machine']==machine];body+=f'<section id="machine-{machine}"><h2>{machine} · {len(nums)}個位置</h2>'
  for cat,title in TYPES.items():
   ns=[n for n in nums if base[n-1]['category']==cat];body+=f'<section id="category-{machine}-{cat}"><h3>{title} · {len(ns)}個位置</h3>'
   groups=defaultdict(list)
   for n in ns:
    c=base[n-1]['c'];groups[(int((c['x']+c['w']/2)//80),int((c['y']+c['h']/2)//80))].append(n)
   for group,items in groups.items():
    body+=f'<h4>相近位置 · {len(items)}個案例</h4>'+card(items[0])
    if len(items)>1:body+=f'<details><summary>展開其餘{len(items)-1}個同類照片</summary>'+''.join(card(n) for n in items[1:])+'</details>'
   if not ns:body+='<p>數量0。</p>'
   body+='</section>'
  body+='</section>'
 body+='<script>function show(){const n=document.getElementById(location.hash.slice(1));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView()}show();addEventListener("hashchange",show)</script>'
 write('normal.html','同批全部正常案例',body)
 training=read(PRIOR/'summary.json');gate=read(ROOT/'workspace/dino-through-line-20261103/summary.json')
 body='''<h1>做了哪些實驗，哪些沒有採用？</h1><table><tr><th>做法</th><th>原本兩顆判對</th><th>五處額外漏判救回</th><th>50個正常誤報</th></tr><tr><td>上一輪：各占一半</td><td>2／2</td><td>0／5</td><td>1</td></tr>'''
 body+=f'<tr><td>讓既有範例學習整體與局部的組合規則</td><td>{training["original_screw"]["new_kept"]}／2</td><td>{training["five_visual_screws"]["new_kept"]}／5</td><td>{training["normal"]["new_kept"]}</td></tr><tr><td>各占一半＋跨越兩側的連續深色區排除規則</td><td>{gate["original_screw"]["kept"]}／2</td><td>{gate["five_visual_screws"]["kept"]}／5</td><td>{gate["normal"]["kept"]}</td></tr><tr><td>本輪較佳結果：先統一明暗，再各占一半</td><td>2／2</td><td>1／5</td><td>0</td></tr></table>'
 body+='''<p>學習組合規則的做法雖排除了線材，卻把原本兩顆弄錯，因此不採用。線材連續性規則保住兩顆、排除線材，但沒有救回五處漏判；那是額外幾何規則，不是DINO自己學會辨識。本頁主結果採明暗調整，沒有疊加該幾何規則。</p><h2>明暗處理規則</h2><p>固定取每張小圖亮度的第1與第99百分位作為黑白端點，做線性拉伸，兩端截斷。範例、參照、待測一視同仁；模型仍用原權重與47＋65張範例，沒有新增訓練答案、手改某張座標、搜尋最有利門檻。</p><h2>怎麼判五處的對錯？</h2><p>依助手重新看參照／待測對照圖，本輪預期五處都應報新增螺絲。未達「參照沒有、待測有」就標判錯。這是明確記錄的目視預期，不冒充使用者既有標記，也不修改人工紀錄。</p><h2>本次限制</h2><p>所有方法都是在反覆研究的同批59個位置上開發。明暗規則事前固定，但本輪較佳方法仍是看過這批結果後比較得出，不能稱獨立驗收。螺絲範例缺完整原始來源，仍有無法完全排除同來源的限制。新法線材判非螺絲的差距也不大，不宣稱已經穩定解決所有線材。</p>'''
 body+='<p><a href="rules.json">明暗調整規則</a> · <a href="results.json">全部59個本輪結果</a> · <a href="summary.json">統計</a> · <a href="../dino-learn-joint-20261103/training.json">組合規則學習紀錄</a> · <a href="../dino-through-line-20261103/results.json">線材規則結果</a> · <a href="preservation.json">正式資料未變</a> · <a href="validation.json">報告核對</a></p>'
 write('methods.html','實驗規則與未採用方法',body)
 # Validate every linked artifact and all59 uniquely enumerated case cards.
 from urllib.parse import urlparse,unquote
 missing=[];cards=[];links=0
 for name in ['index.html','screws.html','normal.html','methods.html']:
  f=OUT/name;s=f.read_text(encoding='utf-8');cards+=re.findall(r'<article id="case-(\d+)"',s)
  for u in re.findall(r'(?:src|href)="([^"]+)"',s):
   if u=='validation.json':continue
   q=urlparse(u);p=Path(unquote(q.path).lstrip('/')) if q.scheme=='file' else OUT/q.path if q.path else f;links+=1
   if not p.is_file():missing.append(str(p))
   elif q.fragment and p.suffix=='.html' and f'id="{unquote(q.fragment)}"' not in p.read_text(encoding='utf-8'):missing.append(u)
 assert not missing,missing
 assert sorted(map(int,cards))==list(range(1,60))
 protected=read(OUT/'preservation-before.json');assert all(sha(Path(p))==v for p,v in protected.items())
 save(OUT/'validation.json',dict(case_cards=len(cards),links_checked=links,missing=missing,protected_unchanged=True,group_counts={'original_screw':2,'five_visual_screws':5,'extra_confirmed':2,'normal':50}))
 print(json.dumps(dict(report=str(OUT/'index.html'),cases=59,links=links,summary=summary),ensure_ascii=False))
if __name__=='__main__':main()
