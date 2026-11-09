import json,re,html,hashlib
from pathlib import Path
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
P=Path('workspace/kph33-4r-eval-20261109').resolve()
def rd(n):return json.loads((P/n).read_text(encoding='utf8'))
def esc(v):return html.escape(str(v))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
protected={str(p):sha(p) for p in (P/'runs').glob('*/*/result.json')};protected.update({str(P/n):sha(P/n) for n in ['cases.json','summary.json','answers.json','answer-matches.json']})
cases=rd('cases.json');misses=rd('audit/miss46-ledger.json')['records'];groups={}
for c in cases:
 if c['keep'] and not c['answers'] and not c['is_reference']:groups.setdefault((c['photo'],tuple(c['canonical_box'])),[]).append(c)
assert len(groups)==5 and sum(map(len,groups.values()))==27
index=P/'report/index.html';old=index.read_text(encoding='utf8');style=re.search(r'<style>(.*?)</style>',old,re.S).group(1)
head='<section id="decision-summary"><h2>本次結果：命中 2／48、過殺 5 處、漏失 46／48</h2><p>依本次提供的標準答案計分。過殺5處按「同張照片、相同實際判斷範圍」合併；原輸出有27個過殺框，其中22個是重複警報。跨照片分開計算。</p><p><a href="decision.html">逐項查看：5處過殺＋46處漏失，以及候選算法／DINO責任 →</a></p></section>'
body='<nav><a href="index.html">返回全圖資報告</a> · <a href="miss46.html">46處完整數值證據</a></nav><h1>KPH33：命中、過殺、漏失</h1>'+head+'<h2>命中：2處</h2><p>2278 答案#3、2296 答案#1。原r3命中4處，本版保住1處、漏掉3處、另命中1處。</p><h2>過殺：5處，逐項原因</h2><p>此處「過殺」指標準答案外的警報，不另要求你逐次確認；是否為答案漏標，與本輪依答案計分分開處理。</p>'
fp=[]
for n,((key,box),cs) in enumerate(groups.items(),1):
 c=cs[0];pair=c['classification']['paired_evidence'];tm=pair['target']['screw_margin'];rm=pair['reference']['screw_margin'];ids=[x['id'] for x in cs]
 kind='線材旁的小黑圓形' if key=='ng-2271' else '板上矩形元件的一小段'
 cause=f'DINO把{kind}判成螺絲；待測分數差 {tm:+.6f} 超過0，參照 {rm:+.6f} 低於0，所以保留。'
 algo='沒有相同範圍重複警報。' if len(cs)==1 else f'候選算法把多個原框改成同一個 {box[2]}×{box[3]} 小範圍，又保留 {len(cs)} 個重複警報；去重沒有生效。'
 fp.append(dict(photo=key,ids=ids,canonical_box=box,primary='DINO AI判定',algorithm_issue=algo,reason=cause))
 body+=f'<article id="overkill-{n}"><h3>過殺{n}：{key}／候選 '+','.join(map(str,ids))+'</h3><p><b>判錯原因：DINO AI判定。</b> '+esc(cause)+'</p><p><b>候選算法：</b>'+esc(algo)+f'</p><img width="800" src="images/{c["key"]}.jpg"><p>左參照、右待測；藍框是實際判斷範圍。<a href="photo-{key}.html#case-{c["key"]}">原候選與完整分數</a></p></article>'
body+='<h2>漏失：46處，逐項責任與原因</h2><p>「兩者」表示候選取圖／範圍條件與DINO分數都有明確失敗證據，不任選一個推卸原因。下表每個答案只計一次；詳細證據保留全部相關候選。</p><table><tr><th>照片／答案</th><th>問題環節</th><th>具體原因</th><th>證據</th></tr>'
responsibility=Counter();ledger=[]
for r in misses:
 cat=r['category'];where='DINO AI判定';why=''
 if cat.startswith('D：'):where='候選區算法';why='機體遮罩切掉螺絲；剩餘差分不足候選條件，DINO沒有取得此位置。'
 elif cat.startswith('C：差分'):where='候選區算法';why='差分切成8～11像素的小碎片，各自不足12；合起來18～21也不足補抓至少25。'
 elif cat.startswith('C：'):why='待測有新增物，但既有圓形參照也被DINO判像螺絲，雙圖規則將警報排除。'
 elif '雙尺寸' in cat:
  geom=False
  for e in r['candidate_evidence']:
   g=e['classification'].get('r4_experiment',{}).get('geometry',[])
   if not g or not g[0] or g[0]['near_share']<.15:geom=True
  where='候選區算法＋DINO AI判定' if geom else 'DINO AI判定'
  why='外擴兩種範圍後，DINO支持未達0.04；'+('物件占比也不足15%。' if geom else '尺度共識未通過。')
 elif 'A：' in cat:why='主板小圓形的DINO正常範例相似度較高，螺絲−正常分數小於0。'
 elif '只剩局部' in cat:
  moved=any('原框' in s and '改成' in s for s in r['findings']);where='候選區算法＋DINO AI判定' if moved else 'DINO AI判定'
  why=('原框被改成看旁邊物件；' if moved else '')+'仍對到答案的局部框，DINO支持分數低於要求0.05，未能保留。'
 else:why='DINO主判正常範例分數較高；已有局部補救時也未達0.05，所有對到答案的候選均未保留。'
 responsibility[where]+=1;ledger.append(dict(photo=r['photo'],answer=r['answer_id'],stage=where,reason=why))
 anchor=f'miss-{r["photo"]}-{r["answer_id"]}'
 body+=f'<tr><td>{r["photo"]}／#{r["answer_id"]}</td><td>{where}</td><td>{esc(why)}</td><td><a href="miss46.html#{anchor}">原圖、每個候選、分數與門檻</a></td></tr>'
body+='</table><p>證據限制：以上確認的是程式在哪個具體條件失敗；尚未藉由改庫實驗證明「刪掉哪張範例就一定改善」。</p>'
(P/'report/decision.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>命中、過殺、漏失</title><style>'+style+'</style><main>'+body+'</main></html>',encoding='utf8')
old=re.sub(r'<section id="decision-summary">.*?</section>','',old,flags=re.S);old=re.sub(r'(<h1>.*?</h1>)',lambda m:m.group(1)+head,old,count=1,flags=re.S)
old=re.sub(r'<p class="metrics">.*?</p>','',old,flags=re.S);index.write_text(old,encoding='utf8')
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:assert a['id'] not in self.ids;self.ids.add(a['id'])
  self.links += [a[k] for k in ['src','href'] if k in a]
parsed={}
for p in (P/'report').glob('*.html'):
 q=Parser();q.feed(p.read_text(encoding='utf8'));parsed[p.resolve()]=q
for p,q in parsed.items():
 for l in q.links:
  u=urlsplit(l);assert not u.scheme;dest=(p.parent/unquote(u.path)).resolve() if u.path else p;assert dest.exists(),l
  if u.fragment:assert unquote(u.fragment) in parsed[dest].ids,l
assert len(ledger)==46 and sum(responsibility.values())==46
assert all(sha(p)==h for p,h in protected.items())
(P/'audit/decision-ledger.json').write_text(json.dumps(dict(hits=2,misses=46,overkill_locations=5,overkill_frames=27,duplicate_overkill_frames=22,scope='依提供標準答案計分；同照片同實際範圍合併，不推定不同照片是不同實體',overkills=fp,miss_ledger=ledger,miss_responsibility_counts=responsibility,all_original_results_unchanged=True,all_report_links_verified=True),ensure_ascii=False,indent=2),encoding='utf8')
print(dict(responsibility));print('PASS: 2 hits; 5 overkill locations /27 frames; 46 misses; unchanged detections')
