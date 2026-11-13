"""Complete report for alarm-only experiments; no inference or activation."""
import argparse,html,json,math,shutil
from pathlib import Path
from collections import Counter,defaultdict
from PIL import Image,ImageDraw
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote

ROOT=Path(__file__).resolve().parents[2]
TYPES={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def esc(v):return html.escape(str(v),quote=True)
STYLE='body{font:17px/1.65 system-ui;color:#183847;max-width:1200px;margin:auto;padding:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:8px}img{max-width:100%}article,section,details{border:1px solid #dde;padding:14px;margin:14px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}.warn{background:#fff2cf;padding:16px}summary{cursor:pointer}code{overflow-wrap:anywhere}'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);a=ap.parse_args();out=a.output.resolve();summary=read(out/'summary.json');assert summary['full_corpus_completed']
 acceptance=read(out/'acceptance.json') if (out/'acceptance.json').exists() else {}
 plan=read(out/'plan.json');rows=read(out/'rows.json');rowmap={r['key']:r for r in rows};report=out/'report';report.mkdir(exist_ok=True);(report/'images').mkdir(exist_ok=True)
 oldcases={c['key']:c for c in read(ROOT/'workspace/dino-4r-integrated-bank-20261106/final/cases.json')}
 nav='<nav><a href="index.html">完整結果</a> · <a href="comparison.html">附加：版本比較與限制</a></nav>'
 def page(name,title,body):(report/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+esc(title)+'</title><style>'+STYLE+'</style>'+nav+'<h1>'+esc(title)+'</h1>'+body,encoding='utf-8')
 cases=[];photo_cases={};items={i['key']:i for i in plan['items']}
 for number,item in enumerate(plan['items']):
  key=item['key'];result=read(out/'runs'/key/'result.json');cs=sorted(result['candidates']+result['filtered_candidates'],key=lambda c:c['id']);assert len(cs)==rowmap[key]['candidates'];folder=Path(item['folder'])
  with Image.open(folder/'reference.png') as f:ref=f.convert('RGB')
  with Image.open(folder/'aligned.png') as f:target=f.convert('RGB')
  for name,im in [('reference',ref),('target',target)]:
   small=im.copy();small.thumbnail((1400,1400));small.save(report/'images'/f'{key}-{name}.jpg',quality=85)
  photo_cases[key]=[]
  for c in cs:
   cid=f"{key}-{c['id']}";cat=oldcases.get(cid,{}).get('category','unknown');authority='沿用舊報告外觀分類；非本次人工確認' if cat!='unknown' else '尚無逐框類型標記'
   if key in ('OK-000001','OK-000009','OK-000015') and c['id'] in {'OK-000001':{8},'OK-000009':{143},'OK-000015':{11}}[key]:cat='wire';authority='助理目視分類；非新增人工標記'
   if key=='OK-000008' and c['id']==13:cat='component';authority='使用者已確認：固定螺絲（2026-11-13）'
   pred=c['classification'];keep=pred['filter_recommendation']=='keep';x,y,w,h=[int(c[k]) for k in ['x','y','w','h']];group=f"{round((x+w/2)/45)}-{round((y+h/2)/45)}";isref=item.get('is_reference',False)
   record=dict(key=cid,photo=key,id=c['id'],category=cat,authority=authority,machine=item['machine'],label=item['label'],keep=keep,group=('self-' if isref else '')+group,box=[x,y,w,h],reason=pred.get('decision_reason',''),is_reference=isref)
   cases.append(record);photo_cases[key].append(record)
   image=report/'images'/f'{cid}.jpg'
   if not image.exists():
    side=max(120,w+48,h+48);x0=max(0,x+w//2-side//2);y0=max(0,y+h//2-side//2);canvas=Image.new('RGB',(600,300),'white')
    for j,im in enumerate([ref,target]):
     crop=im.crop((x0,y0,x0+side,y0+side));d=ImageDraw.Draw(crop);d.rectangle((x-x0,y-y0,x+w-x0,y+h-y0),outline='red',width=1)
     if pred.get('local_object5r',{}).get('accepted'):
      xx,yy,ww,hh=pred['canonical_object']['box'];d.rectangle((xx-x0,yy-y0,xx+ww-x0,yy+hh-y0),outline='blue',width=1)
     canvas.paste(crop.resize((300,300)),(j*300,0))
    canvas.save(image,quality=78)
  if number%20==0:print('REPORT',number,len(plan['items']),flush=True)
 def catfile(c):return 'type-'+c['machine']+'-'+c['category']+'.html'
 def card(c):
  state='保留警報' if c['keep'] else '排除';name=Path(items[c['photo']]['path']).name
  return '<article id="case-'+c['key']+'"><h3>'+esc(name)+' #'+str(c['id'])+'：'+state+'</h3><p>分類：'+TYPES[c['category']]+'（'+esc(c['authority'])+'） · <a href="machine-'+c['machine']+'.html">返回此機種</a> · <a href="'+catfile(c)+'#group-'+c['group']+'">查看同類案例</a> · <a href="photo-'+c['photo']+'.html#case-'+c['key']+'">查看照片</a></p><p>'+esc(c['reason'])+'</p><img loading="lazy" src="images/'+c['key']+'.jpg"><p>左：參照；右：待測。紅框為候選範圍，藍框為本次自動找出的局部物件。此圖供位置核對，並非 DINO 的實際輸入大小；框數不是螺絲顆數。</p></article>'
 def photo_table(selected):
  body='<table><tr><th>照片</th><th>標籤</th><th>保留／排除候選</th><th>照片結果</th></tr>'
  for item in selected:
   r=rowmap[item['key']];verdict='參照自比' if item.get('is_reference') else ('誤報' if r['kept'] else '無警報') if item['label']=='OK' else ('有警報；位置答案另核對' if r['kept'] else '未檢出掉落螺絲')
   body+='<tr><td><a href="photo-'+item['key']+'.html">'+esc(Path(item['path']).name)+'</a></td><td>'+item['label']+'</td><td>'+str(r['kept'])+'／'+str(r['candidates']-r['kept'])+'</td><td>'+verdict+'</td></tr>'
  return body+'</table>'
 for key,item in items.items():
  cc=photo_cases[key];r=rowmap[key];machine=item['machine'];cats=Counter(c['category'] for c in cc)
  body='<p><a href="machine-'+machine+'.html">返回此機種</a> · '+('、'.join('<a href="type-'+machine+'-'+k+'.html">查看同類案例：'+TYPES[k]+' '+str(v)+'</a>' for k,v in cats.items()) or '零候選；無候選分類')+'</p><p>保留 '+str(r['kept'])+' 框，排除 '+str(r['candidates']-r['kept'])+' 框。'+('參照圖自比，獨立列出。' if item.get('is_reference') else '')+'</p><div class="pair"><div>參照<img src="images/'+key+'-reference.jpg"></div><div>待測<img src="images/'+key+'-target.jpg"></div></div><p><a href="../runs/'+key+'/result.json">全部判斷資料</a></p><h2>保留警報</h2>'+(''.join(card(c) for c in cc if c['keep']) or '<p>0 框</p>')+'<details><summary>全部排除候選：'+str(r['candidates']-r['kept'])+' 框</summary>'+''.join(card(c) for c in cc if not c['keep'])+'</details>'
  page('photo-'+key+'.html',Path(item['path']).name,body)
 machines=sorted(set(i['machine'] for i in items.values())|{'MPT10','MPT12','KPH33'})
 for machine in machines:
  subset=[c for c in cases if c['machine']==machine];mi=[i for i in items.values() if i['machine']==machine];body='<p>機種 → 類型 → 相近位置。外觀分類不等於已確認誤報。</p>'
  for cat,title in TYPES.items():
   cc=[c for c in subset if c['category']==cat];body+='<p><a href="type-'+machine+'-'+cat+'.html">'+title+'：'+str(len(cc))+' 框</a></p>';groups=defaultdict(list)
   for c in cc:groups[c['group']].append(c)
   gallery='<p><a href="machine-'+machine+'.html">返回此機種</a>；相近位置僅方便瀏覽，不保證同一物件。</p>'
   for g,members in groups.items():
    gallery+='<section id="group-'+g+'"><h2>相近位置 '+g+'：'+str(len(members))+' 框</h2>'+card(members[0])
    if len(members)>1:gallery+='<details><summary>展開全部同類照片／其餘 '+str(len(members)-1)+' 框</summary>'+''.join(card(c) for c in members[1:])+'</details>'
    gallery+='</section>'
   page('type-'+machine+'-'+cat+'.html',machine+'／'+title,gallery if cc else gallery+'<p>0 案例</p>')
  body+='<h2>全部待測照片</h2>'+photo_table([i for i in mi if not i.get('is_reference')])+'<h2>參照圖自比</h2>'+photo_table([i for i in mi if i.get('is_reference')]);page('machine-'+machine+'.html',machine,body)
 state='隔離 5r 局部複核測試版已就緒。' if acceptance.get('status')=='passed' else '隔離實驗，驗證尚未完成。'
 index='<p class="warn">'+state+'這是既有完整結果的警報複核：原 100 張使用既有驗收基準，本次 KPH33 61 張使用目前批次基準；不是重新產生候選或盲測。舊版已排除的候選原樣保留。</p><p>共 '+str(len(items))+' 張、'+str(len(cases))+' 個候選。NG 無警報按照片計為未檢出；保留候選數不等於螺絲顆數。</p>'
 for machine in machines:
  mi=[i for i in items.values() if i['machine']==machine and not i.get('is_reference')];ok=[i for i in mi if i['label']=='OK'];ng=[i for i in mi if i['label']=='NG'];false=sum(rowmap[i['key']]['kept']>0 for i in ok);miss=sum(rowmap[i['key']]['kept']==0 for i in ng)
  index+='<section><h2><a href="machine-'+machine+'.html">'+machine+'</a></h2><p>OK 誤報 '+str(false)+'／'+str(len(ok))+' 張；NG 未檢出 '+str(miss)+'／'+str(len(ng))+' 張。</p>'
  if machine=='MPT10':index+='<p>有位置答案：保留命中 '+str(sum(len(r['answer_hits']) for r in rows if r['corpus']=='original100'))+'／101 處。這是既有答案匹配口徑。</p>'
  if machine=='KPH33':index+='<p>NG 缺位置答案，有警報不保證命中掉落螺絲。訓練來源 4 張也收錄；其餘 43 張 OK 與新增範例來源分開，但已知問題參與開發，不能宣稱盲測。</p>'
  index+='<h3>良品完整結果</h3>'+photo_table(ok)+'<h3>不良品完整結果</h3>'+photo_table(ng)+'</section>'
 index+='<h2>參照圖自比</h2>'+photo_table([i for i in items.values() if i.get('is_reference')]);page('index.html','5r 局部複核：全圖資完整結果',index)
 comparison='<p>第二張 #13 已由使用者確認為固定螺絲，作螺絲正例；固定螺絲兩圖都像螺絲時排除警報，不把它標成非螺絲。</p><p>只增加線材反例曾誤刪 5 個既有命中候選，該方案已淘汰。加入影像自動定位的局部物件複核後，94 個保護／問題候選檢查通過；全圖資警報複核結果見首頁。</p><p>新增範例主複核庫為 55 螺絲＋96 正常；可見局部庫為 50 螺絲＋83 正常。原有模型權重、原 47＋65 範例、既有基準結果及人工紀錄保持原樣。</p><p>完整 161 張採既有候選的警報複核，不是 161 張全流程重跑。驗證完成情況見下方紀錄。第五個 OK 警報須依本次結果照實列出，不因報表目的刪除。</p><table><tr><th>照片</th><th>原警報</th><th>本次警報</th><th>改為排除的候選</th></tr>'
 for r in rows:
  comparison+='<tr><td><a href="photo-'+r['key']+'.html">'+r['key']+'</a></td><td>'+str(r['baseline_kept'])+'</td><td>'+str(r['kept'])+'</td><td>'+esc(r['changed_candidates'])+'</td></tr>'
 comparison+='</table>'
 if acceptance:
  comparison+='<p>驗證狀態：'+esc(acceptance['status'])+'。四張原圖排除警報，原 79 處命中保留。</p><p>已知限制：第五張 OK 仍有警報；第一張縮至 90% 時仍誤報。候選位移測試仍有原流程的物件切換與無對應物件情況，未列為新版通過。</p><p><a href="../acceptance.json">驗證範圍與全部限制</a></p>'
 examples=out.parent/'run3/examples'
 if (examples/'manifest.json').exists():
  comparison+='<h2>新增的局部正反例</h2><p>來自另外 4 張照片，未使用這四張問題原圖本身入庫。線材由助理目視核對；固定螺絲類型由使用者確認，同位置來源裁圖另行核對。以下為標準方向的輸入圖。</p>'
  for example in read(examples/'manifest.json'):
   source=out.parent/'run3'/example['image'];name='training-'+source.name;shutil.copy2(source,report/'images'/name)
   label='螺絲正例：固定螺絲局部' if example['label']=='screw' else '非螺絲反例：線材局部'
   comparison+='<figure><figcaption>'+label+'；來源照片 '+esc(example['source'])+'</figcaption><img loading="lazy" src="images/'+name+'"></figure>'
 comparison+='<p><a href="../plan.json">完整設定與雜湊</a> · <a href="../summary.json">執行範圍</a> · <a href="../rows.json">全部逐張統計</a></p>';page('comparison.html','附加：版本比較與限制',comparison)
 save(out/'report-index.json',cases)
 class Links(HTMLParser):
  def __init__(self):super().__init__();self.ids=set();self.links=[]
  def handle_starttag(self,tag,attrs):
   a=dict(attrs)
   if 'id' in a:
    if a['id'] in self.ids:raise ValueError('Duplicate anchor '+a['id'])
    self.ids.add(a['id'])
   for k in ('src','href'):
    if k in a:self.links.append(a[k])
 pages={}
 for path in report.glob('*.html'):
  parser=Links();parser.feed(path.read_text(encoding='utf-8'));pages[path.resolve()]=parser
 count=0
 for path,p in pages.items():
  for link in p.links:
   u=urlsplit(link);assert not u.scheme and not u.netloc;dest=(path.parent/unquote(u.path)).resolve() if u.path else path
   assert dest.is_relative_to(out) and dest.is_file(),link
   if u.fragment:assert unquote(u.fragment) in pages[dest].ids,link
   count+=1
 assert len(list(report.glob('photo-*.html')))==len(items)
 assert sum(sum(k.startswith('case-') for k in v.ids) for k,v in pages.items() if k.name.startswith('photo-'))==len(cases)
 assert len(cases)==summary['candidates']
 save(out/('report-publication-verification.json' if acceptance else 'report-verification.json'),dict(status='passed',photos=len(items),candidates=len(cases),html_pages=len(pages),references_checked=count,all_image_and_anchor_targets_exist=True))
 print('VERIFIED',len(items),len(cases),count,flush=True)

if __name__=='__main__':main()
