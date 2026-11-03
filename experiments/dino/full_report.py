"""DINO full-data visual report; reads results only."""
import sys,json,hashlib
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.current_dataset_review import report as R
OUT=ROOT/'workspace/windows-check/diagnostics/dino-full-evaluation-20261103';OLD=ROOT/'workspace/windows-check/diagnostics/v11-examples-full-evaluation-20261103'
R.OUT=OUT;R.LABEL['non_screw']='非螺絲'
original_save=R.save

def save(name,title,body,script=''):
 body=body.replace('CLIP 螺絲外型範例版','DINOv2 螺絲範例版（實驗版）').replace('本次目視抽查：','前次疑似誤刪位置，本次仍排除：').replace('抽查疑似誤刪','前次疑似位置仍排除')
 original_save(name,title,body,script)
R.save=save
read=R.read;esc=R.esc;stats=R.stats

def main():
 rows=read(OUT/'results.json');plan=read(OUT/'plan.json');assert len(rows)==len(plan['items']) and all(r['success'] for r in rows)
 manifest=read(ROOT/'models'/plan['model']['requested']/'manifest.json');bankshas={n.rsplit('-',1)[0] for n in manifest['example_bank']['normal']['ids']}
 known={}
 for sample in read(ROOT/'review/annotations.json')['samples'].values():
  path=ROOT/'workspace/windows-check'/sample['file']
  if path.exists():known[hashlib.sha256(path.read_bytes()).hexdigest()]=sample['objects']
 tracked=[]
 for z in read(ROOT/'experiments/current_dataset_review/visual_review.json'):
  old=read(OLD/'photos'/z['sha256']/'result.json');oc=next(c for c in old['filtered_candidates'] if c['id']==z['candidate_id']);new=read(OUT/'photos'/z['sha256']/'result.json')
  allc=new['candidates']+new['filtered_candidates'];matches=[c for c in allc if R.overlap(c['source_bbox'],oc['source_bbox'])>.5]
  kept={c['id'] for c in new['candidates']};tracked.append(dict(z,matching_ids=[c['id'] for c in matches],retained_ids=[c['id'] for c in matches if c['id'] in kept],removed_ids=[c['id'] for c in matches if c['id'] not in kept],status='保留' if any(c['id'] in kept for c in matches) else '仍排除' if matches else '本次差分沒有相符候選',old_candidate=oc))
 for i,r in enumerate(rows):
  r['example_source']=r['sha256'] in bankshas;r['visual_issue_count']=sum(z['sha256']==r['sha256'] and z['status']=='仍排除' for z in tracked)
  R.photo(r,known)
  if (i+1)%25==0:print('Report',i+1,'/',len(rows),flush=True)
 tested=[r for r in rows if not r['is_reference']];good=[r for r in tested if r['label']=='OK'];bad=[r for r in tested if r['label']=='NG'];g,b=stats(good),stats(bad)
 groups={}
 for machine in sorted({r['machine'] for r in tested}):
  for label in ['OK','NG']:
   subset=[r for r in tested if r['machine']==machine and r['label']==label]
   if subset:groups[machine+'/'+label]=stats(subset)
 checks=[k for r in tested for k in r['known_checks']];oldrows=read(OLD/'results.json');oldlookup={r['relative']:r for r in oldrows}
 comparable=all(r['relative'] in oldlookup and r['sha256']==oldlookup[r['relative']]['sha256'] and r['reference_sha256']==oldlookup[r['relative']]['reference_sha256'] and r['pre_ai_count']==oldlookup[r['relative']]['pre_ai_count'] for r in rows)
 summary=dict(complete=True,images=len(rows),reference_images=sum(r['is_reference'] for r in rows),good=g,bad=b,groups=groups,model=plan['model'],prior_suspected_cases=tracked,known_batch_regions=len(checks),known_batch_retained=sum(bool(k['retained_ids']) for k in checks),clip_inputs_references_candidate_counts_match=comparable)
 nav=R.NAV;retained=sum(z['status']=='保留' for z in tracked);removed=sum(z['status']=='仍排除' for z in tracked)
 body=nav+'<h1>目前版本：良品與不良品檢測結果</h1><p>DINOv2 螺絲範例版（實驗版） · 每機種一張參照圖 · 差分門檻 0.13 · 未套用 upper-green 補框</p>'
 body+=f'<div class="answer"><b>本次已完成 {len(rows)} 張重新檢測；{sum(r["is_reference"] for r in rows)} 張參照圖自比不列入成效。</b><p><b>良品：{g["images"]} 張中，{g["zero"]} 張零誤報，{g["positive"]} 張仍有誤報。</b></p><p>誤報框由 {g["before"]} 個降為 {g["after"]} 個，DINO 排除 {g["removed"]} 個（{g["removed"]/max(1,g["before"]):.1%}）。</p><p><b>不良品：{b["images"]} 張，保留 {b["after"]} 個候選，排除 {b["removed"]} 個。</b></p><p>前次報告的 6 處疑似誤刪位置：DINO 保留 {retained} 處、仍排除 {removed} 處。這是既有疑似位置追蹤，並非本次重新完整標註的漏檢數。</p><a href="issues.html">看這 6 處參照／待測對照 →</a><p>本批 {len(checks)} 處既有目視標記，保留 {summary["known_batch_retained"]} 處。歷史 upper-green 標記有對應疑義，不再沿用「8 處全部保留」作驗收結論。</p></div>'
 body+='<h2>良品：還剩多少誤報？</h2><table><tr><th>機種</th><th>張數</th><th>原誤報框</th><th>AI 刪除</th><th>剩餘誤報框</th><th>零誤報照片</th></tr>'
 for key,s in groups.items():
  if key.endswith('/OK'):body+=f'<tr><td>{key[:-3]}</td><td>{s["images"]}</td><td>{s["before"]}</td><td>{s["removed"]}</td><td>{s["after"]}</td><td>{s["zero"]}</td></tr>'
 body+='</table><p><a href="good.html">逐張看剩餘誤報與已刪除位置 →</a></p>'
 a=stats([r for r in good if r['example_source']]);h=stats([r for r in good if not r['example_source']]);body+=f'<p>{a["images"]} 張照片曾提供非螺絲範例，剩 {a["after"]} 框；另 {h["images"]} 張未提供範例，剩 {h["after"]} 框。清單標示用途，不能把兩組合計當成獨立驗收準確率。</p>'
 body+='<h2>與前次 CLIP 報告比較</h2><table><tr><th>項目</th><th>前次 CLIP</th><th>本次 DINO</th></tr>'
 og=stats([r for r in oldrows if not r['is_reference'] and r['label']=='OK']);ob=stats([r for r in oldrows if not r['is_reference'] and r['label']=='NG'])
 for title,aa,bb in [('良品剩餘誤報框',og['after'],g['after']),('良品零誤報照片',og['zero'],g['zero']),('不良品保留候選框',ob['after'],b['after']),('不良品排除候選框',ob['removed'],b['removed'])]:body+=f'<tr><td>{title}</td><td>{aa}</td><td>{bb}</td></tr>'
 body+='</table><p>'+('已核對原始圖、參照圖雜湊及每張差分候選數一致。' if comparable else '本次與舊報告的輸入／參照／候選數存在差異，不能直接歸因於更換 AI。')+'</p><h2>不良品：保留和刪掉哪些位置？</h2><p><a href="bad.html">逐張看不良品，並核對被刪位置 →</a></p><p>保留框不是螺絲顆數，排除框也不一定全是非螺絲。這批 NG 尚無完整逐顆標註，因此不宣稱召回率或全部螺絲都已抓到；每張附保留與排除位置供核對。</p>'
 body+=f'<details><summary>參照圖與執行紀錄</summary><p>AI 推論錯誤 {g["errors"]+b["errors"]} 個候選。固定 DINO 模型與原有取圖方式；結果另存，未覆寫正式人工紀錄與 CLIP 報告。</p><ul>'+''.join(f'<li>{m}：{esc(Path(ref["path"]).name)}</li>' for m,ref in plan['references'].items())+'</ul><a href="plan.json">執行設定</a> · <a href="summary.json">完整統計</a></details>'
 body+=f'<p><b>{b["zero"]} 張不良品變成零候選，不能解讀為良品。</b> <a href="known.html">查看本批既有目視標記位置 →</a></p>'
 save('index.html','DINO 全圖資檢測報告',body);R.listing(good,True);R.listing(bad,False)
 body=nav+'<h1>前次 6 處疑似誤刪位置：DINO 的結果</h1><p>沿用前次目視標記，按原圖位置對應本次候選。這不是新一輪完整漏檢標註。</p>'
 for z in tracked:
  folder=OUT/'photos'/z['sha256'];rr=read(folder/'result.json');ids=z['matching_ids'];c=next((c for c in rr['candidates']+rr['filtered_candidates'] if c['id'] in ids),z['old_candidate'])
  with Image.open(folder/'aligned.png') as im:w,h=im.size
  prefix='photos/'+z['sha256']+'/';pair=R.pair(c,w,h).replace('href="reference.png"',f'href="{prefix}reference.png"').replace('href="aligned.png"',f'href="{prefix}aligned.png"')
  body+=f'<article><h2>{esc(z["relative"])}</h2><p>前次 CLIP 排除；本次 DINO：<b>{z["status"]}</b>。相符候選：{ids}</p>'+pair+f'<a href="{prefix}report.html">查看整張與全部排除位置</a></article>'
 save('issues.html','既有疑似誤刪位置追蹤',body)
 knownbody=nav+'<h1>本批既有目視標記位置核對</h1><p>按原圖標記與候選位置重疊核對；不是完整螺絲清冊。</p>'
 for row in rows:
  for mark in row['known_checks']:
   folder=OUT/'photos'/row['sha256'];rr=read(folder/'result.json');ids=mark['retained_ids']+mark['removed_ids']
   knownbody+=f'<article><h2>{esc(row["relative"])}</h2><p>相符保留候選：{mark["retained_ids"]}；相符排除候選：{mark["removed_ids"]}。</p>'
   for c in rr['candidates']+rr['filtered_candidates']:
    if c['id'] not in ids:continue
    with Image.open(folder/'aligned.png') as im:w,h=im.size
    prefix='photos/'+row['sha256']+'/'
    knownbody+=R.pair(c,w,h).replace('href="reference.png"',f'href="{prefix}reference.png"').replace('href="aligned.png"',f'href="{prefix}aligned.png"')
   knownbody+='</article>'
 save('known.html','既有目視標記核對',knownbody)
 for name,value in [('summary.json',summary),('report-rows.json',rows),('visual-issues.json',tracked)]: (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in summary.items() if k!='prior_suspected_cases'},ensure_ascii=True))
if __name__=='__main__':
 main()
 from experiments.dino.grouped_review import main as grouped_review
 grouped_review()
