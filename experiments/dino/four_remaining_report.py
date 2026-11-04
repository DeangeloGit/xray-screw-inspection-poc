"""Report the same59 development cases, using saved outputs only."""
import sys,html,re,json
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse,unquote
from PIL import Image
import hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.four_remaining_pilot import OUT,PREV,BASE,read,save,sha
TYPES={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}
ANALYSIS={
5:('仍錯：待測螺絲仍被判成沒有。','整體外觀比較稍微偏向螺絲，但小區域平均更偏向正常範例，合起來判成沒有。正常範例多是板件背景；這是實際比對結果，不能據此斷言模型只看背景。','試過依差異換成方形框，仍判錯。因此本輪沒有靠換框解決。下一個具體方向是讓小區域只比較差異物件內部，避免把整塊板件一起平均；參照與待測用同一範圍，正常線材也一起驗證。此方向尚未實作，不能當成果。'),
6:('改對：參照沒有螺絲、待測有螺絲。','原框同時包含旁邊原有的黑色圓環，參照也被判成有螺絲，於是漏報新增物件。','用差異找到物件範圍，只做一次固定取圖補查。黑色圓環的占比變小後，參照改判沒有、待測仍判有。這支持背景占比會影響結果；新框仍含一部分圓環，不能宣稱已精準分離物件。'),
7:('仍錯：待測螺絲仍被判成沒有。','整體外觀、小區域平均都更偏向正常範例；正常範例中可見相似的板件背景。螺絲外緣靠近原本小圖邊界，但換框後仍錯，不能把原因全歸給裁切。','固定換框仍未判對，而且差異範圍混入上下背景。下一步同1.png：比較物件內部的小區域，並保留整體外觀作核對；不刪正常範例、不改門檻來配合答案。此方向尚未驗證。'),
9:('仍錯：參照與待測都判有螺絲。','參照裡原有的黑色圓環被比到螺絲範例。縮框後仍留下較多圓環，參照依然判有，所以沒報新增。','本輪縮框不足以解決。下一步要檢驗：參照中最像螺絲的區域，是否真的落在待測新增物件的相同位置；不能只因整張小圖某處像螺絲就刪除。需同時測線材移動，不能把所有差異都當螺絲。此方向尚未驗證。')}

def main():
 base=read(BASE/'results.json');rows=read(OUT/'restricted-results.json');raw=read(OUT/'results.json');summary=read(OUT/'restricted-summary.json')
 assert len(base)==len(rows)==len(raw)==59
 for a,b,c in zip(base,rows,raw):
  assert a['key']==b['key']==c['key'];a.setdefault('machine','MPT12');a.setdefault('category','unknown')
  for side in ['reference','target']:
   im=Image.open(OUT/'images'/f'{b["number"]}-final-{side}.png').convert('RGB')
   assert hashlib.sha256(im.tobytes()).hexdigest()==b['input_hashes'][side]
  assert b['new']['keep']==(b['new']['target']['screw'] and not b['new']['reference']['screw'])
 css='''body{margin:0;background:#f4f7f8;color:#173e4b;font:19px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1220px;margin:auto;padding:28px}nav{display:flex;gap:22px;flex-wrap:wrap}a{color:#007d89}h1{font-size:32px}h2{font-size:27px}article,.answer{background:white;border:1px solid #d7e2e6;padding:24px;margin:24px 0;border-radius:8px}.answer{border-left:5px solid #007d89}.warn{border-left-color:#b52b32}table{width:100%;border-collapse:collapse;background:white}td,th{padding:12px;border:1px solid #d7e2e6;text-align:left}th{background:#e6eff2}img.pair{width:100%;max-width:1200px;height:auto}figure{display:inline-block;margin:12px 24px 12px 0}figure img{width:224px;max-width:100%;height:auto}.note{font-size:16px;overflow-wrap:anywhere}.right{color:#007565}.wrong{color:#b52b32}summary{padding:12px;cursor:pointer}details{margin:12px 0}h3,td{overflow-wrap:anywhere}'''
 nav='<nav><a href="index.html">本輪結果</a><a href="screws.html#four">四處哪個改對</a><a href="screws.html#protected">原本兩顆與長螺絲</a><a href="normal.html">全部正常案例</a><a href="attempt.html">失敗做法與限制</a></nav>'
 def write(name,title,body):
  (OUT/name).write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style><main>{nav}{body}</main><script>function show(){{const n=document.getElementById(location.hash.slice(1));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView()}}show();addEventListener("hashchange",show)</script></html>',encoding='utf-8')
 def lab(v):return '有螺絲' if v['screw'] else '沒有螺絲'
 def verdict(n,p):
  normal=base[n-1]['group']=='normal';correct=not p['keep'] if normal else p['keep']
  return '判對：沒有誤報' if normal and correct else '判錯：誤報正常物件' if normal else '判對：參照沒有、待測有' if correct else '判錯：漏報新增螺絲'
 def table(n,attempt=False):
  r=rows[n-1];out='<table><tr><th>方法</th><th>參照圖判斷</th><th>待測圖判斷</th><th>對或錯</th></tr>'
  methods=[('上一輪：統一明暗',r['baseline']),('本輪：限定兩圖都像螺絲才補查',r['new'])]
  if attempt:methods.insert(1,('未採用：所有漏報都嘗試換框',raw[n-1]['new']))
  for name,p in methods:out+=f'<tr><td>{name}</td><td>{lab(p["reference"])}</td><td>{lab(p["target"])}</td><td><b>{verdict(n,p)}</b></td></tr>'
  return out+'</table>'
 def card(n):
  z=base[n-1];r=rows[n-1];m=z['machine'];cat=z['category'];normal=z['group']=='normal';page='normal.html' if normal else 'screws.html'
  s=f'<article id="case-{n}"><h3>{html.escape(z["name"])} · 位置 {z["id"]}</h3><p><b class="{"right" if r["correct"] else "wrong"}">{verdict(n,r["new"])}</b></p>'
  s+=f'<p class="note">分類：{m}／{TYPES[cat]}。'+('沿用助手目視類型，非新增人工確認。' if normal else '此處不臆測誤報類型。')+'</p>'
  if z['group']=='five_visual_screws':s+='<p class="note">對錯依助手核對參照／待測圖所建立的「新增螺絲」預期評分；不是新增使用者確認標籤，原人工紀錄未改。</p>'
  if n in ANALYSIS:
   title,cause,method=ANALYSIS[n];s+=f'<p><b>錯在哪裡：</b>{cause}</p><p><b>本輪處理與後續方向：</b>{method}</p>'
  s+=f'<p>下面依序是參照圖與待測圖。</p><img class="pair" loading="lazy" src="{Path(z["context"]).as_uri()}" alt="參照與待測同位置對照">'+table(n)
  s+='<p>'+('本例實際啟用固定取圖補查。' if r['rechecked'] else '本例沿用上一輪實際雙圖結果；未啟用換框補查。')+'</p>'
  s+='<details><summary>看本輪判斷所使用的兩張小圖</summary>'
  for side,title in [('reference','參照圖'),('target','待測圖')]:s+=f'<figure><figcaption>{title}</figcaption><img loading="lazy" src="images/{n}-final-{side}.png" alt="{title}模型輸入"></figure>'
  s+='</details>'
  if n in ANALYSIS:
   s+=f'<details><summary>原框與固定新框：上排參照，下排待測</summary><img class="pair" loading="lazy" src="images/{n}-geometry.png"><p>圖中文字「尚未看新分數」記錄先疊框、後推論的檢查順序。藍框為上一輪AI取圖範圍；橘框為本輪嘗試的範圍，不是正式檢測紅框。</p></details>'
   s+=f'<details><summary>查看上一輪實際比到的螺絲／正常範例</summary><img class="pair" loading="lazy" src="images/{n}-neighbors.png"><p>每類最像三張的結果；分數僅放此附加說明。這是相似範例，不是證明模型注視哪個像素的圖。</p></details>'
  s+=f'<p><a href="{(Path(z["source"])/"reference.png").as_uri()}">完整參照圖</a> · <a href="{(Path(z["source"])/"aligned.png").as_uri()}">完整待測圖</a> · <a href="{page}#machine-{m}">返回此機種</a> · <a href="{page}#category-{m}-{cat}">查看同類案例</a></p></article>'
  return s
 body='''<h1>四處漏判：1處改對，3處仍錯</h1><div class="answer"><b>本輪改對：MPT11／8.png／位置5。</b><p>原本兩顆、上輪救回的長螺絲都維持「參照沒有、待測有」。同批50個正常位置仍是0個誤報。</p><p>沒有改正式流程。本報告是依本次要求，驗證固定59個位置的小實驗，不是重跑全圖資的驗收報告。</p></div><h2>整批59個位置的結果</h2><table><tr><th>組別</th><th>本輪結果</th></tr><tr><td>原本兩顆問題螺絲</td><td>2個都判對</td></tr><tr><td>上輪救回的長螺絲：3-10.tiff／位置1</td><td>維持判對</td></tr><tr><td>本輪剩下四處</td><td><b>1個改對、3個仍錯</b></td></tr><tr><td>另外兩個既有螺絲標記</td><td>2個都判對</td></tr><tr><td>50個正常位置（42線材、2板件邊界、4元件、2U形結構）</td><td><b>0個誤報</b></td></tr></table><p>「螺絲判對」一定要參照判沒有、待測判有，沒有用「保留待確認」代替。正常位置以是否誤報新增螺絲評分。</p><h2>剩下四處，直接看對錯</h2><table><tr><th>照片／位置</th><th>上一輪</th><th>本輪</th><th>結果說明</th></tr>'''
 for n in [5,6,7,9]:
  z=base[n-1];r=rows[n-1];body+=f'<tr><td><a href="screws.html#case-{n}">{z["name"]}／{z["id"]}</a></td><td>判錯</td><td><b>{"改對" if r["correct"] else "仍錯"}</b></td><td>{ANALYSIS[n][0]}</td></tr>'
 body+='''</table><h2>這輪到底改了什麼？</h2><p>只針對「參照和待測都被判成有螺絲」的情況補查：用局部差異找物件範圍，兩張圖截同一個位置，再各自交給DINO判斷。固定只取一個框，不到處試框選最高分。</p><p>其餘情況保留上一輪實際判斷。原本兩顆和長螺絲本來就符合雙圖規則，因此沿用結果；這不是新補查方法重新證明了它們都能辨識。</p><p>全部47張螺絲＋65張正常範例仍在，明暗處理、各占一半的比較及門檻不變。</p><div class="answer warn"><b>為什麼限制補查？</b><p>先試「所有漏報都換框」時，雖然也救回8.png，卻新增兩處線材誤報。這個通用做法不採用。後來加上上述限制，同批才恢復0誤報。這是看過結果後的開發修正，還不是新資料上的獨立驗證。</p><a href="attempt.html">看兩處新增線材誤報與完整限制 →</a></div><h2>先看改對的8.png</h2>'''
 body+=f'<img class="pair" src="{Path(base[5]["context"]).as_uri()}">'+table(6)+'<p><a href="screws.html#case-6">看疊框與DINO實際小圖 →</a></p><p><a href="screws.html#four">看四處原因與對照圖</a> · <a href="normal.html">看全部50個正常位置</a></p>'
 write('index.html','剩下四處：1處改對、3處仍錯',body)
 body='<h1>螺絲逐例：改對與仍錯</h1><section id="four"><h2>本輪四處</h2><p><a href="#case-5">1.png仍錯</a> · <a href="#case-6">8.png改對</a> · <a href="#case-7">2.png仍錯</a> · <a href="#case-9">5.png仍錯</a></p></section><section id="protected"><h2>要維持判對的三顆</h2><p><a href="#case-1">原本斜螺絲</a> · <a href="#case-2">原本圓頭螺絲</a> · <a href="#case-8">上輪救回的長螺絲</a>：本輪均維持判對。</p></section>'
 for machine in ['MPT10','MPT12','KPH33','MPT11']:
  ns=[n for n in range(1,10) if base[n-1]['machine']==machine];body+=f'<section id="machine-{machine}"><h2>{machine} · {len(ns)}個位置</h2>'
  for cat,title in TYPES.items():
   nums=[n for n in ns if base[n-1]['category']==cat];body+=f'<section id="category-{machine}-{cat}"><h3>{title} · {len(nums)}</h3>'
   groups=defaultdict(list)
   for n in nums:
    c=base[n-1]['c'];groups[(int((c['x']+c['w']/2)//80),int((c['y']+c['h']/2)//80))].append(n)
   for key,items in groups.items():
    body+=f'<h4>相近位置 · {len(items)}個案例</h4>'+card(items[0])
    if len(items)>1:body+=f'<details><summary>展開其餘{len(items)-1}個同類照片</summary>'+''.join(card(n) for n in items[1:])+'</details>'
   if not nums:body+='<p>數量0。</p>'
   body+='</section>'
  body+='</section>'
 write('screws.html','九個螺絲位置：六對三錯',body)
 body='<h1>全部50個正常位置：0個新增誤報</h1><p>沿用同一批案例，沒有移除線材或板件。順序：機種 → 類型 → 相近位置。分類是助手目視歸類，沒有改寫人工紀錄。</p>'
 for machine in ['MPT10','MPT12','KPH33','MPT11']:
  ns=[n for n in range(10,60) if base[n-1]['machine']==machine];body+=f'<section id="machine-{machine}"><h2>{machine} · {len(ns)}個位置</h2>'
  for cat,title in TYPES.items():
   nums=[n for n in ns if base[n-1]['category']==cat];body+=f'<section id="category-{machine}-{cat}"><h3>{title} · {len(nums)}</h3>'
   groups=defaultdict(list)
   for n in nums:
    c=base[n-1]['c'];groups[(int((c['x']+c['w']/2)//80),int((c['y']+c['h']/2)//80))].append(n)
   for key,items in groups.items():
    body+=f'<h4>相近位置 · {len(items)}個案例</h4>'+card(items[0])
    if len(items)>1:body+=f'<details><summary>展開其餘{len(items)-1}個同類照片</summary>'+''.join(card(n) for n in items[1:])+'</details>'
   if not nums:body+='<p>數量0。</p>'
   body+='</section>'
  body+='</section>'
 write('normal.html','全部正常案例與對照圖',body)
 body='''<h1>失敗做法也列出，不只展示成功</h1><table><tr><th>方法</th><th>四處救回幾個</th><th>原本兩顆＋長螺絲</th><th>50正常誤報</th></tr><tr><td>上一輪統一明暗</td><td>0</td><td>3個判對</td><td>0</td></tr><tr><td>所有漏報都嘗試固定換框</td><td>1</td><td>沿用原結果，3個判對</td><td><b>2：不採用</b></td></tr><tr><td>本輪：只補查兩圖都像螺絲</td><td>1</td><td>沿用原結果，3個判對</td><td>0</td></tr></table><p>通用做法59處中有19處通過幾何檢查並補查；限定後只剩8.png／位置5與5.png／位置5兩處。正常案例未進入限定補查，因此0誤報代表限制有效避免本輪新增錯誤，不代表DINO已學會所有線材。</p><h2>通用換框法新增的兩處線材誤報</h2>'''
 for n in [44,50]:
  z=base[n-1];body+=f'<article><h3>{z["name"]}／位置{z["id"]}</h3><img class="pair" src="{Path(z["context"]).as_uri()}">'+table(n,True)
  for side,title in [('reference','通用換框法：參照小圖'),('target','通用換框法：待測小圖')]:body+=f'<figure><figcaption>{title}</figcaption><img src="images/{n}-{side}.png"></figure>'
  body+=f'<p><a href="normal.html#case-{n}">返回本輪最終結果與完整圖片 →</a></p></article>'
 body+='''<h2>固定補查的具體規則</h2><p>沿用已有局部對齊與差異計算，找與候選相交的深色差異連通區，取其長邊為方形，四邊各加2像素。只接受背景對齊可靠、面積至少12像素、沒有碰搜尋邊界、取圖沒有超出原圖的結果。參照和待測從原本對齊圖的相同座標取圖；不塗掉背景、不手改某張座標、不用DINO分數挑框。</p><p>本輪保留完整47＋65範例及上輪明暗處理，整體與小區域各占一半，門檻仍為0。最終仍須參照判沒有、待測判有。</p><h2>尚未解決與下一步</h2><p>1.png、2.png：先研究只在差異物件內比較小區域，不把整塊板件背景平均進去。5.png：檢查參照的「像螺絲區域」與待測新增位置是否一致，避免旁邊原有圓環否決新增螺絲。兩項都尚未驗證，本輪不列為已改善；未刪任何正常範例。</p><h2>資料與驗證限制</h2><p>這59處反覆用來開發，限定條件也是在看過線材誤報後提出。尚未用新資料驗收。五處額外螺絲依助手目視預期評分，不冒充使用者人工標記；範例來源仍有無法完全排除同來源的限制。</p><p>只重算固定位置的候選小圖。沒有重跑全圖資差分、沒有改正式流程、模型、設定、範例或人工紀錄。報告涵蓋同批59處，不宣稱涵蓋全部原始照片、零候選照片或參照自比。</p>'''
 for file,title in [('restricted-rules.json','最終實驗規則'),('restricted-results.json','59處最終結果'),('results.json','未採用通用補查結果'),('restricted-summary.json','統計'),('neighbors.json','實際相似範例'),('preservation.json','原資料未變核對'),('validation.json','報告完整性核對')]:body+=f'<p><a href="{file}">{title}</a></p>'
 body+='<p><a href="../dino-contrast-pair-20261103/index.html">上一輪明暗處理報告</a></p>'
 write('attempt.html','未採用做法、後續方向與限制',body)
 missing=[];cards=[];links=0
 for name in ['index.html','screws.html','normal.html','attempt.html']:
  f=OUT/name;s=f.read_text(encoding='utf-8');cards+=re.findall(r'<article id="case-(\d+)"',s)
  for u in re.findall(r'(?:src|href)="([^"]+)"',s):
   if u=='validation.json':continue
   q=urlparse(u);p=Path(unquote(q.path).lstrip('/')) if q.scheme=='file' else OUT/q.path if q.path else f;links+=1
   if not p.is_file():missing.append(str(p))
   elif q.fragment and p.suffix=='.html' and f'id="{unquote(q.fragment)}"' not in p.read_text(encoding='utf-8'):missing.append(u)
 assert not missing,missing
 assert sorted(map(int,cards))==list(range(1,60))
 protected=read(OUT/'preservation-before.json');assert all(sha(Path(p))==v for p,v in protected.items())
 save(OUT/'validation.json',dict(case_cards=59,links_checked=links,missing=missing,input_images_verified=118,paired_rules_verified=59,protected_unchanged=True,summary=summary))
 print(json.dumps(dict(report=str(OUT/'index.html'),links=links,summary=summary),ensure_ascii=False))
if __name__=='__main__':main()
