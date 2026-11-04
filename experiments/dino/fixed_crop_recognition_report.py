"""Plain Chinese report for the same 17 cases, without running inference."""
import html,json,re,sys,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.fixed_crop_recognition_pilot import OUT,MODEL,PRIOR,read,save,sha
from dino_adapter import input_image
NAMES={'original_cls':'原本判斷','eight_views_cls':'範例補上不同朝向','patch_mean':'改比各小區域的平均特徵','eight_views_patch_mean':'不同朝向＋小區域特徵','equal_vote':'整體與小區域各占一半'}
FONT='C:/Windows/Fonts/msjh.ttc'
def word(z):return '有螺絲' if z['screw'] else '沒有螺絲'
def main():
 rows=read(OUT/'results.json');summary=read(OUT/'summary.json');plan=read(PRIOR/'plan.json')['cases'];m=read(MODEL/'manifest.json');meta=read(MODEL/'examples.json')
 assert len(rows)==17 and all(r['key']==p['key'] for r,p in zip(rows,plan))
 extra=read(OUT/'equal-vote-results.json');extra_summary=read(OUT/'equal-vote-summary.json')
 for r,e in zip(rows,extra):
  assert r['key']==e['key']
  for protocol,pair in e['protocols'].items():r['protocols'][protocol]['equal_vote']=pair
 for protocol,s in extra_summary.items():summary[protocol]['equal_vote']=s
 methods=list(NAMES);a=summary['all_47_65'];held=summary['exclude_known_overlap']
 winners=[k for k in methods[1:] if a[k]['screw_pairs_correct']==2 and not a[k]['normal_alerts']]
 selected=winners[0] if winners else min(methods[1:],key=lambda k:(-a[k]['screw_pairs_correct'],len(a[k]['normal_alerts'])))
 passed=bool(winners)
 conclusion=('保留原 47＋65 範例時，這批案例達到目標：兩顆都判出「參照沒有、待測有」，15 個正常案例沒有新增螺絲誤報。但移除已知重複範例後，圓頭案例又失敗，另有 1 個正常位置誤報，尚不能定案。' if passed else '本輪還沒達到目標：沒有一個改法同時認對兩顆螺絲，又讓 15 個正常案例都不誤報。')
 css='''body{margin:0;background:#f4f7f8;color:#173e4b;font:19px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1340px;margin:auto;padding:28px}h1{font-size:32px}h2{font-size:26px}a{color:#007e8a}nav{display:flex;gap:24px;flex-wrap:wrap}.answer{background:white;border-left:5px solid #00818c;padding:22px}table{width:100%;border-collapse:collapse;background:white}td,th{padding:13px;border:1px solid #d9e3e8;text-align:left}th{background:#e6eff2}article{background:white;border:1px solid #d9e3e8;border-radius:10px;margin:22px 0;padding:20px}.pair{display:flex;gap:22px;flex-wrap:wrap}figure{margin:0 0 16px}figure img{width:224px}summary{cursor:pointer;padding:12px}.note{font-size:16px}.bad{color:#b4282e}.good{color:#08715f}img.board{width:100%;height:auto}pre{white-space:pre-wrap;font-size:14px}'''
 nav='<nav><a href="index.html">本次結果</a><a href="normal.html">全部正常案例</a><a href="evidence.html">範例對照與限制</a></nav>'
 def write(name,title,body):
  (OUT/name).write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style><main>{nav}{body}</main></html>',encoding='utf-8')
 def table(protocol,keys=None):
  s=summary[protocol];body='<table><tr><th>做法</th><th>斜螺絲：參照／待測</th><th>圓頭：參照／待測</th><th>正常案例誤報</th></tr>'
  for k in (keys or methods):
   pairs=[r['protocols'][protocol][k] for r in rows[:2]]
   body+=f'<tr><td>{NAMES[k]}</td>'+''.join(f'<td>{word(p["reference"])}／{word(p["target"])}<br>{"符合目標" if p["keep"] else "未符合"}</td>' for p in pairs)+f'<td>{len(s[k]["normal_alerts"])}／15 個位置</td></tr>'
  return body+'</table>'
 def case(n):
  r=rows[n-1];z=plan[n-1];body=f'<article id="case-{n}"><h3>{n}. {html.escape(z["title"])} · {z["machine"]}／位置 {z["id"]}</h3><p class="note">{html.escape(z["name"])}</p><div class="pair">'
  for side,caption in [('reference','固定的參照小圖'),('target','固定的待測小圖')]:body+=f'<figure><figcaption>{caption}</figcaption><img src="images/{n}-{side}.png"></figure>'
  body+='</div><table><tr><th>做法</th><th>參照判斷</th><th>待測判斷</th><th>是否報新增螺絲</th></tr>'
  for k in methods:
   p=r['protocols']['all_47_65'][k];body+=f'<tr><td>{NAMES[k]}</td><td>{word(p["reference"])}</td><td>{word(p["target"])}</td><td>{"是" if p["keep"] else "否"}</td></tr>'
  body+='</table>'
  if n>2:body+=f'<p><a href="normal.html#machine-{z["machine"]}">返回此機種</a> · <a href="normal.html#category-{z["machine"]}-{z["category"]}">查看同類案例</a></p>'
  else:body+='<p>只有「參照沒有螺絲、待測有螺絲」才算本例成功。排除、兩張都判有、待確認都不算。</p>'
  src=Path(z['source']);body+=f'<details><summary>看完整照片與原候選位置</summary><img class="board" src="../{PRIOR.name}/images/{n}-pair.jpg"><p><a href="{(src/"reference.png").as_uri()}">完整參照圖</a> · <a href="{(src/"aligned.png").as_uri()}">完整待測圖</a></p></details></article>'
  return body
 body=f'<h1>圖片不換，改 DINO 的比較方式</h1><div class="answer"><b>{conclusion}</b><p>兩顆螺絲＋原有物件、線材、板件等 15 個正常對照，共 17 個位置。未使用偏移、新框或待確認代替成功。</p></div><h2>這次實際改了什麼？</h2><p><b>同一張小圖，讓 DINO 從兩個角度比較，最後各占一半：</b></p><ol><li><b>整體外觀：</b>與原範例及它的不同朝向比較。螺絲、正常範例都做相同處理。</li><li><b>小區域特徵：</b>改用 DINO 對圖內各小區域的描述取平均，再與原範例比較。</li></ol><p>兩邊的差距分數平均後，分別決定參照、待測有沒有螺絲。不是任一方法說有就算有，也沒有依案例挑選方法。這個各占一半的做法，是看到兩個單獨方法各能認對一顆後追加的開發實驗；比例固定一半，沒有搜尋最有利比例。</p><p>仍使用原 47＋65 張範例、原正式小圖，門檻固定 0；沒有把測試螺絲加入範例。不同朝向只是同一張的變化，同一張不會重複佔用三張比較名額。</p><h2>結果先看這張表</h2>'+table('all_47_65',['original_cls','equal_vote'])
 body+='<p>正常案例的「沒誤報」不代表每張小圖都認對。有些方法會把兩張都認成螺絲，最後因為雙圖規則才排除；逐例表中保留這個差別。</p>'+case(1)+case(2)
 body+='<h2>線材和板件有沒有一起測？</h2><p>有，沿用同一批 8 個線材，以及 7 個原有物件／板件對照，沒有更換案例。15 個正常位置沒有誤報；其中 14 個兩張都判非螺絲，1 個原有物件兩張都判螺絲，由雙圖規則排除。<a href="normal.html">查看全部 15 個正常位置 →</a></p><h2>為什麼還不能定案？</h2><p>其中 7 個正常案例原本就在正常範例庫。另做移除這 7 個範例的核對，保留 47 張螺絲＋58 張正常；只在實驗內做，正式庫不變。圓頭螺絲的參照又被判有螺絲，另有第 15 個正常案例誤報。這提醒我們，結果仍依賴範例組合，不能拿同批成功宣稱普遍有效。</p>'+table('exclude_known_overlap',['original_cls','equal_vote'])
 body+='<p>此外，斜螺絲在各占一半後只是略高於判斷界線，仍需新案例驗證穩定性。分數不是成功機率。</p><details><summary>展開全部測過的做法（包含失敗）</summary>'+table('all_47_65')+'<h3>移除已知重複範例</h3>'+table('exclude_known_overlap')+'</details>'
 body+='<h2>這輪能說明什麼？</h2><p>'+('固定原圖、原範例庫時，結合兩種 DINO 資訊確實能讓這兩顆各自達成雙圖判斷，但排除重複範例的核對未通過。下一步應補充不與測試照片重複的正常板件／線材，以及不同外觀的真螺絲範例，再做同樣核對；不能直接套用正式版。' if passed else '固定原圖後，這些比較方式仍不足以同時解決兩顆螺絲。不能用「保留」或降低門檻掩蓋分類失敗，也不能宣稱已經修好。')+'</p><p>模型檔、正式判斷、47＋65 範例與人工紀錄未更動，未重跑全圖資。所有結果是這批已知開發案例，非獨立測試。</p>'
 write('index.html','固定原取圖：DINO 辨識改善實驗',body)
 body='<h1>正常案例：全部 15 個位置</h1><p>沿用原先類型；正常來自良品資料或既有人工核對，類型不等於每個局部都已確認沒有固定螺絲。這裡檢查是否誤報為新增螺絲。</p>'
 for machine in ['MPT10','MPT11','MPT12','KPH33']:
  nums=[n for n,z in enumerate(plan,1) if n>2 and z['machine']==machine];body+=f'<section id="machine-{machine}"><h2>{machine} · {len(nums)} 個位置</h2>'
  for category in ['線材','板件邊界','元件外觀','U 形結構','待確認']:
   sub=[n for n in nums if plan[n-1]['category']==category];body+=f'<div id="category-{machine}-{category}"><h3>{category} · {len(sub)} 個位置</h3>'
   if sub:
    body+=case(sub[0])
    if len(sub)>1:body+=f'<details><summary>展開其餘 {len(sub)-1} 個同類位置</summary>'+''.join(case(n) for n in sub[1:])+'</details>'
   else:body+='<p>本批沒有選入，數量 0。</p>'
   body+='</div>'
  body+='</section>'
 body+='<script>function show(){let n=document.getElementById(decodeURIComponent(location.hash.slice(1)));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView()}show();addEventListener("hashchange",show)</script>'
 write('normal.html','同批正常線材與板件',body)
 body='<h1>目前 DINO 拿什麼範例比較？</h1><p>以下顯示固定原小圖與原本最相近的三張螺絲、三張正常範例。每張範例先經正式輸入處理後展示；不把肉眼相似當成模型必定相似。</p>'
 for n in [1,2]:
  canvas=Image.new('RGB',(1515,560),'#f4f7f8');d=ImageDraw.Draw(canvas);font=ImageFont.truetype(FONT,18)
  for row,side in enumerate(['reference','target']):
   y=10+row*275;p=rows[n-1]['protocols']['all_47_65']['original_cls'][side]
   images=[Image.open(OUT/'images'/f'{n}-{side}.png').convert('RGB')];names=[('參照' if side=='reference' else '待測')+'：'+word(p)]
   for group in ['screw','normal']:
    for j,ev in enumerate(p['evidence'][group]['neighbors'],1):
     im=Image.open(MODEL/'examples'/meta[ev['id']]['file']).convert('L');images.append(input_image(m,np.asarray(im,dtype=np.float32)/255));names.append(('螺絲範例 ' if group=='screw' else '正常範例 ')+str(j))
   for col,(im,name) in enumerate(zip(images,names)):
    x=10+col*215;d.text((x,y),name,font=font,fill='#173e4b');canvas.paste(im.resize((200,200)),(x,y+37))
  canvas.save(OUT/f'neighbors-{n}.png');body+=f'<h2>{"斜螺絲" if n==1 else "圓頭螺絲"}</h2><img class="board" src="neighbors-{n}.png">'
 body+='<p>斜螺絲在原本比較中選中的三張螺絲範例都是舊範例，沒有選到後加的現場螺絲照片。圓頭的參照圖也被配到螺絲範例。這是比較結果的證據，尚不能單憑它判定背景是唯一原因。</p>'
 diag=read(OUT/'field_only_diagnostic.json');rr=diag['results'];body+=f'<h2>另外檢查：只用 16 張現場螺絲範例有用嗎？</h2><p>這是看過範例對照後追加的診斷，不是預先指定的主要測試。仍用 65 張正常範例。兩顆成功 {sum(x["keep"] for x in rr[:2])}／2，正常誤報 {sum(x["keep"] for x in rr[2:])}／15；斜螺絲仍未通過。因此不能直接主張移除舊範例就能解決。</p>'
 body+='<h2>限制與追溯</h2><ul><li>只有兩顆新增螺絲，同一張照片；同批案例反覆開發，不是獨立準確率。</li><li>正常範例已知有 7 個測試案例重複，已另做排除核對；其他來源重複仍可能存在。</li><li>各占一半的做法是看到前幾種結果後追加，不能當成事先保留的獨立驗證。沒有用測試標籤擬合權重或修改門檻。</li><li>本輪使用原正式框，不是前輪重新定位框；兩輪數字不能直接當成同一取圖的版本提升。</li><li>小區域特徵取平均仍可能混入背景，這不是已經辨識出物件輪廓。</li><li>方向處理採四種直角轉向及鏡像，不會涵蓋所有角度。</li></ul><p><a href="rules.json">第一輪固定規則</a> · <a href="results.json">逐例結果與相近範例</a> · <a href="summary.json">第一輪統計</a> · <a href="equal-vote-rule.json">各占一半規則</a> · <a href="equal-vote-results.json">各占一半結果</a> · <a href="equal-vote-summary.json">各占一半統計</a> · <a href="field_only_diagnostic.json">現場範例診斷</a> · <a href="preservation.json">正式檔案未變核對</a> · <a href="validation.json">報告核對</a></p>'
 write('evidence.html','DINO 範例比較證據',body)
 canvas=Image.new('RGB',(1100,840),'#f4f7f8');d=ImageDraw.Draw(canvas)
 def txt(x,y,s,size=23,color='#173e4b'):d.text((x,y),s,font=ImageFont.truetype(FONT,size),fill=color)
 txt(22,14,'同一張小圖：改比較方式後，兩顆各自判對',29)
 txt(22,59,'本表沿用原 47＋65 範例；沒有移動取圖框。',22)
 for i,n in enumerate([1,2]):
  y=105+i*285;r=rows[n-1]
  txt(22,y,'斜螺絲' if n==1 else '圓頭螺絲',25)
  for col,side in enumerate(['reference','target']):
   x=22+col*235;txt(x,y+37,'參照圖' if side=='reference' else '待測圖',20)
   im=Image.open(OUT/'images'/f'{n}-{side}.png').convert('RGB').resize((200,200));canvas.paste(im,(x,y+70))
  before=r['protocols']['all_47_65']['original_cls'];after=r['protocols']['all_47_65']['equal_vote']
  txt(515,y+38,'原本判斷',23)
  txt(515,y+80,'參照：'+word(before['reference'])+'　待測：'+word(before['target']),21,'#a8292d')
  txt(515,y+140,'整體與小區域各占一半',23)
  txt(515,y+182,'參照：'+word(after['reference'])+'　待測：'+word(after['target']),21,'#08715f')
 txt(22,694,'同批 15 個正常位置：0 個新增螺絲誤報。',23)
 txt(22,739,'但移除已知重複範例後：只認對 1 顆，正常誤報 1 個。',23,'#a8292d')
 txt(22,781,'仍是開發實驗，尚未套用正式流程。',23)
 canvas.save(OUT/'summary.png')
 # Every source, production model and code protected by the experiment remains intact.
 before=read(OUT/'preservation-before.json');assert all(sha(Path(p))==v for p,v in before.items())
 missing=[];links=0;cards=0
 from urllib.parse import urlparse,unquote
 for f in [OUT/'index.html',OUT/'normal.html',OUT/'evidence.html']:
  s=f.read_text(encoding='utf-8');cards+=len(re.findall(r'<article id="case-',s))
  for link in re.findall(r'(?:src|href)="([^"]+)"',s):
   if link=='validation.json':continue
   parts=urlparse(link);path=Path(unquote(parts.path).lstrip('/')) if parts.scheme=='file' else (OUT/parts.path if parts.path else f)
   links+=1
   if not path.is_file():missing.append(str(path))
   elif parts.fragment and path.suffix=='.html':
    if f'id="{unquote(parts.fragment)}"' not in path.read_text(encoding='utf-8'):missing.append(link)
 assert cards==17 and not missing,(cards,missing)
 save(OUT/'validation.json',dict(case_cards=cards,links_checked=links,missing=missing,protected_unchanged=True,full_batch_rerun=False))
 save(OUT/'verdict.json',dict(passed_same_development_cases=passed,passing_methods=winners,conclusion=conclusion))
 print(json.dumps(dict(conclusion=conclusion,summary=a,report=str(OUT/'index.html')),ensure_ascii=False))
if __name__=='__main__':main()
