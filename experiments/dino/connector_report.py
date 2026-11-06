"""Full 100-image terminal-review experiment report; upstream detections reused."""
import sys,copy,json,shutil
from pathlib import Path
from collections import Counter
import cv2,numpy as np
from PIL import Image,ImageDraw
from html.parser import HTMLParser
from urllib.parse import unquote
import answered_batch_report as common
from result_columns import columns
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-connector-20261106';PRIOR=ROOT/'workspace/dino-4r-example-audit-20261106/final'
read=common.read;save=common.save;sha=common.sha;esc=common.esc;table=common.table;TYPES=common.TYPES
NAV='<nav><a href="index.html">完整結果</a><a href="index.html#good">良品</a><a href="index.html#bad">不良品</a><a href="machine-MPT10.html">MPT10</a><a href="answers.html">全部答案</a><a href="comparison.html">附加：版本與資料重複核對</a><a href="connector-diagnosis.html">附加：接點判斷與穩定性</a></nav>'
def page(folder,name,title,body):
    (folder/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+common.STYLE+'</style><main>'+NAV+'<h1>'+esc(title)+'</h1>'+body+'</main></html>',encoding='utf8')
def main():
    assert read(OUT/'run-complete.json')['complete'];plan=read(OUT/'plan.json');report=OUT/'report';images=report/'images';images.mkdir(parents=True,exist_ok=True)
    original_answers=read(PRIOR/'answers.json');answers={};coordinate_changes=[]
    for item in plan['items']:
        if item['label']!='NG':continue
        serial=str(int(item['key'].split('-')[1]));a=copy.deepcopy(original_answers[serial]);ev=item['duplicate_previous'];assert ev
        if ev['kind']=='identical_oriented_pixels':
            assert not ev['flip'] and ev['quarter_turns']==1
            with Image.open(item['path']) as im:width=im.width
            for mark in a['marks']:
                mark['polygon']=[[width-1-y,x] for x,y in mark['polygon']];x,y=mark['center'];mark['center']=[width-1-y,x]
            coordinate_changes.append(dict(photo=item['key'],operation='Exact inverse of verified pixel rotation: source x=W-1-old_y, source y=old_x',reason='Same image orientation conversion only; no answer relabeling or fitting to predictions'))
        answers[item['key']]=a
    save(OUT/'answers.json',answers);save(OUT/'answer-coordinate-transforms.json',coordinate_changes)
    cases=[];rows=[];markrows=[]
    for number,item in enumerate(plan['items'],1):
        key=item['key'];folder=OUT/'runs'/key;r=read(folder/'result.json');baseline=read(folder/'baseline79-classifications.json');done=read(folder/'complete.json');assert sha(folder/'result.json')==done['result_sha256'] and sha(folder/'baseline79-classifications.json')==done['baseline_sha256']
        ref=Image.open(folder/'reference.png').convert('RGB');tar=Image.open(folder/'aligned.png').convert('RGB');marks=answers.get(key,{}).get('marks',[]);flow=np.zeros((ref.height,ref.width,2),np.float32)
        for region in r['local_alignment']:
            x,y,X,Y=region['bbox'];flow[y:Y,x:X]=[region['dx'],region['dy']]
        flow=cv2.GaussianBlur(flow,(0,0),12);cc=[]
        for c in sorted(r['candidates']+r['filtered_candidates'],key=lambda c:c['id']):
            pred=c['classification'];before=baseline[str(c['id'])];rules=pred.get('overkill_pilot',{}).get('rules',[])+pred.get('r4_experiment',{}).get('rules',[]);keep=pred['filter_recommendation']=='keep';paired=pred['paired_evidence'];assert keep==(paired['target']['label']=='screw' and paired['reference']['label']!='screw' and not rules)
            poly=common.native(c,r,flow);yes,edge=common.matches(poly,marks);oldc=dict(c,classification=before);oldpoly=common.native(oldc,r,flow);oldyes,_=common.matches(oldpoly,marks)
            category=next((cat for rule,cat in [('wire','wire'),('r4_wire_motion','wire'),('border','edge'),('corner','edge'),('component','component'),('r4_part_boundary','edge' if max(c['w'],c['h'])<=9 else 'component'),('r4_weak_object_extent','component')] if rule in rules),'unknown')
            z=dict(key=f'{key}-{c["id"]}',photo=key,id=c['id'],box=list(common.geom(c)),canonical_box=pred['canonical_object']['box'],machine='MPT10',label=item['label'],is_reference=item['is_reference'],keep=keep,baseline_keep=before['filter_recommendation']=='keep',answers=yes,baseline_answers=oldyes,edge_answers=edge,category=category,rules=rules,paired_evidence=paired,reason=pred['decision_reason'],source_polygon=poly.tolist(),new_review='example_crop_review' in pred)
            cc.append(z);x,y,w,h=z['box'];side=max(120,w+48,h+48);x0=int(max(0,min(ref.width-side,x+w/2-side/2)));y0=int(max(0,min(ref.height-side,y+h/2-side/2)));canvas=Image.new('RGB',(800,400),'white')
            for i,im in enumerate((ref,tar)):
                dx,dy=pred.get('correspondence_experiment',{}).get('reference_offset',[0,0]) if i==0 else (0,0);v=im.crop((x0+dx,y0+dy,x0+dx+side,y0+dy+side));draw=ImageDraw.Draw(v);draw.rectangle((x-x0-dx,y-y0-dy,x+w-x0-dx,y+h-y0-dy),outline='#eb2346');cx,cy,cw,ch=z['canonical_box'];draw.rectangle((cx-x0,cy-y0,cx+cw-x0,cy+ch-y0),outline='#00a5dd');canvas.paste(v.resize((400,400)),(i*400,0))
            canvas.save(images/f'{z["key"]}.jpg',quality=85)
        cases+=cc;hit=sorted({a for c in cc if c['keep'] for a in c['answers']});oldhit=sorted({a for c in cc if c['baseline_keep'] for a in c['baseline_answers']})
        rows.append(dict(**item,candidates=len(cc),kept=sum(c['keep'] for c in cc),excluded=sum(not c['keep'] for c in cc),baseline_kept=sum(c['baseline_keep'] for c in cc),hits=hit,baseline_hits=oldhit,answer_count=len(marks),unmatched=sum(c['keep'] and not c['answers'] for c in cc),baseline_unmatched=sum(c['baseline_keep'] and not c['baseline_answers'] for c in cc),alignment_warning=r['alignment_warning'],structure_changes=r['structure_changes']))
        for name,source in [('reference',folder/'reference.png'),('overlay',folder/'all_overlay.png'),('source',Path(item['path']))]:
            with Image.open(source) as im:im=im.convert('RGB');im.thumbnail((1400,1400));im.save(images/f'{key}-{name}.jpg',quality=88)
        if marks:
            im=Image.open(item['path']).convert('RGB');d=ImageDraw.Draw(im)
            for m in marks:
                pts=[tuple(p) for p in m['polygon']];d.line(pts+[pts[0]],fill='#ee244d',width=5);d.text(tuple(m['center']),str(m['id']),fill='#ee244d',stroke_width=2)
                markrows.append(dict(photo=key,id=m['id'],polygon=m['polygon'],hit=m['id'] in hit,candidates=[c['key'] for c in cc if c['keep'] and m['id'] in c['answers']]))
            im.thumbnail((1400,1400));im.save(images/f'{key}-answers.jpg',quality=90)
        print('REPORT',number,key,len(cc),'kept',sum(c['keep'] for c in cc),flush=True)
    good=[r for r in rows if r['label']=='OK' and not r['is_reference']];bad=[r for r in rows if r['label']=='NG'];refs=[r for r in rows if r['is_reference']]
    expected={(f'ng-{m["photo"]}',m['id']) for m in read(PRIOR/'answer-matches.json') if m['methods']['pilot']};actual={(m['photo'],m['id']) for m in markrows if m['hit']};lost=sorted(expected-actual)
    summary=dict(photos=len(rows),candidates=len(cases),good_photos=len(good),bad_photos=len(bad),reference_self_photos=len(refs),answers=len(markrows),answer_hits=len(actual),original79_preserved=not lost,lost_original_answers=lost,good_alarms=sum(r['kept'] for r in good),baseline_good_alarms=sum(r['baseline_kept'] for r in good),good_alert_photos=sum(r['kept']>0 for r in good),baseline_good_alert_photos=sum(r['baseline_kept']>0 for r in good),NG_unmatched=sum(r['unmatched'] for r in bad),baseline_NG_unmatched=sum(r['baseline_unmatched'] for r in bad),independent_new_defect_images=0,good_increased_photos=[r['key'] for r in good if r['kept']>r['baseline_kept']],NG_increased_photos=[r['key'] for r in bad if r['unmatched']>r['baseline_unmatched']],self_alarms=sum(r['kept'] for r in refs),thresholds_retuned=False,development_normal_example_added=True,upstream_detection_reused=True)
    summary['acceptance_passed']=not lost and not summary['good_increased_photos'] and not summary['NG_increased_photos'] and summary['self_alarms']==0
    stability=read(OUT/'stability-proof.json');summary['stability_passed']=stability['query_passed'] and stability['image_resample_passed'];summary['acceptance_passed']=summary['acceptance_passed'] and summary['stability_passed']
    overlap=read(OUT/'example-source-overlap.json');example_sources={z['source'] for z in overlap};summary['normal_example_source_matches']=dict(example_ids=len(overlap),photos=len(example_sources),authority='Normal-example ID source SHA naming matches; no claim of unseen data for other photos')
    summary['good_source_groups']={name:dict(photos=len(group),alarms=sum(r['kept'] for r in group),baseline_alarms=sum(r['baseline_kept'] for r in group)) for name,group in [('example_source_match',[r for r in good if r['path'] in example_sources]),('no_match_in_example_ids',[r for r in good if r['path'] not in example_sources])]}
    save(OUT/'summary.json',summary);save(OUT/'cases.json',cases);save(OUT/'rows.json',rows);save(OUT/'answer-matches.json',markrows)
    def card(c):
        label='保留警報' if c['keep'] else '排除';pair=c['paired_evidence'];answer='答案'+','.join(map(str,c['answers'])) if c['answers'] else '未對到答案' if c['label']=='NG' else '來源標為良品；警報待核對'
        return f'<article id="case-{c["key"]}"><h3>{c["photo"]}／候選#{c["id"]}：{label}</h3><p>{TYPES[c["category"]]} · '+('待確認（未人工分類）' if c['category']=='unknown' else '規則自動推測')+f' · {answer}</p><p><a href="photo-{c["photo"]}.html#case-{c["key"]}">查看照片</a> · <a href="category-{c["category"]}.html#case-{c["key"]}">查看同類案例</a> · <a href="machine-MPT10.html">返回機種</a></p><p>左：參照圖　右：待測圖</p><img loading="lazy" class="pair" src="images/{c["key"]}.jpg" alt="參照與待測"><p>參照：'+('像螺絲' if pair['reference']['label']=='screw' else '不像螺絲')+'；待測：'+('像螺絲' if pair['target']['label']=='screw' else '不像螺絲')+f'。{esc(c["reason"])}</p><details><summary>判斷依據與實際範圍</summary><p>原候選紅框{c["box"]}；實際物件藍框{c["canonical_box"]}；參照分數{pair["reference"]["screw_margin"]:.4f}，待測分數{pair["target"]["screw_margin"]:.4f}。分數不是機率。規則：{esc(", ".join(c["rules"]) or "無")}。</p></details></article>'
    def photo_table(rs):return table(['照片','分類','保留候選','排除候選','答案命中','警報核對'],[[f'<a href="photo-{r["key"]}.html">{esc(r["name"])}</a>','參照自比' if r['is_reference'] else '良品' if r['label']=='OK' else '不良品',r['kept'],r['excluded'],f'{len(r["hits"])}/{r["answer_count"]}' if r['label']=='NG' else '不適用',f'框外{r["unmatched"]}' if r['label']=='NG' else '自比獨立統計' if r['is_reference'] else f'良品警報{r["kept"]}'] for r in rs])
    note='<p class="warn">本資料夾的不良圖與原開發批重複，不是另一批新螺絲驗收；詳見資料核對附頁。良品依來源OK資料夾標示，尚未把每個警報人工確認成誤報。候選框數不等於螺絲顆數，參照自比不算一般良品成績。</p>'
    page(report,'index.html','4r MPT10｜正常接點複核・100張全圖資結果',note+f'<p>本次完整收錄100張：89張一般良品、10張不良品、1張參照自比。答案命中{len(actual)}／101；良品警報{summary["good_alarms"]}框，涉及{summary["good_alert_photos"]}張；不良品答案框外警報{summary["NG_unmatched"]}框。</p><p><a href="machine-MPT10.html">依機種 → 誤報類型 → 相近位置查看</a></p><h2 id="good">良品完整結果</h2>'+photo_table(good)+'<h2 id="bad">不良品完整結果</h2>'+photo_table(bad)+'<h2>參照圖自比</h2>'+photo_table(refs))
    counts=Counter(c['category'] for c in cases);page(report,'machine-MPT10.html','MPT10 → 誤報類型',table(['類型','全部候選框','人工確認分類'],[[f'<a href="category-{k}.html">{v}</a>',counts[k],0] for k,v in TYPES.items()])+'<p>本次指定資料夾只有MPT10，未混入其他機種。</p>'+photo_table(rows))
    for kind,label in TYPES.items():
        selected=[c for c in cases if c['category']==kind];body=f'<p><a href="machine-MPT10.html">返回MPT10</a>；{len(selected)}候選，分類為自動推測或待確認。</p>'
        for i,g in enumerate(common.grouped(selected),1):body+=f'<section><h2>相近位置{i}／{len(g)}候選</h2>'+columns(g,card,lambda c:c['keep'],True)+'</section>'
        if not selected:body+='<p>0 個案例。</p>'
        page(report,f'category-{kind}.html','MPT10 → '+label+' → 相近位置',body)
    for r in rows:
        key=r['key'];cc=[c for c in cases if c['photo']==key];ct=Counter(c['category'] for c in cc);body=f'<p><a href="machine-MPT10.html">返回此機種</a> · <a href="category-unknown.html">查看同類案例</a></p><p>分類：'+esc('、'.join(f'{TYPES[k]} {ct[k]}' for k in TYPES))+f'。保留{r["kept"]}、排除{r["excluded"]}。對位提醒：{r["alignment_warning"]}。</p><div class="grid"><div>參照圖<img src="images/{key}-reference.jpg"></div><div>待測與保留框<img src="images/{key}-overlay.jpg"></div></div><details><summary>原始照片</summary><img src="images/{key}-source.jpg"></details>'
        if r['label']=='NG':body+=f'<p><a href="answers.html#answer-{key}">查看本張答案</a></p>'
        body+='<h2>全部保留與排除候選</h2>'+columns(cc,card,lambda c:c['keep'])
        if r['structure_changes']:body+='<details><summary>其他結構變化（不當螺絲）</summary><pre>'+esc(json.dumps(r['structure_changes'],ensure_ascii=False,indent=2))+'</pre></details>'
        page(report,f'photo-{key}.html','MPT10／'+r['name'],body)
    body='<p>沿用同一影像的101處既有答案。128僅依已核實90度像素旋轉換算座標；無新增或移動答案來配合結果。沿用中心重疊規則，擦邊不算。</p>'
    for r in bad:
        key=r['key'];ms=[m for m in markrows if m['photo']==key]
        body+=f'<section id="answer-{key}"><h2>{key}</h2><p><a href="photo-{key}.html">返回完整照片</a></p><img src="images/{key}-answers.jpg">'+table(['答案','本次結果','候選'],[[m['id'],'命中' if m['hit'] else '未命中','、'.join(f'<a href="photo-{key}.html#case-{c}">{c}</a>' for c in m['candidates']) or '無'] for m in ms])+'</section>'
    page(report,'answers.html','全部101處答案核對',body)
    body=note+'<h2>資料是否真正換批</h2><p>10張不良圖全部與原批相同：9張檔案SHA相同；128經90度旋轉後逐像素相同。因此獨立新不良圖為0。另89張一般良品做本輪額外回歸，沒有宣稱它們從未出現在先前r3開發／範例來源中。</p><h2>固定版本比較</h2><p>比較同一張圖、相同參照與相同候選下的原79版與目前79版。本次沿用原100張的對位、候選與既有判斷，只對符合條件的保留警報重新執行DINO正常結構複核；沒有重跑整段檢測。</p>'+table(['指標','原79版（同張圖）','接點複核版本次'],[['不良品答案命中',sum(len(r['baseline_hits']) for r in bad),len(actual)],['不良品框外警報',summary['baseline_NG_unmatched'],summary['NG_unmatched']],['89張良品警報',summary['baseline_good_alarms'],summary['good_alarms']],['良品有警報張數',summary['baseline_good_alert_photos'],summary['good_alert_photos']]])
    body+=f'<p>原79處遺失：{len(lost)}處。良品警報增加照片：{esc("、".join(summary["good_increased_photos"]) or "無")}；不良品框外增加照片：{esc("、".join(summary["NG_increased_photos"]) or "無")}。本輪保護條件：'+('通過' if summary['acceptance_passed'] else '未通過；不把本輪結果稱為誤報不增加')+'。</p><p>本輪是開發實驗：依使用者確認，只取128 #22作正常接點範例，#40未加入範例庫但已看過，不能稱盲測。47＋65完整比例範例庫保持不變；另設一個正常接點比對庫。正式流程不變。</p>'
    body+=f'<h2>與正常範例來源重疊</h2><p>{len(overlap)}個正常範例ID中的來源SHA對到本資料夾{len(example_sources)}張良品；因此也不能把這個良品集合稱為完全未見的盲測。這是依來源雜湊命名紀錄核對，其他未匹配ID的照片也不直接宣稱獨立。</p>'+table(['良品來源分組','照片','前輪警報','本次警報'],[[('範例ID來源有匹配' if k=='example_source_match' else '未從範例ID查到匹配'),v['photos'],v['baseline_alarms'],v['alarms']] for k,v in summary['good_source_groups'].items()])+'<p><a href="../example-source-overlap.json">正常範例與來源匹配紀錄</a></p>'
    body+=table(['照片','前輪保留','本次保留','差異'],[[f'<a href="photo-{r["key"]}.html">{r["name"]}</a>',r['baseline_kept'],r['kept'],r['kept']-r['baseline_kept']] for r in rows])
    body+='<p><a href="../source-inventory.json">來源SHA及重複證據</a> · <a href="../plan.json">凍結計畫</a> · <a href="../answer-coordinate-transforms.json">128座標換算</a> · <a href="../summary.json">統計</a> · <a href="../verification.json">完整性驗證</a></p>';page(report,'comparison.html','附加：版本比較與資料重複核對',body)
    diagnosis(report,cases)
    verify(report,images,cases,rows,plan,summary)
def verify(report,images,cases,rows,plan,summary):
    save(OUT/'verification.json',dict(status='checking'))
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[];self.stack=[];self.outcomes={}
        def handle_starttag(self,t,a):
            d=dict(a)
            if 'id' in d:self.ids.append(d['id'])
            self.links.extend(d[k] for k in ('href','src') if k in d)
            if t=='section':self.stack.append(d.get('data-result'))
            if t=='article' and d.get('id','').startswith('case-'):self.outcomes[d['id'][5:]]=next((v for v in reversed(self.stack) if v),None)
        def handle_endtag(self,t):
            if t=='section':self.stack.pop()
    parsed={};ci={c['key']:c for c in cases};links=0
    for p in report.glob('*.html'):
        v=Parser();v.feed(p.read_text(encoding='utf8'));assert len(v.ids)==len(set(v.ids)),p;parsed[p.resolve()]=v
        for key,side in v.outcomes.items():assert side==('keep' if ci[key]['keep'] else 'exclude'),(p,key,side)
    for p,v in parsed.items():
        for link in v.links:
            name,_,anchor=link.partition('#');dest=(p.parent/unquote(name)).resolve() if name else p;assert dest.exists(),(p,link)
            if anchor:assert anchor in parsed[dest].ids,(p,link)
            links+=1
    for r in rows:assert set(parsed[(report/f'photo-{r["key"]}.html').resolve()].outcomes)=={c['key'] for c in cases if c['photo']==r['key']}
    for kind in TYPES:assert set(parsed[(report/f'category-{kind}.html').resolve()].outcomes)=={c['key'] for c in cases if c['category']==kind}
    checked_images=list(images.glob('*.jpg'))+list(report.glob('*.png'))
    for p in checked_images:
        with Image.open(p) as im:im.verify()
    assert all(sha(p)==h for p,h in plan['hashes'].items());assert len(rows)==100 and summary['answers']==101
    save(OUT/'verification.json',dict(status='passed',html_pages=len(parsed),links_checked=links,images_checked=len(checked_images),photos=100,candidates=len(cases),all_candidates_in_correct_outcome_column=True,all_photos_and_category_candidates_covered=True,frozen_policy_and_source_hashes_unchanged=True,acceptance_passed=summary['acceptance_passed'],original79_preserved=summary['original79_preserved'],independent_new_defect_images=0,result_sha256={r['key']:sha(OUT/'runs'/r['key']/'result.json') for r in rows}))
    print('VERIFIED',len(parsed),'pages',links,'references',len(cases),'candidates',flush=True)

def diagnosis(report,cases):
    proof=read(OUT/'stability-proof.json');old=read(ROOT/'workspace/dino-4r-crossbatch-20261106/cases.json');index={c['key']:c for c in old}
    changed=[c for c in cases if c['keep']!=index[c['key']]['keep']]
    body='<p>使用者確認：128 #22與#40都是正常結構，應排除。這是實際判斷複核，並非把報告文字改成一致。</p>'
    body+='<h2>為何原本相反</h2><p>#40原待測分數+0.0616，#22為−0.1282。舊取圖會將長方形放大後只取中央正方形；#40的兩端遭切掉，模型只看到密集接點。其最接近的螺絲範例為S07、S05、S20。原範例配對未能可靠區分接點與螺紋。分數是相似度差，不是機率。</p><p>#40使用原範例庫、背景2／4／8／12像素時，分數依序−0.0119、−0.0196、+0.0237、+0.0616，會隨取圖翻轉；完整外形與兩類一致取圖時四範圍皆為負值。既有79版的完整比例補救只處理特定漏抓候選，沒有複核這個原本已保留的警報。</p>'
    shutil.copy2(OUT/'actual-inputs.png',report/'actual-inputs.png');body+='<img src="actual-inputs.png" alt="兩例實際模型輸入：左為舊中央裁圖，右為完整外形"><p>上排#40，下排#22；左欄是舊模型真正看到的輸入，右三欄保留完整外形。</p>'
    body+='<h2>本輪實際規則</h2><p>在既有79版完成後，另做正常結構複核。保留完整外形的2／4／8／12像素四範圍必須全部較接近原65張正常範例；整體與局部特徵的四範圍平均，都必須比各範圍最相似的47張螺絲範例更接近人工確認的接點#22；物件長寬比例與正常範例相差不得超過兩倍，才排除。若條件不足，沿用原判斷。雙圖均重新推論；遮擋螺絲B的局部辨識保持原判斷。</p><p>只將#22加入獨立正常比對庫；未把#40加入。兩者均已在開發時看過，不是獨立驗收。本輪規則是在這批開發，幾何條件仍需要新批圖驗證。</p><h2>未採用版本也保留</h2><p>初版原79處保住，但#40影像放大125%仍留警報。第二版增加正常範例取圖範圍，仍未修好放大問題，且會排除5個已命中螺絲，未採用。現版恢復單一#22正常範例，加入比例核對與四範圍平均證據。單純把所有完整外形負分警報刪除的方案也未採用。</p><p><a href="../diagnostic-v1/stability-proof.json">初版縮放失敗紀錄</a> · <a href="../rejected-v2.json">第二版保護失敗紀錄</a></p>'
    body+='<h2>兩例與穩定性</h2>'+table(['案例','人工判定','原版','本輪'],[[f'<a href="photo-ng-128.html#case-ng-128-{i}">128 #{i}</a>','正常／排除','保留' if index[f'ng-128-{i}']['keep'] else '排除','保留' if next(c for c in cases if c['key']==f'ng-128-{i}')['keep'] else '排除'] for i in (22,40)])
    body+=f'<p>候選框位移／縮放：{sum(t["verdict"]=="exclude" and t["same_object"] for t in proof["query_tests"])}／{len(proof["query_tests"])}，每次重新推論。位移±4像素，大小75%、90%、100%、110%、125%。影像實際縮放的辨識診斷：{sum(t["exclude"] for t in proof["image_resample_tests"])}／{len(proof["image_resample_tests"])}；此項以縮放後的物件位置測複核器，未重新產生候選。兩項都不代表新拍攝批次驗證。</p>'
    body+='<h2>全部變更案例</h2><p>以下未對到答案的警報減少，不把未經人工確認的其他案例一律稱為已確認誤報。其餘完整結果請看首頁。</p>'+table(['照片／候選','原結果','本輪','對到答案'],[[f'<a href="photo-{c["photo"]}.html#case-{c["key"]}">{c["key"]}</a>','保留' if index[c['key']]['keep'] else '排除','保留' if c['keep'] else '排除',str(c['answers']) if c['answers'] else '無'] for c in changed])
    body+='<p><a href="../human-confirmations.json">本輪人工確認</a> · <a href="../stability-proof.json">完整穩定性測試</a> · <a href="../run-complete.json">100張複核執行紀錄</a></p>'
    page(report,'connector-diagnosis.html','附加：正常接點判斷與穩定性',body)

if __name__=='__main__':main()

