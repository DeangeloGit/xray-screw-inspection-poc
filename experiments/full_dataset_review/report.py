"""Standalone OK/NG review reports; never equate candidate presence with recall."""
import sys,json,html,hashlib
from pathlib import Path
from collections import Counter
from statistics import median
from PIL import Image,ImageDraw,ImageFont

PROJECT=Path(__file__).resolve().parents[2]
OUT=PROJECT/'workspace/windows-check/diagnostics/v10-full-evaluation-20261103'
STYLE='''body{font:17px/1.7 "Microsoft JhengHei",sans-serif;color:#173b47;background:#f5f8fa;max-width:1450px;margin:30px auto;padding:0 20px}a{color:#007a85}h1{font-size:29px}h2{font-size:23px}.notice{padding:16px;background:#fff4d7;border-left:5px solid #e4ac26}.panel,article{background:white;border:1px solid #dbe4e8;border-radius:10px;padding:18px;margin:18px 0}table{border-collapse:collapse;width:100%;background:white;font-size:15px}td,th{border:1px solid #dce4e8;padding:8px;text-align:left;overflow-wrap:anywhere}th{background:#eaf2f4}img{max-width:100%;height:auto}.triple{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}.pair svg{width:100%;background:#fff}.bad{color:#b02c36}.muted{color:#607781}button,input,select{font:inherit;padding:6px}nav a{display:inline-block;margin-right:18px}.stats{display:flex;gap:20px;flex-wrap:wrap}.stat{background:white;padding:12px 24px;border:1px solid #dbe4e8;border-radius:8px}.stat b{display:block;font-size:26px}article[hidden],tr[hidden]{display:none}.controls{position:sticky;top:0;padding:12px;background:#eaf2f4;z-index:3}code{overflow-wrap:anywhere}details{margin:12px 0}@media(max-width:800px){.triple{grid-template-columns:1fr}.pair{gap:8px}body{padding:0 10px}table{font-size:13px}}'''
LABELS={'screw':'疑似螺絲','uncertain':'不確定','cable':'線材','circuit_board':'電路板','metal_plate':'金屬片','hole':'孔洞','background':'背景'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def esc(x):return html.escape(str(x))
def page(title,body,script=''):return f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}</style>{body}<script>{script}</script></html>'

def overlap(a,b):
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return inter/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter)

def known_annotations():
    annotations=read(PROJECT/'review/annotations.json');result={}
    for name,row in annotations['samples'].items():
        path=PROJECT/'workspace/windows-check'/row['file']
        if path.exists():result[hashlib.sha256(path.read_bytes()).hexdigest()]=row['objects']
    return result

def photo_page(row,known):
    folder=OUT/'photos'/row['sha256']
    if (folder/'report.html').exists():return
    title=f'{row["machine"]} / {row["label"]} / {Path(row["path"]).name}'
    navigation='<nav><a href="../../index.html">總報告</a><a href="../../good.html">良品報告</a><a href="../../bad.html">不良品報告</a></nav>'
    if not row['success']:
        (folder/'report.html').write_text(page(title,navigation+f'<h1>{esc(title)}</h1><p class="notice">分析失敗，不能當成零候選或正常。</p><p>{esc(row["error"])}</p><p>來源：{esc(row["path"])}</p>'),encoding='utf-8');return
    r=read(folder/'result.json')
    with Image.open(folder/'aligned.png') as image:
        overlay=image.convert('RGB');width,height=overlay.size
    draw=ImageDraw.Draw(overlay);font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',16)
    for c in r['candidates']:
        x,y,w,h=(c[k] for k in ('x','y','w','h'));color='#e1263b' if c['priority']=='high' else '#df9e00'
        draw.rectangle((x-2,y-2,x+w+2,y+h+2),outline=color,width=2);draw.text((x,max(0,y-20)),str(c['id']),font=font,fill=color)
    overlay.save(folder/'aligned_overlay.png')
    marked=[]
    for obj in known.get(row['sha256'],[]):
        matches=[c for c in r['candidates'] if overlap(c['source_bbox'],obj['bbox'])>.15]
        marked.append(dict(bbox=obj['bbox'],matched_ids=[c['id'] for c in matches],high=any(c['priority']=='high' for c in matches)))
    (folder/'known-check.json').write_text(json.dumps(marked,indent=2))
    badge='參照圖自比，排除於成效統計' if row['is_reference'] else '資料夾標籤：'+('良品 OK' if row['label']=='OK' else '不良品 NG')
    warning='<p class="notice">部分區域對齊品質不足，候選與未標記區域都需要人工確認。</p>' if r['alignment_warning'] else ''
    known_text=f'<p>暫定視覺標註檢查：{sum(bool(m["matched_ids"]) for m in marked)} / {len(marked)} 個區域有候選；這不是完整螺絲真值。</p>' if marked else ''
    body=navigation+f'<h1>{esc(title)}</h1><p>{esc(badge)} · 門檻 0.13 · V10 · '+('鏡像方向已校正' if r['mirrored_input'] else '一般方向對齊')+f'</p>{warning}<div class="stats"><div class="stat">全部候選<b>{r["proposal_count"]}</b></div><div class="stat">優先紅框<b>{r["high_count"]}</b></div><div class="stat">黃色複核<b>{r["review_count"]}</b></div><div class="stat">線材提示（未刪除）<b>{r["wire_review_count"]}</b></div></div>{known_text}'
    body+='<p>下列三圖使用相同方向與座標。紅框是規則優先候選，並非 AI 或人工確認螺絲；黃色框與無框影像也需查看。</p><div class="triple"><div><h3>唯一正常參照圖</h3><a href="reference.png"><img src="reference.png"></a></div><div><h3>待測圖（已對齊）</h3><a href="aligned.png"><img src="aligned.png"></a></div><div><h3>全部候選標記</h3><a href="aligned_overlay.png"><img src="aligned_overlay.png"></a></div></div>'
    body+=f'<details><summary>來源與完整機器結果</summary><p>參照：{esc(row["reference"])}</p><p>待測：{esc(row["path"])}</p><p><a href="source.png">原始方向預覽</a> · <a href="all_overlay.png">原始方向候選標記</a> · <a href="difference.png">差分圖</a> · <a href="result.json">完整結果 JSON</a></p></details>'
    body+='<h2>逐候選參照／待測對照</h2><div class="controls"><label>顯示 <select id="filter"><option value="all">全部候選</option><option value="high">優先紅框</option><option value="review">黃色複核</option><option value="wire">線材提示</option></select></label><label><input id="boxes" type="checkbox" checked>顯示框線</label></div>'
    if not r['candidates']:body+='<p class="notice">沒有候選。仍需人工查看整張照片，不能直接判定良品。</p>'
    for c in r['candidates']:
        x,y,w,h=(c[k] for k in ('x','y','w','h'));side=max(96,w+48,h+48)
        x0=max(0,min(width-side,x+w//2-side//2));y0=max(0,min(height-side,y+h//2-side//2))
        cw=min(side,width-x0);ch=min(side,height-y0)
        color='#e1263b' if c['priority']=='high' else '#df9e00'
        label='優先紅框' if c['priority']=='high' else '黃色複核'
        classification=c['classification'];ai=LABELS.get(classification.get('label'),classification.get('label','不確定'))
        ai_text='AI 建議：'+ai+'（不作自動判定）' if classification.get('status')=='shadow' else 'AI 無有效建議：'+str(classification.get('error',classification.get('status')))
        margin=classification.get('screw_margin');margin_text=f'；螺絲與最高其他類別分數差 {margin:.4f}（不是機率）' if margin is not None else ''
        body+=f'<article data-priority="{c["priority"]}" data-wire="{str(bool(c.get("wire_review"))).lower()}" id="candidate-{c["id"]}"><h3>候選 #{c["id"]} · {label}</h3><p>{esc(ai_text+margin_text)}</p><p>{esc("；".join(c["reasons"]))}</p><div class="pair">'
        for name,filename in [('參照圖：相同位置','reference.png'),('待測圖：已對齊','aligned.png')]:
            body+=f'<div><b>{name}</b><svg viewBox="{x0} {y0} {cw} {ch}" xmlns="http://www.w3.org/2000/svg"><image href="{filename}" width="{width}" height="{height}"/><rect class="candidate-rect" x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="1"/></svg></div>'
        body+=f'</div><p class="muted">對齊座標 ({x}, {y})；{w} × {h} 像素；差分強度 {c["score"]}</p></article>'
    body+=f'<details><summary>另列的既有結構變化：{r["structure_change_count"]} 個</summary><p>既有差分規則另列，不代表已人工確認正常。線材提示不會移入這裡，仍保留在上方候選。</p>'
    for c in r['structure_changes']:
        body+=f'<div class="panel"><b>結構變化 #{c["id"]}</b><div class="pair"><img loading="lazy" src="structure_ref_{c["id"]}.png"><img loading="lazy" src="structure_target_{c["id"]}.png"></div></div>'
    body+='</details>'
    script="document.getElementById('filter').onchange=e=>{for(const c of document.querySelectorAll('article'))c.hidden=!(e.target.value==='all'||(e.target.value==='wire'?c.dataset.wire==='true':c.dataset.priority===e.target.value))};document.getElementById('boxes').onchange=e=>{for(const r of document.querySelectorAll('.candidate-rect'))r.style.display=e.target.checked?'':'none'};"
    (folder/'report.html').write_text(page(title,body,script),encoding='utf-8')

def metrics(rows):
    usable=[r for r in rows if r['success']]
    return dict(images=len(rows),success=len(usable),failed=len(rows)-len(usable),
        candidates=sum(r['count'] for r in usable),high=sum(r['high'] for r in usable),
        zero=sum(r['count']==0 for r in usable),positive=sum(r['count']>0 for r in usable),
        high_positive=sum(r['high']>0 for r in usable),
        median=median([r['count'] for r in usable]) if usable else None,
        maximum=max([r['count'] for r in usable],default=None),wire=sum(r['wire'] for r in usable),
        alignment_warning=sum(r['alignment_warning'] for r in usable),mirrored=sum(r['mirrored'] for r in usable),
        ai_screw=sum(r['ai_screw'] for r in usable),ai_uncertain=sum(r['ai_uncertain'] for r in usable),
        ai_non_screw=sum(r['ai_non_screw'] for r in usable),ai_error=sum(r['ai_error'] for r in usable))

def result_table(rows):
    head='<div class="controls"><input id="search" type="search" placeholder="搜尋機種、檔名或標籤"></div><table id="results"><thead><tr><th>機種／標籤／檔名</th><th>候選</th><th>優先紅框</th><th>線材提示</th><th>AI 螺絲／不確定／其他</th><th>狀態</th></tr></thead><tbody>'
    for r in rows:
        link='photos/'+r['sha256']+'/report.html'
        status='參照自比' if r['is_reference'] else '待人工複核'
        if r['previously_deferred']:status+='；前次暫放案例'
        if not r['success']:status='分析失敗：'+r['error']
        elif r['alignment_warning']:status+='；對齊品質提醒'
        vals=[r.get('count','—'),r.get('high','—'),r.get('wire','—'),f'{r["ai_screw"]} / {r["ai_uncertain"]} / {r["ai_non_screw"]}' if r['success'] else '—']
        head+=f'<tr data-search="{esc(r["relative"].lower())}"><td><a href="{link}">{esc(r["relative"])}</a></td>'+''.join('<td>'+esc(v)+'</td>' for v in vals)+f'<td>{esc(status)}</td></tr>'
    return head+'</tbody></table>'

FILTER="const q=document.getElementById('search');if(q)q.oninput=e=>{for(const r of document.querySelectorAll('#results tbody tr'))r.hidden=!r.dataset.search.includes(e.target.value.trim().toLowerCase())};"

def main():
    partial='--partial' in sys.argv
    plan=read(OUT/'plan.json')
    rows=[read(p) for p in (OUT/'photos').glob('*/evaluation.json')]
    rows.sort(key=lambda r:r['relative'])
    complete=len(rows)==len(plan['items']) and (OUT/'results.json').exists()
    if not partial:assert complete,'Wait for the full batch before final report'
    known=known_annotations()
    for r in rows:photo_page(r,known)
    mainrows=[r for r in rows if not r['is_reference']]
    groups={}
    for machine in sorted(plan['references']):
        for label in ['OK','NG']:
            rr=[r for r in mainrows if r['machine']==machine and r['label']==label]
            groups[machine+'/'+label]=metrics(rr)
    summary=dict(complete=complete,processed=len(rows),expected=len(plan['items']),
                 references=sum(r['is_reference'] for r in rows),all=metrics(rows),
                 non_reference=metrics(mainrows),good=metrics([r for r in mainrows if r['label']=='OK']),
                 bad=metrics([r for r in mainrows if r['label']=='NG']),groups=groups)
    known_results=[]
    for r in rows:
        if r['success'] and r['sha256'] in known:
            marked=read(OUT/'photos'/r['sha256']/'known-check.json')
            known_results.append(dict(relative=r['relative'],checks=marked))
    summary['provisional_visual_checks']=known_results
    acquisition_groups={}
    for label in ['PNG / 一般方向','TIFF / 一般方向','TIFF / 鏡像校正']:
        selected=[r for r in mainrows if r['label']=='NG' and r['success'] and
                  ('PNG / 一般方向' if Path(r['path']).suffix.lower()=='.png' else
                   'TIFF / 鏡像校正' if r['mirrored'] else 'TIFF / 一般方向')==label]
        acquisition_groups[label]=metrics(selected)
    summary['ng_acquisition_groups']=acquisition_groups
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    nav='<nav><a href="index.html">總報告</a><a href="good.html">良品報告</a><a href="bad.html">不良品報告</a><a href="plan.json">固定設定與圖資清單</a><a href="summary.json">統計 JSON</a></nav>'
    status=f'<p class="notice">'+('完整批次已完成' if complete else '批次進行中，以下為暫時結果')+f'：{len(rows)} / {len(plan["items"])} 張。參照圖自比另列，失敗不當成零候選。</p>'
    intro='<p>V10 · 固定門檻 0.13 · 每個機種只有一張參照圖 · CLIP 為建議模式，不刪候選。線材提示只調整優先級，全部候選仍需人工確認。</p>'
    limitation='<p class="notice">資料夾 OK／NG 是圖像標籤，沒有完整螺絲位置真值。「NG 有候選」可能只是線材或固定零件誤報，不能當成螺絲召回率；「沒有紅框」也不代表良品。本批案例曾用於調教，這是固定版本重跑，並非全新獨立驗證集。</p>'
    columns='<tr><th>機種／標籤</th><th>測試張數</th><th>失敗</th><th>零候選</th><th>有候選</th><th>候選總數</th><th>紅框數／有紅框照片</th><th>每張中位數／最大</th><th>對齊提醒</th></tr>'
    group_table='<table>'+columns
    for group,m in groups.items():
        group_table+=f'<tr><td>{group}</td>'+''.join('<td>'+esc(value)+'</td>' for value in [m['images'],m['failed'],m['zero'],m['positive'],m['candidates'],f'{m["high"]} / {m["high_positive"]} 張',f'{m["median"]} / {m["maximum"]}',m['alignment_warning']])+'</tr>'
    group_table+='</table>'
    references='<table><tr><th>機種</th><th>唯一參照圖</th></tr>'+''.join(f'<tr><td>{esc(model)}</td><td>{esc(Path(r["path"]).name)}</td></tr>' for model,r in sorted(plan['references'].items()))+'</table>'
    good,bad=summary['good'],summary['bad']
    rate=f'{100*good["positive"]/good["success"]:.1f}%' if good['success'] else '—'
    acceptance=f'<h2>定案前應看的結果</h2><p>非參照良品：{good["positive"]} / {good["success"]} 張出現候選（候選警示比例 {rate}），候選總數 {good["candidates"]}；其中 {good["high_positive"]} 張有優先紅框，共 {good["high"]} 個紅框。這是在良品標籤假設下的誤報負擔，黃色候選不等於已判為不良。</p><p>不良品：{bad["positive"]} / {bad["success"]} 張有候選、{bad["zero"]} 張零候選、{bad["failed"]} 張失敗。此處只表示圖像有警示，尚未確認候選是否落在真正螺絲上。</p><p>MPT10、MPT12、KPH33 沒有 NG；MPT11 唯一 OK 已作參照，沒有獨立 OK 驗證。這批資料不足以確認每個機種同時具有低誤報與低漏檢。建議將本報告作為人工候選輔助版的驗收材料，不把它當成自動 OK／NG 定案證據。</p>'
    body=nav+'<h1>V10 圖資全批檢測總報告</h1>'+status+intro+limitation+group_table+acceptance+'<h2>固定的單張參照</h2>'+references
    body+='<p>MPT12 沿用已比較過的 cnd64409qy.tiff。此前暫放的 17_14_35_98.tiff 已納入本次 47 張 NG，於逐圖表另行標示。所有原始圖、站台設定與人工複判紀錄均不由本批寫入。</p>'
    prior_reference=next((r for r in rows if r['machine']=='MPT12' and Path(r['path']).name=='cnd64304g5.tiff' and r['success']),None)
    if prior_reference:
        body+=f'<p>MPT12 與前次「共同 48 張／56 個候選／6 個紅框」的差別：本次另將舊參照 cnd64304g5.tiff 作為待測，增加 {prior_reference["count"]} 個候選、{prior_reference["high"]} 個優先紅框；新參照本身仍另列自比。</p>'
    body+=f'<h2>AI 建議概況（非自動判定）</h2><p>疑似螺絲 {summary["non_reference"]["ai_screw"]}；不確定 {summary["non_reference"]["ai_uncertain"]}；其他類別建議 {summary["non_reference"]["ai_non_screw"]}；分類錯誤 {summary["non_reference"]["ai_error"]}。CLIP 分數不是螺絲機率，其他類別候選仍保留。</p>'
    body+='<h2>NG 依檔案與方向校正分組</h2><p>用來觀察不同取像資料的候選負擔，並非螺絲檢出率。</p><table><tr><th>組別</th><th>照片</th><th>候選總數</th><th>每張中位數／最大</th><th>對齊提醒</th></tr>'
    for label,m in acquisition_groups.items():
        body+=f'<tr><td>{label}</td><td>{m["images"]}</td><td>{m["candidates"]}</td><td>{m["median"]} / {m["maximum"]}</td><td>{m["alignment_warning"]}</td></tr>'
    body+='</table>'
    body+='<h2>全部照片</h2>'+result_table(rows)
    (OUT/'index.html').write_text(page('V10 全批檢測總報告',body,FILTER),encoding='utf-8')
    for label,filename,title in [('OK','good.html','良品檢測報告'),('NG','bad.html','不良品檢測報告')]:
        selected=[r for r in rows if r['label']==label]
        text=nav+f'<h1>{title}</h1>'+status+intro+limitation
        if label=='OK':text+='<p>參照自比列在表中，但不計入誤報統計。點照片可查看參照、待測、所有框及逐候選對照。</p>'
        else:text+='<p>本批 NG 都屬於 MPT11。請逐張確認是否標到實際螺絲；候選總數不是螺絲數量。</p>'
        text+=result_table(selected)
        (OUT/filename).write_text(page(title,text,FILTER),encoding='utf-8')
    print(json.dumps(dict(complete=complete,processed=len(rows),good=good,bad=bad),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
