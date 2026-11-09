"""Append evidence-only miss ledger to existing full report; no inference."""
import json,hashlib,re,html
from pathlib import Path
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import unquote,urlsplit
P=Path('workspace/kph33-4r-eval-20261109').resolve()
def read(n):return json.loads((P/n).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def esc(v):return html.escape(str(v))
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
plan=read('plan.json');protected={p:sha(p) for p in plan['hashes']};assert protected==plan['hashes']
original={n:sha(P/n) for n in ['summary.json','cases.json','rows.json','answers.json','answer-matches.json','position-consistency.json']}
for p,h in read('run-complete.json').get('result_sha256',{}).items():assert sha(P/p)==h
cases={(c['photo'],c['id']):c for c in read('cases.json')};audit=read('audit/4r-diagnostic.json');cg={r['photo']:r for r in read('audit/miss46-C-geometry.json')['photos']};dg={r['photo']:r for r in read('audit/candidate-diagnostics-summary.json')['D_rows']}
records=[]
def f(v):return '未記錄' if v is None else f'{v:+.5f}'
def analyze(c):
 s=c['classification'];pair=s.get('paired_evidence',{});t=pair.get('target',{});r=pair.get('reference',{});out=[]
 tm=t.get('screw_margin');rm=r.get('screw_margin')
 out.append(f"待測螺絲−正常分數 {f(tm)}，參照 {f(rm)}；差值是相似度差，不是機率。")
 if tm is not None and tm<0:out.append('待測正常範例的平均相似度高於螺絲範例，主判落在正常側。')
 if tm is not None and rm is not None and tm>=0 and rm>=0:out.append('新增部位與既有圓形結構都落在螺絲側；雙圖規則要求參照低於0，故排除。')
 for side,obj in [('待測',t),('參照',r)]:
  for view,e in obj.get('dino_evidence',{}).items():
   a,b=e['screw'],e['normal'];out.append(f"{side}/{view}：螺絲 {a['similarity']:.5f}（{','.join(a['neighbors'])}）；正常 {b['similarity']:.5f}（{','.join(b['neighbors'])}）。")
 ex=s.get('r4_experiment',{});views=ex.get('views',{})
 if views:
  g=ex.get('geometry',[]);share=g[0].get('near_share') if g and g[0] else None
  out.append('物件鄰近占比 '+f(share)+'，要求 ≥0.15'+('，未通過。' if share is None or share<.15 else '，通過。'))
  for pad,v in views.items():
   vals={side:sum(v[side][k] for k in ('whole','local','focused'))/3 for side in ('target','reference')}
   failed=[]
   if vals['target']<.04:failed.append('待測不足0.04')
   if vals['reference']>=0:failed.append('參照未低於0')
   out.append(f"補抓外擴{pad}：待測三視角平均 {f(vals['target'])}、參照 {f(vals['reference'])}；"+('、'.join(failed) or '分數條件通過')+'。')
 if 'visible_part_experiment' in s:
  v=s['visible_part_experiment'];out.append(f"局部部位副庫要求待測 ≥{v['target_min']:.2f}，實際 {f(tm)}，差 {v['target_min']-tm:.5f}；幾何 {json.dumps(v['geometry'],ensure_ascii=False)}。僅看外露局部，不輸入遮擋物本體。")
 meta=s.get('correspondence_experiment',{})
 for pad,v in meta.get('contour_views',{}).items():
  q=v.get('paired_evidence',{});out.append(f"完整輪廓外擴{pad}複核：待測 {f(q.get('target',{}).get('screw_margin'))}／參照 {f(q.get('reference',{}).get('screw_margin'))}；{v.get('decision_reason','')}。")
 rv=s.get('integrated_contour_review',{})
 if rv.get('performed'):
  vs=rv['views'];mean=sum(v['target']['screw_margin'] for v in vs)/len(vs);refs=[v['reference']['screw_margin'] for v in vs]
  out.append(f"既有副庫四範圍複核：待測平均 {f(mean)}（須≥0）；參照各值 {','.join(f(x) for x in refs)}（須每個<0）；接受={rv['accepted']}。")
 return out
for row in audit['rows']:
 for m in row['marks']:
  if m['kept_ids']:continue
  key=row['key'];mid=m['id'];pos=m['position'];ids=sorted(set(m['excluded_ids']+m['raw_matched_ids']))
  cc=[cases[key,i] for i in ids];notes=[];evidence=[]
  if pos=='D':
   cat='D：機體遮罩截斷';v=dg[key]
   notes=[f"答案有效拍攝範圍覆蓋100%；中心在機體遮罩外，答案區域僅 {v['machine_region_share']:.1%} 在遮罩內。主路徑超門檻像素剩 {v['main_threshold_pixels']}，開運算後 {v['main_open_pixels']}。",'局部遮罩後的連通塊：'+json.dumps(v['main_components'],ensure_ascii=False),'細容差路徑：'+json.dumps(v['tight_components'],ensure_ascii=False),'完整輪廓在不限制機體遮罩的幾何診斷中可形成 '+str(v['counterfactual_full_component']['area'])+' 像素；這只是幾何證據，未驗證 DINO 會保留。']
   evidence=['audit/candidate-diagnostics-summary.json'];basis='保存PNG幾何診斷支持；量化邊界可能與原始浮點略異。'
  elif pos=='C' and not m['excluded_ids']:
   cat='C：差分碎片小於補抓門檻';v=cg[key];a=v['stages']['7']['actual_mask'][str(mid)];b=v['stages']['3']['actual_mask'][str(mid)];areas=[x['area'] for x in b['components']]
   notes=[f"此處在機體遮罩內。主路徑原有 {a['raw_above_threshold_pixels']} 個超門檻像素，開運算後 {a['after_open_pixels']}，連通塊面積 {[x['area'] for x in a['components']]}，不足主路徑至少12。",f"細容差剩下兩個碎片，面積 {areas}，各自不足12；即使合起來也僅 {sum(areas)}，低於補抓至少25。配對碎片入口又要求每塊≥12，因此也進不去。",'保存影像幾何重算的補抓及可見部位候選均為空；原檢測結果此處也沒有候選。']
   evidence=['audit/miss46-C-geometry.json'];basis='三張保存PNG的針對性幾何診斷支持；非新推論，非浮點原執行逐步日誌。'
  else:
   if pos=='C':cat='C：既有圓形參照也像螺絲'
   elif pos=='A':cat='A：雙尺寸／物件占比未通過' if any(c['classification'].get('r4_experiment',{}).get('views') for c in cc) else 'A：主判正常範例分數較高'
   else:cat='B：只剩局部框且信心不足' if all('visible_part_experiment' in cases[key,i]['classification'] for i in m['excluded_ids']) else 'B：主判正常且補救未通過'
   basis='既有逐候選分數、實際取圖與執行規則可直接證實；不能據此宣稱某張範例刪掉就會改善。'
   for c in cc:
    if mid in c['proposal_answers']+c['proposal_ambiguous_answers'] and mid not in c['answers']:
     notes.append(f"候選 #{c['id']} 原框 {c['box']} 對到此答案，但改成 {c['canonical_box']}，實際對到答案 {c['answers']}；原框警報不能算本處命中。")
   if pos=='C':notes.append('新增物貼近既有圓形結構；待測分數雖支持螺絲，參照更強或也為正。以下同時列原裁圖與完整輪廓複核，避免只看最終標籤。')
   if pos=='A':notes.append('主板小圓形在既有裁圖下正常範例支持較強，或外擴後支持下降；以下列出每個尺度與占比的實際失敗項。背景混入是否為特徵錯誤的主因，現有分數尚不足以單獨證明。')
   evidence=['runs/4r/'+key+'/result.json'];notes+=['候選 #'+str(c['id'])+'：'+' '.join(analyze(c)) for c in cc]
  rec=dict(photo=key,answer_id=mid,position=pos,category=cat,candidate_ids=ids,original_r3_hit=mid in next(r for r in read('rows.json') if r['key']==key)['baseline_hits'],findings=notes,basis=basis,evidence=evidence,candidate_evidence=[dict(id=c['id'],query_box=c['box'],canonical_box=c['canonical_box'],actual_answers=c['answers'],classification=c['classification']) for c in cc])
  assert notes;records.append(rec)
assert len(records)==46 and len({(r['photo'],r['answer_id']) for r in records})==46
expected={(m['photo'],m['id']) for m in read('answer-matches.json') if not m['hit']};assert expected=={(r['photo'],r['answer_id']) for r in records}
counts=Counter(r['category'] for r in records)
save('audit/miss46-ledger.json',dict(complete=True,misses=46,groups=counts,records=records,inference_rerun=False,limitations='機制由保存證據確認；影像/範例的因果歸因未做消融實驗。三張C僅針對性CPU幾何重算，沒有DINO或整批檢測。'))
index=(P/'report/index.html').read_text(encoding='utf8');style=re.search(r'<style>(.*?)</style>',index,re.S).group(1)
body='<nav><a href="index.html">返回全圖資完整報告</a> · <a href="answers.html">全部48處答案</a> · <a href="diagnosis.html">原原因圖解</a></nav><h1>KPH33｜46處漏抓逐一對帳</h1><p>48處答案＝命中2處＋漏抓46處。本頁每個答案只算一次；多個候選及同一物件的不同取圖不重複計數。原完整照片、全部保留／排除候選與左右排版保持不變。</p><p>分數是螺絲相似度減正常相似度，不是機率。已證實的排除機制與仍需實驗的特徵原因分開說明；本次沒有重跑DINO或整批檢測。</p><table><tr><th>互斥原因組</th><th>漏抓處數</th></tr>'+''.join(f'<tr><td>{esc(k)}</td><td>{v}</td></tr>' for k,v in counts.items())+'<tr><th>合計</th><th>46</th></tr></table><p><a href="../audit/miss46-ledger.json">完整逐處數據與原始分類證據</a></p><ol>'+''.join(f'<li><a href="#miss-{r["photo"]}-{r["answer_id"]}">{r["photo"]} 答案#{r["answer_id"]}：{esc(r["category"])}</a></li>' for r in records)+'</ol>'
for r in records:
 k=r['photo'];n=r['answer_id'];body+=f'<article id="miss-{k}-{n}"><h2>{k}／答案#{n}：{esc(r["category"])}</h2><p>原r3命中：'+('是，本次退步' if r['original_r3_hit'] else '否')+f'。<a href="photo-{k}.html">完整照片與全部候選</a> · <a href="answers.html#mark-{k}-{n}">原答案記錄</a></p><img width="300" src="images/{k}-answer-{n}.jpg"><p>紅線是答案；黃框是排除範圍；藍框若僅鄰近／擦邊，不計本處命中。</p><ul>'+''.join('<li>'+esc(z)+'</li>' for z in r['findings'])+'</ul><p>'+esc(r['basis'])+'</p>'
 for i in r['candidate_ids']:
  body+=f'<details><summary>候選#{i}：參照左／待測右，紅原框／藍實際框</summary><a href="photo-{k}.html#case-{k}-{i}">查看原判斷及同類案例</a><br><img src="images/{k}-{i}.jpg"></details>'
 body+='<p>證據：'+' · '.join(f'<a href="../{p}">{esc(p)}</a>' for p in r['evidence'])+'</p></article>'
(P/'report/miss46.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>46處漏抓逐一對帳</title><style>'+style+'</style><main>'+body+'</main></html>',encoding='utf8')
for name in ['index.html','diagnosis.html','answers.html']+[f'photo-{r["key"]}.html' for r in read('rows.json')]:
 p=P/'report'/name;t=p.read_text(encoding='utf8');link='<p id="miss46-link"><a href="miss46.html">46處漏抓逐一分析與完整對帳 →</a></p>';t=re.sub(r'<p id="miss46-link">.*?</p>','',t);t=t.replace('</nav>','</nav>'+link,1);p.write_text(t,encoding='utf8')
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:assert a['id'] not in self.ids;self.ids.add(a['id'])
  for k in ['src','href']:
   if k in a:self.links.append(a[k])
parsed={}
for p in (P/'report').glob('*.html'):
 v=Parser();v.feed(p.read_text(encoding='utf8'));parsed[p.resolve()]=v
links=0
for p,v in parsed.items():
 for l in v.links:
  u=urlsplit(l);assert not u.scheme
  dest=(p.parent/unquote(u.path)).resolve() if u.path else p
  assert dest.exists(),l
  if u.fragment:assert unquote(u.fragment) in parsed[dest].ids,(p,l)
  links+=1
assert all(sha(P/n)==h for n,h in original.items())
assert all(sha(p)==h for p,h in protected.items())
assert all(not Path(p).exists() for p in plan.get('protected_absent',[]))
save('audit/miss46-verification.json',dict(status='passed',unique_misses=46,counts=counts,all_original_report_data_unchanged=True,protected_source_model_policy_files=len(protected),all_protected_hashes_unchanged=True,html_pages=len(parsed),links_checked=links,all_miss_keys_equal_original_46=True,ledger_sha256=sha(P/'audit/miss46-ledger.json')))
print(json.dumps(counts,ensure_ascii=False));print('PASS 46 misses, all report links, source/result hashes unchanged')
