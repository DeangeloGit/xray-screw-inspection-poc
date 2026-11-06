"""Full-corpus report for a frozen answered batch, following full_paired_report layout.

Answers use the existing central-overlap matching rule from the prior MPT10 audit.
All candidates (including exclusions), zero-candidate photos and self comparisons
are retained. No detector, model, source image or manual record is modified.
"""
import argparse
from collections import Counter
import hashlib
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
from urllib.parse import unquote
import cv2
import numpy as np
from PIL import Image, ImageDraw
from result_columns import columns as outcome_columns,STYLE as OUTCOME_STYLE

TYPES={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}
METHODS={'r3':'原 r3','recovery':'補抓版（過濾前）','pilot':'本次試驗版'}
STYLE='''body{font:17px/1.65 "Microsoft JhengHei",sans-serif;color:#183847;background:#f2f5f7;margin:0}main{max-width:1200px;margin:auto;padding:28px}nav{display:flex;gap:20px;flex-wrap:wrap}a{color:#12628b}table{border-collapse:collapse;background:white;width:100%;margin:18px 0}th,td{padding:10px;border:1px solid #ced9df;text-align:left}img{max-width:100%;height:auto}article,details,.box{background:white;padding:18px;margin:18px 0;border:1px solid #d4dfe4;border-radius:8px}.pair{max-width:800px}.muted{color:#526977}.warn{background:#fff3d5;padding:15px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}summary{cursor:pointer;font-weight:bold}h1,h2,h3{line-height:1.35}code{overflow-wrap:anywhere}@media(max-width:700px){main{padding:12px}.grid{grid-template-columns:1fr}table{font-size:13px}}'''
NAV='<nav><a href="index.html">完整結果</a><a href="machine-MPT10.html">MPT10</a><a href="answers.html">全部答案核對</a><a href="comparison.html">附加：版本比較</a><a href="provenance.html">圖資與核對證據</a></nav>'
STYLE+=OUTCOME_STYLE
esc=lambda s:html.escape(str(s))


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def hull(p):return cv2.convexHull(np.asarray(p,np.float32)).reshape(-1,2)
def geom(c):return tuple(c[k] for k in ('x','y','w','h'))


def native(c,r,flow):
    # Invert the same registration/local-flow transform used by source_points.
    x,y,w,h=geom(c)
    p=np.float32([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
    # Use the production coordinate converter, without importing detector at module load.
    from detector import source_points
    reg=dict(matrix=np.asarray(r['matrix']),rotation=r['rotation_ccw']//90,mirrored=r['mirrored_input'],target_scale=r['preview_scale'])
    padded=np.float32([[x-5,y-5],[x+w+5,y-5],[x+w+5,y+h+5],[x-5,y+h+5]])
    assert np.max(abs(source_points(padded,reg,flow,r['source_shape'])-np.asarray(c['source_polygon'])))<.08
    canonical=c.get('classification',{}).get('canonical_object',{}).get('box')
    if canonical:
        x,y,w,h=canonical;p=np.float32([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
    return source_points(p,reg,flow,r['source_shape'])


def matches(poly,marks):
    cp=hull(poly);center=tuple(float(v) for v in cp.mean(axis=0));yes=[];edge=[]
    for m in marks:
        ap=hull(m['polygon']);ac=np.float32(m['center'])
        inter,_=cv2.intersectConvexConvex(ap,cp)
        if inter<=0:continue
        inner=hull(ac+(ap-ac)*.8)
        central=cv2.pointPolygonTest(inner,center,False)>=0 or cv2.pointPolygonTest(cp,tuple(float(v) for v in ac),False)>=0
        (yes if central else edge).append(m['id'])
    assert len(yes)<=1,(yes,poly)
    return yes,edge


def table(head,rows):
    return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def grouped(items):
    groups=[]
    for c in sorted(items,key=lambda c:(c['box'][1],c['box'][0],c['key'])):
        x,y,w,h=c['box'];center=(x+w/2,y+h/2)
        group=next((g for g in groups if math.dist(center,g[0]['center'])<=45),None)
        c['center']=center
        if group is None:groups.append([c])
        else:group.append(c)
    return sorted(groups,key=lambda g:-len(g))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    out=args.output.resolve();root=Path(__file__).resolve().parents[2]
    import os,sys
    os.environ['XRAY_WORKSPACE']=str(out/'report-runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');sys.path.insert(0,str(root))
    plan=read(out/'plan.json');assert read(out/'run-complete.json')['complete']
    meta=read(out/'report-meta.json') if (out/'report-meta.json').exists() else {}
    feedback=read(out/'manual-feedback.json') if (out/'manual-feedback.json').exists() else {}
    METHODS.update(meta.get('methods',{}))
    expected_answers=meta.get('expected_answers',100)
    answers=read(out/'answers.json');provenance=read(out/'provenance.json')
    report=out/'report';report.mkdir(exist_ok=True);images=report/'images';images.mkdir(exist_ok=True)
    def page(name,title,body):
        (report/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+STYLE+'</style><main>'+NAV+'<h1>'+esc(title)+'</h1>'+body+'</main></html>',encoding='utf-8')
    def preview(source,name):
        im=Image.open(source).convert('RGB');im.thumbnail((1400,1400));im.save(images/name,quality=90)
        return 'images/'+name
    allcases=[];rows=[];markrows=[]
    for item in plan['items']:
        key=item['key'];marks=answers.get(key,{}).get('marks',[]);isref=key=='golden'
        results={method:read(out/'runs'/method/key/'result.json') for method in METHODS}
        for method in METHODS:
            f=out/'runs'/method/key
            assert sha(f/'result.json')==read(f/'complete.json')['result_sha256']
        r=results['pilot'];folder=out/'runs'/'pilot'/key
        ref=Image.open(folder/'reference.png').convert('RGB');target=Image.open(folder/'aligned.png').convert('RGB')
        flow=np.zeros((ref.height,ref.width,2),np.float32)
        for region in r['local_alignment']:
            x,y,X,Y=region['bbox'];flow[y:Y,x:X]=[region['dx'],region['dy']]
        flow=cv2.GaussianBlur(flow,(0,0),12)
        maps={method:{geom(c):c for c in z['candidates']+z['filtered_candidates']} for method,z in results.items()}
        assert all(len(maps[m])==len(results[m]['candidates'])+len(results[m]['filtered_candidates']) for m in METHODS)
        assert set(maps['recovery'])<=set(maps['pilot'])
        assert set(maps['r3'])<=set(maps['pilot'])
        for method in METHODS:
            assert results[method]['matrix']==r['matrix'] and results[method]['local_alignment']==r['local_alignment']
        cases=[]
        for box,c in sorted(maps['pilot'].items(),key=lambda z:z[1]['id']):
            poly=native(c,r,flow);matched,edge=matches(poly,marks)
            keeps={method:box in maps[method] and maps[method][box]['classification']['filter_recommendation']=='keep' for method in METHODS}
            method_matches={method:matches(native(maps[method][box],results[method],flow),marks) if box in maps[method] else ([],[]) for method in METHODS}
            rules=c['classification'].get('overkill_pilot',{}).get('rules',[])
            rules=rules+c['classification'].get('r4_experiment',{}).get('rules',[])
            evidence=c['classification']['paired_evidence']
            paired_keep=evidence['target']['label']=='screw' and evidence['reference']['label']!='screw'
            assert keeps['pilot']==(paired_keep and not rules),(key,c['id'])
            category=next((cat for rule,cat in [('wire','wire'),('r4_wire_motion','wire'),('border','edge'),('corner','edge'),('component','component'),('r4_part_boundary','edge' if max(c['w'],c['h'])<=9 else 'component'),('r4_weak_object_extent','component')] if rule in rules),'unknown')
            z=dict(key=f'{key}-{c["id"]}',photo=key,id=c['id'],box=list(box),native=poly.tolist(),answers=matched,edge_answers=edge,keep=keeps,rules=rules,category=category,classification_source='規則自動推測' if category!='unknown' else '待確認（未人工分類）',is_reference=isref)
            z['paired_evidence']=evidence;z['decision_reason']=c['classification']['decision_reason']
            z['method_matches']=method_matches;z['canonical_object']=c['classification'].get('canonical_object')
            z['correspondence_experiment']=c['classification'].get('correspondence_experiment')
            z['manual_feedback']=feedback.get(z['key'])
            x,y,w,h=box;side=max(120,w+48,h+48);x0=max(0,min(ref.width-side,x+w/2-side/2));y0=max(0,min(ref.height-side,y+h/2-side/2));cropbox=(int(x0),int(y0),int(x0+side),int(y0+side))
            pair=Image.new('RGB',(800,400),'white')
            for j,im in enumerate((ref,target)):
                dx,dy=(z['correspondence_experiment'] or {}).get('reference_offset',[0,0]) if j==0 else (0,0)
                actualcrop=(cropbox[0]+dx,cropbox[1]+dy,cropbox[2]+dx,cropbox[3]+dy)
                crop=im.crop(actualcrop);ImageDraw.Draw(crop).rectangle((x-actualcrop[0],y-actualcrop[1],x+w-actualcrop[0],y+h-actualcrop[1]),outline='#eb2346',width=1)
                if z['canonical_object']:
                    cx,cy,cw,ch=z['canonical_object']['box'];ImageDraw.Draw(crop).rectangle((cx-cropbox[0],cy-cropbox[1],cx+cw-cropbox[0],cy+ch-cropbox[1]),outline='#00a5dd',width=1)
                pair.paste(crop.resize((400,400)),(j*400,0))
            pair.save(images/f'{z["key"]}.jpg',quality=86)
            cases.append(z)
        allcases.extend(cases)
        metrics={}
        for method in METHODS:
            kept=[z for z in cases if z['keep'][method]]
            hits=sorted({i for z in kept for i in z['method_matches'][method][0]})
            metrics[method]=dict(kept=len(kept),excluded=len(maps[method])-len(kept),answer_hits=hits,unmatched=sum(not z['method_matches'][method][0] for z in kept),edge_only=sum(bool(z['method_matches'][method][1]) and not z['method_matches'][method][0] for z in kept))
        lost=[z['key'] for z in cases if z['keep']['r3'] and not z['keep']['pilot']]
        removed=[z for z in cases if z['keep']['recovery'] and not z['keep']['pilot']]
        row=dict(key=key,name=Path(item['path']).name,machine='MPT10',label='參照自比' if isref else 'NG',is_reference=isref,answers=len(marks),candidates=len(cases),metrics=metrics,lost_r3=lost,removed=[z['key'] for z in removed],removed_answer_hits=[z['key'] for z in removed if z['answers']],alignment_warning=r['alignment_warning'],structure_changes=r['structure_change_count'])
        rows.append(row)
        original=Image.open(item['path']).convert('RGB')
        for m in marks:
            markrows.append(dict(photo=key,**m,methods={method:[z['key'] for z in cases if m['id'] in z['method_matches'][method][0] and z['keep'][method]] for method in METHODS}))
            mx,my=m['center'];span=max(180,int(np.ptp(np.asarray(m['polygon']),axis=0).max())+80)
            x0=max(0,min(original.width-span,int(mx-span/2)));y0=max(0,min(original.height-span,int(my-span/2)))
            crop=original.crop((x0,y0,x0+span,y0+span));draw=ImageDraw.Draw(crop)
            def polyline(poly,color):
                pts=[(x-x0,y-y0) for x,y in poly];draw.line(pts+[pts[0]],fill=color,width=2)
            polyline(m['polygon'],'#ec254d')
            for z in cases:
                if m['id'] in z['answers'] or m['id'] in z['edge_answers']:
                    polyline(z['native'],'#0088dd' if z['keep']['pilot'] else '#d49c00')
            crop.resize((300,300)).save(images/f'{key}-mark-{m["id"]}.jpg',quality=92)
        preview(folder/'all_overlay.png',f'{key}-overlay.jpg');preview(folder/'reference.png',f'{key}-reference.jpg')
        preview(item['path'],f'{key}-source.jpg')
        if item['answer']:preview(item['answer'],f'{key}-answer.jpg')
        print('REPORT',key,len(cases),metrics,flush=True)
    totals={m:dict(kept=sum(r['metrics'][m]['kept'] for r in rows if not r['is_reference']),answer_hits=sum(len(r['metrics'][m]['answer_hits']) for r in rows if not r['is_reference']),unmatched=sum(r['metrics'][m]['unmatched'] for r in rows if not r['is_reference'])) for m in METHODS}
    summary=dict(photos=len(rows),test_photos=sum(not r['is_reference'] for r in rows),reference_self_comparisons=sum(r['is_reference'] for r in rows),answer_marks=len(markrows),candidates=len(allcases),totals=totals,lost_r3_candidates=[k for r in rows for k in r['lost_r3']],lost_r3_answers=[f'{m["photo"]}-{m["id"]}' for m in markrows if m['methods']['r3'] and not m['methods']['pilot']],lost_recovery_answers=[f'{m["photo"]}-{m["id"]}' for m in markrows if m['methods']['recovery'] and not m['methods']['pilot']],removed_candidates=[k for r in rows for k in r['removed']],removed_answer_candidates=[k for r in rows for k in r['removed_answer_hits']],independent_new_scans=0)
    save(out/'summary.json',summary);save(out/'rows.json',rows);save(out/'cases.json',allcases);save(out/'answer-matches.json',markrows)
    def case_card(z):
        label='保留警報' if z['keep']['pilot'] else '排除'
        ans='答案 '+','.join(map(str,z['answers'])) if z['answers'] else ('僅擦到答案邊緣，待確認' if z['edge_answers'] else '未對到答案')
        pairlabels='；'.join(('參照' if side=='reference' else '待測')+'：'+('像螺絲' if z['paired_evidence'][side]['label']=='screw' else '不像螺絲') for side in ('reference','target'))
        if z.get('canonical_object'):
            obj=z['canonical_object'];pairlabels+='。紅框：原候選；藍框：實際判斷物件 '+str(obj['box'])+'；物件 '+obj['object_id']+'；已重新推論'
        if z.get('correspondence_experiment'):
            meta=z['correspondence_experiment'];offset=meta.get('reference_offset',[0,0])
            if offset!=[0,0]:pairlabels+='。左圖已依參照物件位移 '+str(offset)+' 重新取圖，並非原同位置空白區'
            if meta.get('recheck')=='complete_contour':pairlabels+='。完整輪廓及外圍 4／8／12 像素皆重新推論'
            if meta.get('low_confidence'):pairlabels+='。低對比參照：外圍 20／32 像素重看；邊界分數僅供人工複核'
            if meta.get('recheck')=='shared_contrast_reference':pairlabels+='。兩圖共用明暗尺度；外圍 4／8／12 像素重看，參照取中位分數、待測取最低分數'
        if z.get('manual_feedback'):pairlabels+='。使用者回饋：'+z['manual_feedback']['text']
        return f'<article id="case-{z["key"]}"><h3>{esc(z["photo"])}／候選 #{z["id"]}：{label}</h3><p>{TYPES[z["category"]]} · {z["classification_source"]} · {ans}</p><p><a href="photo-{z["photo"]}.html#case-{z["key"]}">查看照片</a> · <a href="category-{z["category"]}.html#case-{z["key"]}">查看同類案例</a></p><p>左：參照圖　右：待測圖</p><img class="pair" src="images/{z["key"]}.jpg" alt="{z["key"]} 參照與待測候選對照"><p>{pairlabels}。{esc(z["decision_reason"])}</p><p>自動過濾規則：{esc(', '.join(z['rules']) or '無')}</p></article>'
    def photo_table(rs):
        return table(['照片','本次保留候選框','排除候選框','答案命中','答案框外警報','本張分類'],[[f'<a href="photo-{r["key"]}.html">{esc(r["name"])}</a>',r['metrics']['pilot']['kept'],r['metrics']['pilot']['excluded'],f'{len(r["metrics"]["pilot"]["answer_hits"])}/{r["answers"]}' if not r['is_reference'] else '不適用',r['metrics']['pilot']['unmatched'] if not r['is_reference'] else '不適用','待確認／詳見照片'] for r in rs])
    caveat='<p class="warn">本批為既有影像補齊答案後的回歸驗證，獨立新影像為 0 張。候選框數不是螺絲顆數；未對到答案的警報依提供答案視為疑似誤報，未另經人工逐框確認。沒有一般良品圖，Golden 自比不計入良品效能。</p>'
    if feedback:
        confirmed=[z for z in allcases if (z.get('manual_feedback') or {}).get('label')=='screw']
        if confirmed and not meta.get('reviewed_scoring'):caveat+='<p class="box">另有使用者新增確認 '+str(len(confirmed))+' 處掉落物件，本輪保留 '+str(sum(z['keep']['pilot'] for z in confirmed))+' 處；與原 100 處答案分開記錄，不改原始答案與前後比較口徑。'+ '、'.join(f'<a href="photo-{z["photo"]}.html#case-{z["key"]}">{z["key"]}</a>' for z in confirmed)+'</p>'
    if meta.get('reviewed_scoring'):caveat+='<p class="box">本頁採校正後 101 處答案；包含使用者確認的兩處螺絲，其中線材案例原已在100處內，不重複加計。原始55／100與校正增加分開列於附加頁，校正不是模型新增命中。</p>'
    stats=totals['pilot']
    page('index.html',meta.get('title','4r 全圖資檢測結果｜2026-11-06'),caveat+f'<p>固定 47 張螺絲＋65 張正常範例、DINO 雙圖。{esc(meta.get("policy_description","沿用既有過殺試驗規則。"))}本次涵蓋 10 張不良品、1 張參照自比、{expected_answers} 處答案；答案命中 {stats["answer_hits"]}/{expected_answers}，保留 {stats["kept"]} 個候選框，答案框外警報 {stats["unmatched"]} 個。</p><h2>良品完整結果</h2><p>一般良品 0 張；本批未提供。參照自比獨立列於下方。</p><h2>不良品完整結果</h2>'+photo_table([r for r in rows if not r['is_reference']])+'<h2>依機種查看</h2><p><a href="machine-MPT10.html">MPT10 → 誤報類型 → 相近位置</a></p><p>本批無 MPT12、KPH33、MPT11 圖資，不建立虛構案例。</p><h2>參照圖自比</h2>'+photo_table([r for r in rows if r['is_reference']]))
    catcounts=Counter(z['category'] for z in allcases)
    cat_table=table(['類型','全部候選框','人工確認分類'],[[f'<a href="category-{k}.html">{v}</a>',catcounts[k],0] for k,v in TYPES.items()])
    page('machine-MPT10.html','MPT10｜全圖資',caveat+cat_table+photo_table(rows))
    for category,title in TYPES.items():
        selected=[z for z in allcases if z['category']==category]
        body=f'<p><a href="machine-MPT10.html">返回此機種</a></p><p>共 {len(selected)} 個候選框；類型為自動推測或待確認，人工確認分類 0。依參照圖座標、中心距離 45 像素內分組。</p>'
        for n,group in enumerate(grouped(selected),1):
            body+=f'<section><h2>相近位置 {n}｜{len(group)} 個候選</h2>'+outcome_columns(group,case_card,lambda z:z['keep']['pilot'],compact=True)
            body+='</section>'
        if not selected:body+='<p>0 個案例。</p>'
        page(f'category-{category}.html',f'MPT10 → {title} → 相近位置',body)
    for r in rows:
        key=r['key'];cs=[z for z in allcases if z['photo']==key];cats=Counter(z['category'] for z in cs)
        body='<p><a href="machine-MPT10.html">返回此機種</a> · <a href="category-unknown.html">查看同類案例</a></p><p>本張分類：'+esc('、'.join(f'{TYPES[k]} {cats[k]}' for k in TYPES))+'</p>'
        body+=f'<p>{r["label"]}；保留 {r["metrics"]["pilot"]["kept"]} 框、排除 {r["metrics"]["pilot"]["excluded"]} 框。對位提醒：{r["alignment_warning"]}；另有結構變化 {r["structure_changes"]} 處（不當成螺絲）。</p>'
        body+=f'<div class="grid"><div>參照圖<img src="images/{key}-reference.jpg"></div><div>待測圖與本次保留框<img src="images/{key}-overlay.jpg"></div></div>'
        if not r['is_reference']:
            body+=f'<details><summary>原始待測圖與提供答案</summary><div class="grid"><img src="images/{key}-source.jpg"><img src="images/{key}-answer.jpg"></div></details><p><a href="answers.html#answer-{key}">查看本張全部答案核對</a></p>'
        body+='<h2>全部保留與排除候選</h2>'+outcome_columns(cs,case_card,lambda z:z['keep']['pilot'])
        if r['structure_changes']:
            body+='<details><summary>其他結構變化完整紀錄</summary><pre>'+esc(json.dumps(read(out/'runs'/'pilot'/key/'result.json')['structure_changes'],ensure_ascii=False,indent=2))+'</pre></details>'
        page(f'photo-{key}.html',f'MPT10／{r["name"]}',body)
    body='<p>以提供的 PNG 紅框為本輪答案；每張 10 處，共 100 處。先以未標註像素配準，再用原圖座標核對各版本實際判斷的物件框（未使用物件定位的版本沿用緊候選框）。候選中心需在縮至 80% 的答案框內，或答案中心落在候選框內，且兩框重疊；僅擦邊不算命中。此規則沿用前輪答案核對，不因版本結果調整。</p>'
    body=meta.get('answer_intro',body)
    for r in rows:
        if r['is_reference']:continue
        key=r['key'];ms=[m for m in markrows if m['photo']==key]
        body+=f'<section id="answer-{key}"><h2>{key}｜{len(ms)} 處答案</h2><a href="photo-{key}.html">返回照片</a><img src="images/{key}-answer.jpg">'
        body+=table(['答案編號','本次結果','命中候選'],[[m['id'],'命中' if m['methods']['pilot'] else '未命中','、'.join(f'<a href="photo-{key}.html#case-{k}">{k}</a>' for k in m['methods']['pilot']) or '無'] for m in ms])
        body+='<details><summary>展開全部答案局部圖（紅：答案；藍：保留；黃：排除）</summary><div class="grid">'+''.join(f'<article><h3>答案 {m["id"]}：'+('命中' if m['methods']['pilot'] else '未命中')+f'</h3><img src="images/{key}-mark-{m["id"]}.jpg"></article>' for m in ms)+'</div></details></section>'
    page('answers.html',f'全部 {expected_answers} 處答案核對',body)
    body=caveat+table(['版本',f'答案命中／{expected_answers}','保留候選框','答案框外警報'],[[METHODS[m],totals[m]['answer_hits'],totals[m]['kept'],totals[m]['unmatched']] for m in METHODS])
    body+=f'<p>原 r3 命中答案損失：{len(summary["lost_r3_answers"])}；原 r3 保留候選轉為排除：{len(summary["lost_r3_candidates"])}。過殺過濾移除 {len(summary["removed_candidates"])} 框，其中對到答案 {len(summary["removed_answer_candidates"])} 框；過濾前命中、過濾後漏掉的答案 {len(summary["lost_recovery_answers"])} 處。</p>'
    body+='<p>'+esc(meta.get('comparison_description','補抓版使用同一套固定試驗程式，只在隔離驗證程序中略過結構過濾；正式程式檔案與設定未修改。這個對照用來隔離過殺過濾的作用。'))+'</p>'
    body+=table(['照片',*[METHODS[m]+' 命中' for m in METHODS],*[METHODS[m]+' 框外警報' for m in METHODS]],[[r['key'],*[len(r['metrics'][m]['answer_hits']) for m in METHODS],*[r['metrics'][m]['unmatched'] for m in METHODS]] for r in rows if not r['is_reference']])
    body+='<h2>本輪轉為排除的全部候選</h2>'+''.join(case_card(z) for z in allcases if z['key'] in summary['removed_candidates'])
    page('comparison.html','附加｜版本與過殺比較',body)
    source=Path(plan['source']);inventory=[]
    for p in sorted(source.rglob('*')):
        if not p.is_file():continue
        relative=p.relative_to(source).as_posix();role='待測原圖' if relative.startswith('NG/') else '參照圖' if relative=='Golden.tiff' else ('原始 PNG 答案（保留追溯）' if meta.get('reviewed_scoring') else '本輪 PNG 答案') if relative.startswith('ANSWER_PNG/') else '歷史 TIFF 答案（輔助，不混用標註）'
        if relative.startswith('Answer/'):
            dest=preview(p,'legacy-'+p.stem+'.jpg');label=f'<a href="{dest}">{esc(relative)}</a>'
        else:label=esc(relative)
        inventory.append([label,role,sha(p)])
    answer_source_note='兩張舊 TIFF 答案各有 9 處；原始 PNG 每張 10 處。本輪採另存的校正答案，共101處，原始標註未改動；校正依據與前後座標見實驗附頁。' if meta.get('reviewed_scoring') else '兩張舊 TIFF 答案各有 9 處，本輪以新 PNG 的每張 10 處為準。'
    body=caveat+'<p>第 128 張雖檔案 SHA 不同，但與舊圖逆時針旋轉 90 度後逐像素相同；其餘 9 張 SHA 相同。全部 23 個來源檔案列於下方，均以唯讀方式使用。'+answer_source_note+'</p>'
    body+=table(['照片','配準內點','95% 誤差（縮圖像素）','未標註像素相關性'],[[key,a['registration']['inliers'],round(a['registration']['p95_error'],3),round(a['registration']['correlation'],4)] for key,a in answers.items()])
    body+=table(['來源檔案','用途','SHA-256'],inventory)+'<p><a href="../summary.json">統計 JSON</a> · <a href="../plan.json">固定模型、程式與來源雜湊</a> · <a href="../cases.json">全部候選判斷</a> · <a href="../answer-matches.json">答案逐處匹配</a> · <a href="../verification.json">完整性核對</a></p>'
    page('provenance.html','圖資、答案與完整性證據',body)
    # Data-driven checks replace the old verifier's hard-coded 190/2793 corpus totals.
    assert len(allcases)==sum(r['candidates'] for r in rows)==sum(read(out/'runs'/'pilot'/r['key']/'result.json')['pre_ai_count'] for r in rows)
    assert len(markrows)==expected_answers and all(r['answers']==len(answers[r['key']]['marks']) for r in rows if not r['is_reference'])
    assert not summary['lost_r3_answers']
    if meta.get('protect_r3_candidates',True):assert not summary['lost_r3_candidates']
    if meta.get('protect_previous_answer_hits'):assert not summary['lost_recovery_answers']
    if meta.get('protect_unmatched'):assert totals['pilot']['unmatched']<=totals['recovery']['unmatched']
    assert all(sha(p)==h for p,h in plan['hashes'].items())
    save(out/'verification.json',dict(status='checking_links'))
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if 'id' in a:self.ids.append(a['id'])
            for k in ('href','src'):
                if k in a:self.links.append(a[k])
    parsed={}
    for p in report.glob('*.html'):
        v=Parser();v.feed(p.read_text(encoding='utf-8'));assert len(v.ids)==len(set(v.ids)),p;parsed[p.resolve()]=v
    link_count=0
    for p,v in parsed.items():
        for link in v.links:
            name,_,anchor=link.partition('#');dest=(p.parent/unquote(name)).resolve() if name else p
            assert dest.exists(),(p,link)
            if anchor:assert anchor in parsed[dest].ids,(p,link)
            link_count+=1
    for row in rows:
        p=report/f'photo-{row["key"]}.html'
        expected={'case-'+z['key'] for z in allcases if z['photo']==row['key']}
        assert expected=={s for s in parsed[p.resolve()].ids if s.startswith('case-')}
    for category in TYPES:
        expected={'case-'+z['key'] for z in allcases if z['category']==category}
        assert expected=={s for s in parsed[(report/f'category-{category}.html').resolve()].ids if s.startswith('case-')}
    for p in images.glob('*.jpg'):
        with Image.open(p) as im:im.verify()
    verification=dict(status='passed',photos=len(rows),candidates=len(allcases),answers=len(markrows),html_pages=len(parsed),links_checked=link_count,images_checked=len(list(images.glob('*.jpg'))),all_photo_and_category_candidates_covered=True,protected_hashes_unchanged=True,r3_candidates_and_answer_hits_preserved=not summary['lost_r3_candidates'],r3_answer_hits_preserved=not summary['lost_r3_answers'],previous_answer_hits_preserved=not summary['lost_recovery_answers'])
    verification['result_sha256']={str(p.relative_to(out)):sha(p) for p in (out/'runs').glob('*/*/result.json')}
    save(out/'verification.json',verification);print(json.dumps(summary,ensure_ascii=False,indent=2));print(verification)


if __name__=='__main__':main()
