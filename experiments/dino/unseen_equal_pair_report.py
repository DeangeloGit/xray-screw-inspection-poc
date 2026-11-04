"""Complete selected-case report with plain-language paired-image evidence."""
import sys,json,html,re,math
from pathlib import Path
from collections import Counter,defaultdict
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.unseen_pair_prepare import OUT,read,save
from experiments.dino.fixed_crop_recognition_pilot import sha
from experiments.dino.paired_review_clear_home import build_home
TYPES={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}
FONT='C:/Windows/Fonts/msjh.ttc'
def font(n):return ImageFont.truetype(FONT,n)
def word(value):return '有螺絲' if value['screw'] else '沒有螺絲'
def main():
 plan=read(OUT/'plan.json');cases=plan['cases'];rows=read(OUT/'results.json');summary=read(OUT/'summary.json')
 assert len(cases)==len(rows)==57 and all(c['key']==r['key'] for c,r in zip(cases,rows))
 assert not summary['all']['exact_bank_input_matches']
 (OUT/'photos').mkdir(exist_ok=True)
 # Fixed position grouping; no dependence on outcomes.
 groups=defaultdict(list);group_for={}
 for i,(z,r) in enumerate(zip(cases,rows),1):
  c=z['c'];cx,cy=c['x']+c['w']/2,c['y']+c['h']/2
  group=f'{z["machine"]}-{z["category"]}-{int(cx//80)}-{int(cy//80)}';groups[group].append(i);group_for[i]=group
  side=max(100,c['w']+48,c['h']+48);canvas=Image.new('RGB',(900,490),'#f4f7f8');d=ImageDraw.Draw(canvas)
  for col,(s,f) in enumerate([('reference','reference.png'),('target','aligned.png')]):
   im=Image.open(Path(z['source'])/f).convert('RGB');x0=max(0,min(im.width-side,round(cx-side/2)));y0=max(0,min(im.height-side,round(cy-side/2)))
   crop=im.crop((x0,y0,x0+side,y0+side)).resize((430,430));draw=ImageDraw.Draw(crop);k=430/side
   draw.rectangle([(c['x']-x0)*k,(c['y']-y0)*k,(c['x']+c['w']-x0)*k,(c['y']+c['h']-y0)*k],outline='#df2944',width=2)
   d.text((10+col*450,7),'參照圖：同位置' if col==0 else '待測圖：同位置',font=font(24),fill='#173e4b');canvas.paste(crop,(10+col*450,48))
  canvas.save(OUT/'images'/f'{i}-pair.jpg',quality=94)
 css='''body{margin:0;background:#f4f7f8;color:#173e4b;font:19px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1260px;margin:auto;padding:28px}h1{font-size:32px}h2{font-size:27px}a{color:#007e8a}nav{display:flex;gap:24px;flex-wrap:wrap}.answer{background:white;padding:22px;border-left:5px solid #007f89}.warn{border-left-color:#b82b30}table{width:100%;border-collapse:collapse;background:white}td,th{padding:13px;border:1px solid #d4dfe5;text-align:left}th{background:#e6eff2}article{background:white;padding:22px;margin:22px 0;border:1px solid #d4dfe5;border-radius:10px}img.pair{width:100%;max-width:900px;height:auto}figure{display:inline-block;margin:8px 20px 8px 0}figure img{width:224px}.note{font-size:16px;overflow-wrap:anywhere}summary{cursor:pointer;padding:15px}.bad{color:#b62c31}.good{color:#08715e}pre{white-space:pre-wrap;font-size:14px}'''
 nav='<nav><a href="index.html">兩組結果總覽</a><a href="index.html#original-problems">原本沒判對的兩顆</a><a href="additional.html">額外驗證案例</a><a href="screws.html">額外螺絲對照</a><a href="normal.html">額外正常案例</a><a href="sources.html">來源核對</a></nav>'
 def write(name,title,body,depth=False):
  navigation=nav.replace('href="','href="../') if depth else nav
  (OUT/name).write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style><main>{navigation}{body}</main></html>',encoding='utf-8')
 def mainpage(n):return 'normal.html' if rows[n-1]['group']=='normal' else 'screws.html'
 def link(n):return f'{mainpage(n)}#case-{n}'
 def method_table(n):
  r=rows[n-1];b='<table><tr><th>方法</th><th>參照圖判斷</th><th>待測圖判斷</th><th>報成新增螺絲？</th></tr>'
  for k,name in [('original','原本 DINO'),('equal','整體與小區域各占一半')]:
   b+=f'<tr><td>{name}</td><td>{word(r["pair"]["reference"][k])}</td><td>{word(r["pair"]["target"][k])}</td><td>{"是" if r["keep"][k] else "否"}</td></tr>'
  return b+'</table>'
 def card(n):
  z=cases[n-1];r=rows[n-1];page=mainpage(n);basis=z['label_basis'];g=group_for[n]
  label={'confirmed_screw':'已有螺絲標記','suspected_screw':'助手目視疑似新增螺絲，尚非人工確認','normal':'良品來源'}[r['group']]
  if r['group']=='confirmed_screw':finding='符合「參照沒有、待測有」；原本方法也判對。' if r['keep']['equal'] else '未符合「參照沒有、待測有」。'
  elif r['group']=='suspected_screw':finding='判錯：依本輪對照圖核對，應報出新增螺絲，但沒有報出。核對者為助手，原人工紀錄不變。' if not r['keep']['equal'] else '依本輪看圖預期判對：參照沒有、待測有。核對者為助手，原人工紀錄不變。'
  else:finding='新增誤報：線材被判成螺絲。' if r['keep']['equal'] and not r['keep']['original'] else '本例沒有新增螺絲誤報。'
  body=f'<article id="case-{n}"><h3>{n}. {html.escape(z["name"])} · 位置 {z["id"]}</h3><p><b>{label}。{finding}</b></p><p class="note">分類：{TYPES[z["category"]]}；{html.escape(basis)}</p><img class="pair" loading="lazy" src="images/{n}-pair.jpg"><p class="note">紅框沿用原差分候選；沒有重新定位。下方是 DINO 實際收到的原正式小圖。</p>'
  for side,caption in [('reference','DINO 收到的參照小圖'),('target','DINO 收到的待測小圖')]:body+=f'<figure><figcaption>{caption}</figcaption><img loading="lazy" src="images/{n}-{side}.png"></figure>'
  body+=method_table(n)
  body+=f'<p><a href="photos/{z["sha"]}.html">查看完整照片與本輪位置</a> · <a href="{page}#machine-{z["machine"]}">返回此機種</a> · <a href="{page}#group-{g}">查看同類案例</a></p>'
  body+='<details><summary>查看分數與輸入核對</summary><p>分數是外觀相似度差，不是正確率。整體與小區域固定各占一半，門檻仍為 0。</p><pre>'+html.escape(json.dumps(dict(pair=r['pair'],input_audit=r['audit']),ensure_ascii=False,indent=2))+'</pre></details></article>'
  return body
 normal=summary['normal'];confirmed=summary['confirmed_screw'];sus=summary['suspected_screw']
 body=f'<h1>換一批現有案例，這個改法有進步嗎？</h1><div class="answer warn"><b>這批沒有看到改善，還增加 1 個線材誤報。</b><p>2 個已有螺絲標記的位置，新舊方法都判對；5 個目視疑似新增螺絲位置，新舊方法都未判出。50 個正常位置，誤報從 0 增加到 1。</p><p>原 47＋65 張範例全部保留，固定沿用各占一半的做法；沒有重挑比例、改門檻或重裁圖，未套用正式流程。</p></div><h2>本次完整結果</h2><table><tr><th>核對組別</th><th>本次位置數</th><th>原本 DINO</th><th>各占一半</th></tr><tr><td>已有螺絲標記</td><td>2</td><td>2 個符合參照無、待測有</td><td>2 個符合，沒有增加</td></tr><tr><td>助手目視疑似新增螺絲</td><td>5</td><td>0 個判出</td><td>0 個判出</td></tr><tr><td>正常線材、板件與其他結構</td><td>50</td><td>0 個誤報</td><td>1 個誤報</td></tr></table><p>共 57 個位置、41 張來源照片。這是依你要求挑選的額外案例驗證，並非全圖資重跑；所有選入案例都列出，沒有只呈現成功案例。</p>'
 body+='<h2>先看新增的線材誤報</h2><p>KPH33 的線束位置改變。原本沒有報螺絲，新方法卻判成「參照沒有、待測有」。</p><img class="pair" src="images/8-pair.jpg">'+method_table(8)+f'<p><a href="{link(8)}">查看這個誤報的實際 AI 小圖 →</a></p>'
 body+='<h2>螺絲有沒有真正判對？</h2><p>有，兩個已有標記的位置都明確符合「參照圖沒螺絲、待測圖有螺絲」，沒有使用待確認代替。但原本方法也判對，所以這兩個不能算成新增改善。</p><div class="pair">'
 for n in [1,2]:body+=f'<p><a href="{link(n)}">{html.escape(cases[n-1]["name"])}／位置 {cases[n-1]["id"]} →</a></p><img class="pair" src="images/{n}-pair.jpg">'
 body+='</div><p><a href="screws.html">看全部 7 個螺絲／疑似螺絲位置，包括失敗例 →</a></p><h2>正常案例依機種看</h2><table><tr><th>機種</th><th>照片／位置</th><th>原本誤報</th><th>新法誤報</th><th>入口</th></tr>'
 for machine in ['MPT10','MPT12','KPH33','MPT11']:
  sub=[(n,z,r) for n,(z,r) in enumerate(zip(cases,rows),1) if r['group']=='normal' and z['machine']==machine]
  body+=f'<tr><td>{machine}</td><td>{len({z["sha"] for _,z,_ in sub})}／{len(sub)}</td><td>{sum(r["keep"]["original"] for _,_,r in sub)}</td><td>{sum(r["keep"]["equal"] for _,_,r in sub)}</td><td><a href="normal.html#machine-{machine}">查看分類</a></td></tr>'
 body+='</table><h2>這些圖片確定沒放進範例庫嗎？</h2><p>已排除已知範例來源照片、上一輪 17 例的來源照片，以及目視可疑重複的螺絲。57 個位置的待測與參照輸入，均沒有與範例的標準輸入完全相同。</p><p><b>但有一個來源限制：</b>16 張現場螺絲範例來自拼圖，沒有原始照片檔名；舊 31 張也只追溯到範例頁面裁圖，未完整對應原始拍攝檔名。不同裁切或縮放會改變檔案比對結果，所以只能說「目前核對未見相同範例」，不能保證完全沒有同來源圖片。<a href="sources.html">查看篩選與排除紀錄 →</a></p><h2>本輪結論</h2><p>保留完整範例庫後，這個方法沒有在這批額外案例證明更好，因此繼續保留為實驗，不更新正式流程。下一步應針對實際未判出的螺絲及這個線材誤報找原因，不能因上一輪兩顆成功就直接採用。</p>'
 body='<h1>額外驗證案例：不包含原本問題的兩顆</h1><div class="answer"><p>本頁的兩個已標記螺絲，明確指 <b>MPT11／5.png 位置 2、9.png 位置 1</b>。不是原本問題的 MPT12 斜螺絲 #94、圓頭 #34。</p><p><a href="index.html#original-problems">查看原本沒判對的兩顆及改善結果 →</a></p></div>'+body
 write('additional.html','額外驗證案例：另找的57個位置',body)
 build_home(OUT,write,cases,rows,method_table)
 for group,page,title in [('normal','normal.html','正常案例：線材、板件與其他結構'),('screw','screws.html','螺絲：兩個既有標記、五個目視疑似')]:
  body=f'<h1>{title}</h1><p>依機種 → 類型 → 相近位置。先看代表圖，可展開同組全部案例。分類由助手目視核對，與使用者人工確認分開。</p>'
  if group=='screw':body+='<div class="answer"><b>這頁全是額外驗證案例，不包含原本問題的兩顆。</b><p>兩個已有螺絲標記是 MPT11／5.png 位置 2、9.png 位置 1。<a href="index.html#original-problems">原本沒判對的斜螺絲與圓頭螺絲在此 →</a></p></div><p>其餘五個沿用助手目視疑似，沒有升格為已確認標籤；因此類型列於待確認，但 AI 結果仍明確分有／沒有螺絲。</p>'
  for machine in ['MPT10','MPT12','KPH33','MPT11']:
   nums=[n for n,r in enumerate(rows,1) if r['machine']==machine and ((r['group']=='normal')==(group=='normal'))]
   body+=f'<section id="machine-{machine}"><h2>{machine} · {len(nums)} 個位置</h2>'
   for cat,label in TYPES.items():
    sub=[n for n in nums if rows[n-1]['category']==cat];body+=f'<div id="category-{machine}-{cat}"><h3>{label} · {len(sub)} 個位置</h3>'
    if not sub:body+='<p>本輪未選入，數量 0。</p>'
    else:
     for g in dict.fromkeys(group_for[n] for n in sub):
      same=[n for n in sub if group_for[n]==g];body+=f'<div id="group-{g}"><h4>相近位置 · {len(same)} 個案例</h4>'+card(same[0])
      if len(same)>1:body+=f'<details><summary>展開其餘 {len(same)-1} 個同位置案例</summary>'+''.join(card(n) for n in same[1:])+'</details>'
      body+='</div>'
    body+='</div>'
   body+='</section>'
  body+='<script>function show(){const n=document.getElementById(decodeURIComponent(location.hash.slice(1)));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView()}show();addEventListener("hashchange",show)</script>'
  write(page,title,body)
 # Full source photographs and every selected candidate on them, without rerunning detection.
 photos=defaultdict(list)
 for n,z in enumerate(cases,1):photos[z['sha']].append(n)
 for key,nums in photos.items():
  z=cases[nums[0]-1];canvas=Image.new('RGB',(1040,570),'#f4f7f8');d=ImageDraw.Draw(canvas)
  for col,f in enumerate(['reference.png','aligned.png']):
   im=Image.open(Path(z['source'])/f).convert('RGB');original=im.size;im.thumbnail((500,500));k=im.width/original[0];draw=ImageDraw.Draw(im)
   for n in nums:
    c=cases[n-1]['c'];draw.rectangle([c['x']*k,c['y']*k,(c['x']+c['w'])*k,(c['y']+c['h'])*k],outline='#f02a42',width=2);draw.text((c['x']*k,c['y']*k-15),str(n),font=font(14),fill='#e02032')
   canvas.paste(im,(10+col*520,45));d.text((10+col*520,5),'完整參照圖' if col==0 else '完整待測圖',font=font(23),fill='#173e4b')
  canvas.save(OUT/'images'/f'photo-{key}.jpg',quality=94)
  body=f'<h1>{html.escape(z["name"])}</h1><p>紅框只標本輪選入位置，數字為本報告案例編號；未重跑全圖檢測。</p><img class="pair" src="../images/photo-{key}.jpg"><ul>'
  for n in nums:body+=f'<li>分類：{TYPES[cases[n-1]["category"]]} · <a href="../{link(n)}">案例 {n}／位置 {cases[n-1]["id"]}</a> · <a href="../{mainpage(n)}#group-{group_for[n]}">查看同類案例</a></li>'
  body+=f'</ul><p><a href="../{mainpage(nums[0])}#machine-{z["machine"]}">返回此機種</a> · <a href="{(Path(z["source"])/"reference.png").as_uri()}">參照原圖</a> · <a href="{(Path(z["source"])/"aligned.png").as_uri()}">待測原圖</a></p>'
  write(f'photos/{key}.html',z['name'],body,True)
 body='<h1>如何挑出未見相同範例的案例？</h1><ol><li>保留完整 47 張螺絲＋65 張正常範例，不刪任何範例。</li><li>正常組排除 65 張正常範例對應的 42 張來源照片，也排除上一輪測試案例的已知來源。</li><li>全部符合條件的 50 個正常候選都納入，沒有根據新模型分數挑案例。</li><li>從既有螺絲標記及目視疑似清單取 24 個位置，先看圖比對 47 張螺絲範例，保守排除 17 個疑似重複或難以排除同來源者，留下 7 個。</li><li>在新方法推論前固定選入清單。核對實際輸入像素：沒有與範例或其直角轉向／鏡像完全相同的輸入。</li></ol><div class="answer warn"><b>這不是完整獨立測試的保證。</b><p>16 張現場螺絲範例缺原始檔名和座標；舊 31 張僅有範例頁面及裁圖座標。裁切、縮放、亮度變化會使相同來源也有不同像素。因此本頁稱「未見相同範例」，不稱已證明來源完全獨立。這批照片也曾出現在舊報告中，只是沒有用來調這次各占一半的方法。</p></div><h2>保留的螺絲／疑似位置</h2><table><tr><th>來源</th><th>既有依據</th><th>本輪比對</th></tr>'
 for n in range(1,8):
  z=cases[n-1];body+=f'<tr><td><a href="{link(n)}">{html.escape(z["name"])}／{z["id"]}</a></td><td>{html.escape(z["label_basis"])}</td><td>{html.escape(z["visual_provenance"])}</td></tr>'
 body+='</table><h2>未納入的 17 個位置</h2><p>「相近範例編號」只是保守排除時的目視線索，不表示已完成原始照片來源鑑定；沒有明確編號者表示無法可靠排除同來源或重疊影響。</p><table><tr><th>篩選圖編號</th><th>候選代碼</th><th>相近範例編號</th></tr>'
 for z in plan['excluded_screw_review']:body+=f'<tr><td>{z["number"]}</td><td class="note">{z["key"]}</td><td>{z["related_bank_number"] or "未確定"}</td></tr>'
 body+='</table><details><summary>展開全部螺絲篩選圖與原範例，核對有沒有挑掉失敗例</summary><p>篩選圖編號與本報告案例編號不同。此清單在新方法推論前固定。</p>'
 for f in ['screw-review-1.jpg','screw-review-2.jpg','screw-review-3.jpg','bank-screw-1.jpg','bank-screw-2.jpg']:body+=f'<img class="pair" loading="lazy" src="{f}">'
 body+='</details><h2>實驗規則與資料核對</h2><p>沿用前輪固定的整體與小區域分數各一半，兩張獨立判有／沒有，僅「待測有、參照沒有」報新增螺絲。原正式裁圖、模型權重與 47＋65 範例不變。前輪 34 張小圖的計算結果已核對一致。</p><p><a href="plan.json">固定選例與規則</a> · <a href="results.json">全部 57 個結果</a> · <a href="summary.json">統計</a> · <a href="preservation.json">正式模型與資料未變</a> · <a href="validation.json">圖片與連結核對</a></p>'
 write('sources.html','案例來源與重複核對',body)
 before=read(OUT/'preservation-before.json');assert all(sha(Path(p))==v for p,v in before.items())
 from urllib.parse import urlparse,unquote
 missing=[];checked=0;cards=[]
 for f in [OUT/'index.html',OUT/'additional.html',OUT/'screws.html',OUT/'normal.html',OUT/'sources.html',*list((OUT/'photos').glob('*.html'))]:
  s=f.read_text(encoding='utf-8');cards+=re.findall(r'<article id="case-(\d+)"',s)
  for url in re.findall(r'(?:src|href)="([^"]+)"',s):
   if url=='validation.json':continue
   parts=urlparse(url);path=Path(unquote(parts.path).lstrip('/')) if parts.scheme=='file' else (f.parent/parts.path if parts.path else f)
   checked+=1
   if not path.is_file():missing.append(str(path))
   elif parts.fragment and path.suffix=='.html' and f'id="{unquote(parts.fragment)}"' not in path.read_text(encoding='utf-8'):missing.append(url)
 assert not missing,missing
 assert sorted(map(int,cards))==list(range(1,58))
 assert len(photos)==41
 home=(OUT/'index.html').read_text(encoding='utf-8')
 assert len(re.findall(r'<article id="original-',home))==2
 assert 'original-94' in home and 'original-34' in home
 assert 'additional-screw-1' in home and 'additional-screw-2' in home and 'new-wire-alarm' in home
 save(OUT/'validation.json',dict(case_cards=len(cards),original_problem_cards=2,additional_cases=57,total_distinct_cases=59,photo_pages=len(photos),links_images_checked=checked,missing=missing,source_files_unchanged=True,model_examples=112,
  confirmed_screw_positions=2,suspected_screw_positions=5,normal_positions=50,selection_scope='All57 selected cases, NOT full dataset evaluation'))
 print(json.dumps(dict(report=str(OUT/'index.html'),summary=summary,links=checked),ensure_ascii=False))
if __name__=='__main__':main()
