"""Offline paired-reference pilot. Reads frozen detections; never activates a model."""
import sys,json,hashlib,math,os
from pathlib import Path
from collections import Counter
import numpy as np
import onnxruntime as ort
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.current_dataset_review import report as R
from dino_adapter import classify
BASE=ROOT/'workspace/windows-check/diagnostics/dino-full-evaluation-20261103'
OUT=ROOT/'workspace/dino-paired-reference-20261103'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def novel(c):
    e=c.get('change_evidence',{})
    return (c['area']>=25 and c['aspect']<=4 and c['bipolar']<=.3
            and c['shape_similarity']<=.65 and c['score']>=.18
            and e.get('remaining',0)>=12 and (not e.get('context_supported') or e.get('ratio',0)>.2))
def group(items):
    groups=[]
    for z in sorted(items,key=lambda z:(z['machine'],z['category'],z['c']['y'],z['c']['x'],z['name'])):
        c=z['c'];cx,cy=c['x']+c['w']/2,c['y']+c['h']/2
        g=next((g for g in groups if g[0]['machine']==z['machine'] and g[0]['category']==z['category'] and math.hypot(cx-g[0]['cx'],cy-g[0]['cy'])<=45),None)
        z['cx'],z['cy']=cx,cy
        if g is None:groups.append([z])
        else:g.append(z)
    return sorted(groups,key=lambda g:-len(g))
def main():
    OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
    model=ROOT/'models/dino-examples-a3b8c97aa539';m=read(model/'manifest.json')
    protected=[ROOT/'models/active.json',model/'manifest.json',model/'model.onnx',ROOT/'detector.py',ROOT/'dino_adapter.py',BASE/'results.json']
    rows=read(BASE/'report-rows.json');protected += [BASE/'photos'/r['sha256']/'result.json' for r in rows]
    before={str(p):digest(p) for p in protected}
    bankshas={n.rsplit('-',1)[0] for n in m['example_bank']['normal']['ids']}
    tracked={(z['sha256'],i) for z in read(BASE/'summary.json')['prior_suspected_cases'] for i in z['matching_ids']}
    allitems=[]
    for row in rows:
        rr=read(BASE/'photos'/row['sha256']/'result.json')
        known={i for k in row.get('known_checks',[]) for i in k['retained_ids']+k['removed_ids']}
        for c in rr['candidates']+rr['filtered_candidates']:
            key=f'{row["sha256"]}-{c["id"]}'
            allitems.append(dict(key=key,sha=row['sha256'],id=c['id'],name=row['relative'],machine=row['machine'],label=row['label'],c=c,
                removed=c['classification']['action']=='discard',novel=novel(c),bank_source=row['sha256'] in bankshas,
                known=c['id'] in known,tracked=(row['sha256'],c['id']) in tracked,
                category='細長外觀（待確認）' if c['aspect']>2 else '較圓或短塊外觀（待確認）'))
    shortlist=[z for z in allitems if z['label']=='NG' and z['removed'] and z['novel']]
    groups=group(shortlist)
    # Predeclared sample: up to 36 group representatives, all OK candidates,
    # existing annotations, prior six tracked regions, and user's two anchors.
    selected={z['key']:z for z in allitems if z['label']=='OK' or z['known'] or z['tracked'] or
              (z['name']=='MPT11/NG/1.png' and z['id']==7) or
              (z['name'].endswith('17_13_17_96.tiff') and z['id']==80)}
    for g in groups[:36]:selected[g[0]['key']]=g[0]
    plan=dict(source=str(BASE),model_hash=digest(model/'model.onnx'),manifest_hash=digest(model/'manifest.json'),
        shortlist_rule='area>=25, aspect<=4, bipolar<=.3, shape_similarity<=.65, score>=.18, remaining>=12, and unsupported context or ratio>.2',
        sampling='all 128 OK candidates + first 36 largest shortlist groups + existing marked/tracked regions + user anchors',
        sample_keys=list(selected),guard_rule='existing keep remains keep; existing discard with novelty becomes review; otherwise discard',
        naive_rule='both DINO screw => discard; target screw only => keep; otherwise discard',protected_hashes=before)
    (OUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1
    session=ort.InferenceSession(str(model/'model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    cachepath=OUT/'inference.json';cache=read(cachepath) if cachepath.exists() else {}
    for i,z in enumerate(selected.values(),1):
        if z['key'] not in cache:
            p=BASE/'photos'/z['sha'];c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'))
            predictions={}
            for side,file in [('reference','reference.png'),('target','aligned.png')]:
                with Image.open(p/file) as im:
                    crop=im.convert('L').crop((max(0,x-12),max(0,y-12),min(im.width,x+w+12),min(im.height,y+h+12)))
                    predictions[side]=classify(m,session,np.asarray(crop,np.float32)/255)
            original=c['classification']['screw_margin']
            assert abs(predictions['target']['screw_margin']-original)<1e-5,(z['key'],original,predictions['target']['screw_margin'])
            cache[z['key']]=predictions
            cachepath.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
        p=cache[z['key']];ref=p['reference']['screw_margin']>=0;tar=p['target']['screw_margin']>=0
        z['reference_screw']=ref;z['reference_margin']=p['reference']['screw_margin']
        z['naive']='排除' if ref or not tar else '保留'
        z['guard']='保留' if not z['removed'] else '待確認' if z['novel'] else '排除'
        if i%25==0:print('PAIRED',i,'/',len(selected),flush=True)
    def card(z):
        p=BASE/'photos'/z['sha'];c=z['c'];filename=z['key']+'.jpg';dest=OUT/'images'/filename
        if not dest.exists():
            x,y,w,h=(c[k] for k in ('x','y','w','h'));side=max(96,w+48,h+48)
            canvas=Image.new('RGB',(800,400),'white')
            for j,file in enumerate(['reference.png','aligned.png']):
                with Image.open(p/file) as im:
                    x0=max(0,min(im.width-side,x+w//2-side//2));y0=max(0,min(im.height-side,y+h//2-side//2))
                    crop=im.convert('RGB').crop((x0,y0,x0+side,y0+side));d=ImageDraw.Draw(crop);d.rectangle((x-x0,y-y0,x+w-x0,y+h-y0),outline='#e1263b',width=1)
                    canvas.paste(crop.resize((400,400)),(j*400,0))
            canvas.save(dest,quality=90)
        old='排除' if z['removed'] else '保留';tested=z['key'] in selected
        status=f'原方法：{old}。'
        if tested:
            status+=f'參照 DINO：{"像螺絲" if z["reference_screw"] else "較像正常範例"}；直接雙圖法：{z["naive"]}；新增物保護法：{z["guard"]}。'
        else:status+='未納入本次雙圖推論。'
        if z['known']:status+='【既有目視標記】'
        elif z['tracked']:status+='【前次疑似誤刪追蹤，未當成確定標籤】'
        else:status+='【尚未確認是不是螺絲】'
        href=os.path.relpath(p/'report.html',OUT).replace('\\','/')+('#removed-' if z['removed'] else '#candidate-')+str(z['id'])
        return f'<article id="case-{z["key"]}"><h3>{R.esc(z["name"])} · 位置 {z["id"]}</h3><p>{status}</p><p>左：參照圖　／　右：待測圖（紅框沿用差分）</p><img loading="lazy" style="width:100%;max-width:1000px" src="images/{filename}"><p><a href="{href}">查看完整照片與此位置 →</a> · <a href="#top">返回此頁總覽</a></p></article>'
    R.OUT=OUT
    nav='<nav id="top"><a href="index.html">總結果</a><a href="suspects.html">疑似誤刪分組</a><a href="good.html">良品對照</a><a href="bad.html">不良品實驗</a></nav>'
    body=nav+f'<h1>疑似誤刪：機種 → 外觀 → 相近位置</h1><div class="answer">掃描 2335 個已排除的不良品候選，挑出 {len(shortlist)} 個新增跡象候選，共 {len(groups)} 組。不是已確認誤刪數，也不保證找齊。</div><p>依既有差分紀錄挑選較集中、以新增暗物為主、與參照不太相似的位置；45 像素內分組。外觀分類只按長寬比例，不宣稱已辨認物件。同位置也不保證同一物件。</p>'
    for machine in sorted({z['machine'] for z in shortlist}):
        body+=f'<h2>{machine}</h2>'
        for cat in sorted({z['category'] for z in shortlist if z['machine']==machine}):
            body+=f'<h2>{cat}</h2>'
            for gi,g in enumerate(groups,1):
                if g[0]['machine']!=machine or g[0]['category']!=cat:continue
                body+=f'<section id="group-{gi}"><h2>第 {gi} 組：{len(g)} 個框／{len({z["sha"] for z in g})} 張照片</h2>'+card(g[0])
                if len(g)>1:body+=f'<details><summary>展開其他 {len(g)-1} 個案例</summary>'+''.join(card(z) for z in g[1:])+'</details>'
                body+='</section>'
    R.save('suspects.html','疑似誤刪分組',body)
    summary={}
    for label,title,file in [('OK','良品對照','good.html'),('NG','不良品小實驗','bad.html')]:
        zs=[z for z in selected.values() if z['label']==label]
        summary[label]=dict(candidates=len(zs),photos=len({z['sha'] for z in zs}),original_kept=sum(not z['removed'] for z in zs),naive_kept=sum(z['naive']=='保留' for z in zs),guard= dict(Counter(z['guard'] for z in zs)),bank_source_candidates=sum(z['bank_source'] for z in zs))
        body=nav+f'<h1>{title}</h1><p>按機種與相近位置分組；每組先看代表圖。待確認不是已確認螺絲，也不是檢出成功。</p>'
        for gi,g in enumerate(group(zs),1):
            body+=f'<h2>{g[0]["machine"]} / {g[0]["category"]} / 第 {gi} 組 · {len(g)} 個框</h2>'+card(g[0])
            if len(g)>1:body+=f'<details><summary>展開另外 {len(g)-1} 個案例</summary>'+''.join(card(z) for z in g[1:])+'</details>'
        R.save(file,title,body)
    summary.update(shortlist=len(shortlist),groups=len(groups),sample=len(selected),known=[dict(name=z['name'],id=z['id'],naive=z['naive'],guard=z['guard']) for z in selected.values() if z['known']])
    body=nav+'<h1>DINO 加看參照圖：離線小實驗</h1><p>使用既有結果；未補框、未改正式模型、未重跑差分。候選挑選規則與樣本名單在推論前寫入 plan.json，未用本次結果反覆調門檻。</p><div class="answer"><b>結論：只加看參照圖，還不能解決誤刪。</b><p>你提出的圖二，以及 5.png、9.png 的既有目視螺絲標記，直接雙圖法仍排除。新增物保護法讓它們轉為待確認，但良品也新增 17 個待確認框。先不套用正式流程。</p><p><a href="#priority">先看另外找到的 3 個優先核對案例 →</a></p><b>本次比較的是處理方式，不是完整準確率。</b><p>直接雙圖法：兩張都像螺絲就排除；只有待測像螺絲才保留。</p><p>新增物保護法：原本保留的仍保留；原本排除但有新增跡象者轉待確認。此法目前不自動刪除「兩邊都有螺絲」的候選，因為尚未證明是同一顆。這是保護規則，不能把改善歸功於參照 DINO。</p></div>'
    body+='<table><tr><th>測試範圍</th><th>候選數</th><th>原方法保留</th><th>直接雙圖法保留</th><th>保護法：保留／待確認／排除</th></tr>'
    for label,s in [('良品',summary['OK']),('不良品抽樣',summary['NG'])]:
        g=s['guard'];body+=f'<tr><td>{label}</td><td>{s["candidates"]}</td><td>{s["original_kept"]}</td><td>{s["naive_kept"]}</td><td>{g.get("保留",0)}／{g.get("待確認",0)}／{g.get("排除",0)}</td></tr>'
    body+='</table><p>良品中所有保留或待確認都增加檢查負擔；不良品抽樣刻意包含疑似誤刪，不代表整批比例。良品部分照片曾供正常範例，不能當成獨立驗收。</p>'
    body+=f'<p><a href="suspects.html">先看 {len(shortlist)} 個候選、{len(groups)} 組代表圖 →</a>　<a href="bad.html">看不良品實驗 →</a>　<a href="good.html">看良品誤報代價 →</a></p><h2>既有目視標記（獨立列出）</h2>'
    for z in selected.values():
        if z['known'] or (z['name']=='MPT11/NG/1.png' and z['id']==7) or (z['name'].endswith('17_13_17_96.tiff') and z['id']==80):body+=card(z)
    body+='<h2 id="priority">另外找到的 3 個優先核對案例</h2><p>助手抽看 12 組代表圖後挑出：參照同位置未見相同物件，待測多出帶頭／桿或圓形暗物。屬目視疑似螺絲，尚未由使用者確認；未將這 3 例當成已確認螺絲計算準確率。其他候選尚未逐框目視。</p>'
    spotlight=[]
    for prefix,cid in [('e2bf682d',2),('afd64da5',10),('a2fb377a',5)]:
        z=next(z for z in shortlist if z['sha'].startswith(prefix) and z['id']==cid)
        gi,g=next((i,g) for i,g in enumerate(groups,1) if any(t['key']==z['key'] for t in g))
        body+=card(z)+f'<p><a href="suspects.html#group-{gi}">查看此組全部 {len(g)} 個相近位置 →</a></p>'
        spotlight.append(dict(key=z['key'],name=z['name'],group=gi,group_candidates=len(g),basis='assistant visual suspicion, not user-confirmed'))
    (OUT/'visual-shortlist.json').write_text(json.dumps(spotlight,ensure_ascii=False,indent=2),encoding='utf-8')
    body+='<p>候選未經逐框確認，不能將待確認數稱為救回螺絲數。篩選未涵蓋細長、弱差異等情況，未入選不等於沒有漏檢。</p><p><a href="plan.json">固定實驗規則</a> · <a href="summary.json">統計資料</a></p>'
    R.save('index.html','DINO 雙圖小實驗',body)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'cases.json').write_text(json.dumps(dict(shortlist=shortlist,selected=list(selected.values())),ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(digest(Path(p))==v for p,v in before.items()),'Protected files changed'
    print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
